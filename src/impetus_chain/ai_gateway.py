import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    label: str
    kind: str
    model: str
    api_key_env: str
    base_url: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        provider_id="openai",
        label="OpenAI GPT-5.5 (娣卞害鍒嗘瀽)",
        kind="openai_responses",
        model="gpt-5.5",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1/responses",
    ),
    "openai_gpt54": ProviderSpec(
        provider_id="openai_gpt54",
        label="OpenAI GPT-5.4 (骞宠　閫熷害/璐ㄩ噺)",
        kind="openai_responses",
        model="gpt-5.4",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1/responses",
    ),
    "openai_gpt54mini": ProviderSpec(
        provider_id="openai_gpt54mini",
        label="OpenAI GPT-5.4-mini (楂橀/浣庢垚鏈?",
        kind="openai_responses",
        model="gpt-5.4-mini",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1/responses",
    ),
    "anthropic": ProviderSpec(
        provider_id="anthropic",
        label="Anthropic",
        kind="anthropic_messages",
        model="claude-3-5-sonnet-20241022",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1/messages",
    ),
    "gemini": ProviderSpec(
        provider_id="gemini",
        label="Google Gemini",
        kind="gemini_generate_content",
        model="gemini-1.5-pro",
        api_key_env="GEMINI_API_KEY",
    ),
    "deepseek": ProviderSpec(
        provider_id="deepseek",
        label="DeepSeek",
        kind="openai_compatible",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com/chat/completions",
    ),
    "qwen": ProviderSpec(
        provider_id="qwen",
        label="Qwen (DashScope)",
        kind="openai_compatible",
        model="qwen-plus",
        api_key_env="DASHSCOPE_API_KEY",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    ),
}


MODULE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_DIR / 'prompts'
FULL_PROMPT_PATH = PROMPTS_DIR / 'node_analysis_full_prompt.txt'
STEP_PROMPT_PATH = PROMPTS_DIR / 'node_analysis_step_prompt.txt'

def provider_status() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for provider in PROVIDERS.values():
        rows.append(
            {
                "provider_id": provider.provider_id,
                "label": provider.label,
                "enabled": bool(os.getenv(provider.api_key_env, "").strip()),
                "api_key_env": provider.api_key_env,
            }
        )
    return rows


def _mask_headers(headers: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "x-api-key"}:
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def _http_post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    progress: Callable[[str], None] | None = None,
) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    if progress:
        progress(
            "API request\n"
            f"url: {url}\n"
            f"headers: {json.dumps(_mask_headers(headers), ensure_ascii=False)}\n"
            f"payload: {json.dumps(payload, ensure_ascii=False)}"
        )
    req = urllib.request.Request(url=url, data=raw, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            if progress:
                progress(f"API response\nstatus: {getattr(resp, 'status', 'unknown')}\nbody: {body}")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        if progress:
            progress(f"API HTTP error {exc.code}\nbody: {err_body}")
        raise RuntimeError(f"AI HTTP error {exc.code}: {err_body}") from exc
    except urllib.error.URLError as exc:
        if progress:
            progress(f"API network error: {exc.reason}")
        raise RuntimeError(f"AI network error: {exc.reason}") from exc


def _read_prompt_template(path: Path, fallback: str) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return fallback


def _render_prompt(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace(key, value)
    return out


def _build_prompt(
    project: str,
    node: str,
    core_intro: str,
    strategy_text: str,
    prompt_script_text: str,
) -> str:
    fallback = (
        "You are a financial research assistant.\n\n"
        "Project Context:\n"
        "- Project: __PROJECT__\n"
        "- Selected Node: __NODE__\n"
        "- Core Impetus Intro: __CORE_INTRO__\n\n"
        "You MUST follow these 5 analysis steps and output machine-readable keys first.\n\n"
        "Analysis Strategy File (authoritative project core):\n"
        "__STRATEGY_TEXT__\n\n"
        "AI Prompt Script File (communication protocol):\n"
        "__PROMPT_SCRIPT_TEXT__\n"
    )
    template = _read_prompt_template(FULL_PROMPT_PATH, fallback)
    return _render_prompt(
        template,
        {
            "__PROJECT__": project,
            "__NODE__": node,
            "__CORE_INTRO__": core_intro or "N/A",
            "__STRATEGY_TEXT__": strategy_text or "[EMPTY]",
            "__PROMPT_SCRIPT_TEXT__": prompt_script_text or "[EMPTY]",
        },
    )


def _build_step_prompt(
    project: str,
    node: str,
    core_intro: str,
    strategy_text: str,
    prompt_script_text: str,
    step_name: str,
    step_instruction: str,
    required_keys: list[str],
) -> str:
    key_lines = ", ".join(required_keys)
    fallback = (
        "You are a financial research assistant.\n\n"
        "Project Context:\n"
        "- Project: __PROJECT__\n"
        "- Selected Node: __NODE__\n"
        "- Core Impetus Intro: __CORE_INTRO__\n\n"
        "Current Step: __STEP_NAME__\n"
        "Instruction: __STEP_INSTRUCTION__\n\n"
        "Output must be STRICT JSON only (no markdown, no prose, no code fences).\n"
        "Use exactly one JSON object with these keys:\n"
        "__REQUIRED_KEYS__\n\n"
        "Analysis Strategy File (authoritative project core):\n"
        "__STRATEGY_TEXT__\n\n"
        "AI Prompt Script File (communication protocol):\n"
        "__PROMPT_SCRIPT_TEXT__\n\n"
        "If uncertain, still return valid JSON with best estimate and concise values."
    )
    template = _read_prompt_template(STEP_PROMPT_PATH, fallback)
    return _render_prompt(
        template,
        {
            "__PROJECT__": project,
            "__NODE__": node,
            "__CORE_INTRO__": core_intro or "N/A",
            "__STEP_NAME__": step_name,
            "__STEP_INSTRUCTION__": step_instruction,
            "__REQUIRED_KEYS__": key_lines,
            "__STRATEGY_TEXT__": strategy_text or "[EMPTY]",
            "__PROMPT_SCRIPT_TEXT__": prompt_script_text or "[EMPTY]",
        },
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        chunk = text[start : end + 1]
        try:
            parsed = json.loads(chunk)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _normalize_text_value(value: Any, max_len: int = 240) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text[:max_len]


def _normalize_impetus_type(value: Any) -> str:
    raw = _normalize_text_value(value, max_len=64).lower()
    allowed = {
        "natural_disaster",
        "political_event",
        "social_event",
        "technology_progress",
    }
    return raw if raw in allowed else "social_event"


def _normalize_list(value: Any, max_items: int = 8, max_len: int = 80) -> list[str]:
    if isinstance(value, list):
        items = [str(v).strip() for v in value]
    else:
        items = [s.strip() for s in str(value or "").split(",")]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        norm = " ".join(item.split())[:max_len]
        key = norm.casefold()
        if not norm or key in seen:
            continue
        seen.add(key)
        out.append(norm)
        if len(out) >= max_items:
            break
    return out


def _call_openai_compatible(
    spec: ProviderSpec, api_key: str, prompt: str, progress: Callable[[str], None] | None = None
) -> str:
    payload = {
        "model": spec.model,
        "messages": [
            {"role": "system", "content": "You are a concise financial analyst assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    body = _http_post_json(
        url=spec.base_url,
        payload=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        progress=progress,
    )
    return str(body["choices"][0]["message"]["content"]).strip()


def _extract_openai_response_text(body: dict) -> str:
    output_text = str(body.get("output_text", "")).strip()
    if output_text:
        return output_text
    chunks: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            text = str(content.get("text", "")).strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _call_openai_responses(
    spec: ProviderSpec, api_key: str, prompt: str, progress: Callable[[str], None] | None = None
) -> str:
    payload = {
        "model": spec.model,
        "reasoning": {"effort": "high"},
        "tools": [{"type": "web_search"}],
        "input": prompt,
    }
    body = _http_post_json(
        url=spec.base_url,
        payload=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        progress=progress,
    )
    return _extract_openai_response_text(body)


def _call_anthropic(
    spec: ProviderSpec, api_key: str, prompt: str, progress: Callable[[str], None] | None = None
) -> str:
    payload = {
        "model": spec.model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    body = _http_post_json(
        url=spec.base_url,
        payload=payload,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        progress=progress,
    )
    parts = body.get("content", [])
    texts = [str(item.get("text", "")) for item in parts if item.get("type") == "text"]
    return "\n".join(t for t in texts if t).strip()


def _call_gemini(
    spec: ProviderSpec, api_key: str, prompt: str, progress: Callable[[str], None] | None = None
) -> str:
    encoded_model = urllib.parse.quote(spec.model, safe="")
    key = urllib.parse.quote(api_key, safe="")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{encoded_model}:generateContent?key={key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    body = _http_post_json(url=url, payload=payload, headers={}, progress=progress)
    candidates = body.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [str(item.get("text", "")) for item in parts]
    return "\n".join(t for t in texts if t).strip()


def analyze_node_with_ai(
    provider_id: str,
    project: str,
    node: str,
    core_intro: str = "",
    strategy_text: str = "",
    prompt_script_text: str = "",
    api_key_override: str = "",
    progress: Callable[[str], None] | None = None,
) -> str:
    spec = PROVIDERS.get(provider_id)
    if spec is None:
        raise ValueError(f"Unsupported AI provider: {provider_id}")

    api_key = api_key_override.strip() or os.getenv(spec.api_key_env, "").strip()
    if not api_key:
        raise ValueError(f"Missing API key: set env var {spec.api_key_env}")

    prompt = _build_prompt(
        project=project,
        node=node,
        core_intro=core_intro,
        strategy_text=strategy_text,
        prompt_script_text=prompt_script_text,
    )
    if progress:
        progress(f"Prompt\n{prompt}")
    if spec.kind == "openai_responses":
        return _call_openai_responses(spec=spec, api_key=api_key, prompt=prompt, progress=progress)
    if spec.kind == "openai_compatible":
        return _call_openai_compatible(spec=spec, api_key=api_key, prompt=prompt, progress=progress)
    if spec.kind == "anthropic_messages":
        return _call_anthropic(spec=spec, api_key=api_key, prompt=prompt, progress=progress)
    if spec.kind == "gemini_generate_content":
        return _call_gemini(spec=spec, api_key=api_key, prompt=prompt, progress=progress)
    raise ValueError(f"Unsupported provider kind: {spec.kind}")


def analyze_node_with_ai_five_steps(
    provider_id: str,
    project: str,
    node: str,
    core_intro: str = "",
    strategy_text: str = "",
    prompt_script_text: str = "",
    api_key_override: str = "",
    progress: Callable[[str], None] | None = None,
) -> str:
    spec = PROVIDERS.get(provider_id)
    if spec is None:
        raise ValueError(f"Unsupported AI provider: {provider_id}")

    api_key = api_key_override.strip() or os.getenv(spec.api_key_env, "").strip()
    if not api_key:
        raise ValueError(f"Missing API key: set env var {spec.api_key_env}")

    steps = [
        (
            "Step-1",
            "Classify impetus type from exactly one option: natural_disaster/political_event/social_event/technology_progress.",
            ["impetus_type"],
        ),
        (
            "Step-2",
            "Estimate expected duration and force evolution pattern.",
            ["duration_estimate", "force_pattern"],
        ),
        (
            "Step-3",
            "Estimate impact magnitude using global financial market cap change (USD range).",
            ["impact_market_cap_change_range_usd"],
        ),
        (
            "Step-4",
            "Identify directly tradable speculation targets (commodities/equities/bonds/currencies/indices).",
            ["direct_spec_targets"],
        ),
        (
            "Step-5",
            "Generate next-level expansion child nodes (3-8 short noun phrases) as JSON array.",
            ["next_level_nodes_json"],
        ),
    ]

    structured: dict[str, Any] = {
        "impetus_type": "social_event",
        "duration_estimate": "",
        "force_pattern": "",
        "impact_market_cap_change_range_usd": "",
        "direct_spec_targets": [],
        "next_level_nodes_json": [],
    }

    for idx, (step_name, instruction, keys) in enumerate(steps, start=1):
        if progress:
            progress(f"{step_name}: 发起第 {idx}/5 次 API 调用")
        step_prompt = _build_step_prompt(
            project=project,
            node=node,
            core_intro=core_intro,
            strategy_text=strategy_text,
            prompt_script_text=prompt_script_text,
            step_name=step_name,
            step_instruction=instruction,
            required_keys=keys,
        )
        if progress:
            progress(f"{step_name} Prompt\n{step_prompt}")
        if spec.kind == "openai_responses":
            step_text = _call_openai_responses(
                spec=spec, api_key=api_key, prompt=step_prompt, progress=progress
            )
        elif spec.kind == "openai_compatible":
            step_text = _call_openai_compatible(
                spec=spec, api_key=api_key, prompt=step_prompt, progress=progress
            )
        elif spec.kind == "anthropic_messages":
            step_text = _call_anthropic(
                spec=spec, api_key=api_key, prompt=step_prompt, progress=progress
            )
        elif spec.kind == "gemini_generate_content":
            step_text = _call_gemini(
                spec=spec, api_key=api_key, prompt=step_prompt, progress=progress
            )
        else:
            raise ValueError(f"Unsupported provider kind: {spec.kind}")

        if progress:
            progress(f"{step_name}: 完成第 {idx}/5 次 API 调用")
        data = _extract_json_object(step_text)
        if not data:
            if progress:
                progress(f"{step_name}: 未解析到 JSON，将使用默认/空值")
            data = {}

        if "impetus_type" in keys:
            structured["impetus_type"] = _normalize_impetus_type(data.get("impetus_type"))
        if "duration_estimate" in keys:
            structured["duration_estimate"] = _normalize_text_value(
                data.get("duration_estimate"), 120
            )
        if "force_pattern" in keys:
            structured["force_pattern"] = _normalize_text_value(data.get("force_pattern"), 120)
        if "impact_market_cap_change_range_usd" in keys:
            structured["impact_market_cap_change_range_usd"] = _normalize_text_value(
                data.get("impact_market_cap_change_range_usd"), 160
            )
        if "direct_spec_targets" in keys:
            structured["direct_spec_targets"] = _normalize_list(
                data.get("direct_spec_targets"), max_items=12, max_len=64
            )
        if "next_level_nodes_json" in keys:
            structured["next_level_nodes_json"] = _normalize_list(
                data.get("next_level_nodes_json"), max_items=8, max_len=80
            )

    return (
        f"impetus_type: {structured['impetus_type']}\n"
        f"duration_estimate: {structured['duration_estimate'] or 'unspecified'}\n"
        f"force_pattern: {structured['force_pattern'] or 'unspecified'}\n"
        f"impact_market_cap_change_range_usd: {structured['impact_market_cap_change_range_usd'] or 'unspecified'}\n"
        f"direct_spec_targets: {', '.join(structured['direct_spec_targets']) or 'unspecified'}\n"
        f"next_level_nodes_json: {json.dumps(structured['next_level_nodes_json'], ensure_ascii=False)}\n"
        f"structured_json: {json.dumps(structured, ensure_ascii=False)}"
    )


