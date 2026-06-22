import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from .project_store import ensure_project_dirs, project_core_dir


def project_secret_path(project: str) -> Path:
    return project_core_dir(project) / "api_keys.enc.json"


def _master_key_bytes() -> bytes:
    master = os.getenv("IMPETUS_SECRETS_MASTER_KEY", "").strip()
    if not master:
        # Dev fallback. Strongly recommend setting IMPETUS_SECRETS_MASTER_KEY.
        master = "impetus-local-dev-master-key"
    return master.encode("utf-8")


def _derive_keys(master_key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    material = hashlib.pbkdf2_hmac("sha256", master_key, salt, 200_000, dklen=64)
    return material[:32], material[32:]


def _keystream_xor(data: bytes, enc_key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hashlib.sha256(enc_key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out[: len(data)]))


def _encrypt_value(plaintext: str) -> dict:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    enc_key, mac_key = _derive_keys(_master_key_bytes(), salt)
    cipher = _keystream_xor(plaintext.encode("utf-8"), enc_key, nonce)
    mac = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    return {
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "cipher_b64": base64.b64encode(cipher).decode("ascii"),
        "mac_b64": base64.b64encode(mac).decode("ascii"),
    }


def _decrypt_value(record: dict) -> str:
    salt = base64.b64decode(record["salt_b64"])
    nonce = base64.b64decode(record["nonce_b64"])
    cipher = base64.b64decode(record["cipher_b64"])
    mac = base64.b64decode(record["mac_b64"])
    enc_key, mac_key = _derive_keys(_master_key_bytes(), salt)
    expected = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Secret integrity check failed.")
    plain = _keystream_xor(cipher, enc_key, nonce)
    return plain.decode("utf-8")


def _load_store(project: str) -> dict:
    path = project_secret_path(project)
    if not path.exists():
        return {"version": 1, "providers": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_store(project: str, store: dict) -> Path:
    ensure_project_dirs(project)
    path = project_secret_path(project)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return path


def save_project_api_key(project: str, provider_id: str, api_key: str) -> Path:
    clean = api_key.strip()
    if not clean:
        raise ValueError("API key cannot be empty.")
    store = _load_store(project)
    providers = store.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}
    providers[provider_id] = _encrypt_value(clean)
    store["providers"] = providers
    return _save_store(project, store)


def get_project_api_key(project: str, provider_id: str) -> str:
    store = _load_store(project)
    providers = store.get("providers", {})
    if not isinstance(providers, dict):
        return ""
    record = providers.get(provider_id)
    if not isinstance(record, dict):
        return ""
    try:
        return _decrypt_value(record)
    except Exception:
        return ""


def has_project_api_key(project: str, provider_id: str) -> bool:
    return bool(get_project_api_key(project, provider_id))

