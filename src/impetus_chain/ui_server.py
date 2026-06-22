from collections import defaultdict
import base64
from datetime import datetime, timezone
from html import escape
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import struct
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlparse

from .ai_gateway import PROVIDERS, analyze_node_with_ai_five_steps, provider_status
from .project_secrets import get_project_api_key, has_project_api_key, save_project_api_key
from .project_service import create_project
from .project_store import (
    load_chain_project,
    project_ai_prompt_path,
    project_chain_path,
    project_strategy_path,
    read_text_file,
    save_analysis_result,
    save_chain_project,
)

MODULE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = MODULE_DIR / "templates" / "index.html"
APP_JS_PATH = MODULE_DIR / "static" / "app.js"

def _ws_read_exact(conn: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            raise ConnectionError("websocket closed")
        data += chunk
    return data


def _ws_read_frame(conn: socket.socket) -> tuple[int, bytes]:
    header = _ws_read_exact(conn, 2)
    b1, b2 = header[0], header[1]
    opcode = b1 & 0x0F
    masked = (b2 & 0x80) != 0
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", _ws_read_exact(conn, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _ws_read_exact(conn, 8))[0]
    mask = _ws_read_exact(conn, 4) if masked else b""
    payload = _ws_read_exact(conn, length) if length else b""
    if masked and payload:
        payload = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
    return opcode, payload


def _ws_send_frame(conn: socket.socket, payload: bytes, opcode: int = 0x1) -> None:
    first = bytes([0x80 | (opcode & 0x0F)])
    length = len(payload)
    if length < 126:
        head = first + bytes([length])
    elif length <= 0xFFFF:
        head = first + bytes([126]) + struct.pack("!H", length)
    else:
        head = first + bytes([127]) + struct.pack("!Q", length)
    conn.sendall(head + payload)


class _WebSocketClient:
    def __init__(self, conn: socket.socket) -> None:
        self.conn = conn
        self.lock = threading.Lock()

    def send_json(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self.lock:
            _ws_send_frame(self.conn, data, opcode=0x1)


class _WebSocketBroker:
    def __init__(self) -> None:
        self._channels: dict[str, set[_WebSocketClient]] = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, channel: str, client: _WebSocketClient) -> None:
        with self._lock:
            self._channels[channel].add(client)

    def unsubscribe(self, channel: str, client: _WebSocketClient) -> None:
        with self._lock:
            clients = self._channels.get(channel)
            if not clients:
                return
            clients.discard(client)
            if not clients:
                self._channels.pop(channel, None)

    def publish_event(self, channel: str, event: dict) -> None:
        with self._lock:
            clients = list(self._channels.get(channel, set()))
        dead: list[_WebSocketClient] = []
        for client in clients:
            try:
                client.send_json(event)
            except Exception:
                dead.append(client)
        if dead:
            with self._lock:
                current = self._channels.get(channel, set())
                for client in dead:
                    current.discard(client)

    def publish_text(self, channel: str, text: str) -> None:
        self.publish_event(
            channel,
            {
                "type": "progress",
                "text": text,
                "at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )


WS_BROKER = _WebSocketBroker()


def list_existing_projects() -> list[str]:
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []
    names: list[str] = []
    for child in projects_dir.iterdir():
        if child.is_dir() and project_chain_path(child.name).exists():
            names.append(child.name)
    return sorted(names)


def resolve_selected_project(requested: str | None, projects: list[str]) -> str | None:
    if requested in projects:
        return requested
    if projects:
        return projects[0]
    return None


def resolve_selected_provider(
    project: str | None, payload: dict, requested_provider: str | None
) -> str:
    all_provider_ids = list(PROVIDERS.keys())
    if requested_provider in all_provider_ids:
        return requested_provider
    mapping = payload.get("task_ai_mapping", {})
    if isinstance(mapping, dict):
        mapped = mapping.get("node_speculation")
        if mapped in all_provider_ids:
            return mapped
    for row in provider_status():
        pid = str(row["provider_id"])
        if row["enabled"] or (project and has_project_api_key(project, pid)):
            return pid
    return all_provider_ids[0]


def load_project_view(project: str | None) -> dict:
    if not project:
        return {}
    try:
        return load_chain_project(project)
    except Exception:
        return {}


def build_tree_view(payload: dict) -> tuple[str, list[dict]]:
    root = str(payload.get("root", "")).strip()
    edges = payload.get("edges", [])
    children_map: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        src = str(edge.get("src", "")).strip()
        dst = str(edge.get("dst", "")).strip()
        if src and dst:
            children_map[src].append(dst)
    rows: list[dict] = []
    for l1 in children_map.get(root, []):
        rows.append({"node": l1, "children": children_map.get(l1, [])})
    return root, rows


def _project_options(projects: list[str], selected: str | None) -> str:
    if not projects:
        return '<option value="">鏆傛棤椤圭洰</option>'
    parts: list[str] = []
    for name in projects:
        flag = " selected" if name == selected else ""
        parts.append(f'<option value="{escape(name)}"{flag}>{escape(name)}</option>')
    return "".join(parts)


def _provider_options(project: str | None, selected_provider: str) -> str:
    parts: list[str] = []
    for row in provider_status():
        provider_id = str(row["provider_id"])
        label = str(row["label"])
        env_enabled = bool(row["enabled"])
        proj_enabled = bool(project and has_project_api_key(project, provider_id))
        key_env = str(row["api_key_env"])
        if proj_enabled:
            state = "项目已保存"
        elif env_enabled:
            state = "环境变量已配置"
        else:
            state = f"未配置({key_env})"
        selected = " selected" if provider_id == selected_provider else ""
        parts.append(
            f"<option value='{escape(provider_id)}'{selected}>{escape(label)} - {escape(state)}</option>"
        )
    return "".join(parts)


def _provider_options_simple(project: str | None, selected_provider: str) -> str:
    parts: list[str] = []
    for row in provider_status():
        provider_id = str(row["provider_id"])
        label = str(row["label"])
        env_enabled = bool(row["enabled"])
        proj_enabled = bool(project and has_project_api_key(project, provider_id))
        key_env = str(row["api_key_env"])
        if proj_enabled:
            state = "项目已保存"
        elif env_enabled:
            state = "环境变量已配置"
        else:
            state = f"未配置({key_env})"
        selected = " selected" if provider_id == selected_provider else ""
        parts.append(
            f"<option value='{escape(provider_id)}'{selected}>{escape(label)} - {escape(state)}</option>"
        )
    return "".join(parts)


def _impetus_type_label(value: str) -> str:
    mapping = {
        "natural_disaster": "澶╃伨",
        "political_event": "鏀挎不浜嬩欢",
        "social_event": "绀句細浜嬩欢",
        "technology_progress": "绉戞妧杩涙",
    }
    return mapping.get(value, "未识别")


def _json_for_script(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def extract_impetus_type(analysis_text: str) -> str:
    m = re.search(
        r"impetus_type\s*[:：]\s*(natural_disaster|political_event|social_event|technology_progress)",
        analysis_text,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).lower()
    return ""


def extract_duration_estimate(analysis_text: str) -> str:
    m = re.search(r"duration_estimate\s*[:：]\s*(.+)", analysis_text, flags=re.IGNORECASE)
    if not m:
        return ""
    return m.group(1).strip().splitlines()[0][:120]


def extract_force_pattern(analysis_text: str) -> str:
    m = re.search(r"force_pattern\s*[:：]\s*(.+)", analysis_text, flags=re.IGNORECASE)
    if not m:
        return ""
    return m.group(1).strip().splitlines()[0][:120]


def extract_impact_range(analysis_text: str) -> str:
    m = re.search(
        r"impact_market_cap_change_range_usd\s*[:：]\s*(.+)",
        analysis_text,
        flags=re.IGNORECASE,
    )
    if not m:
        return ""
    return m.group(1).strip().splitlines()[0][:160]


def _extract_field(analysis_text: str, key: str, max_len: int = 240) -> str:
    m = re.search(rf"{re.escape(key)}\s*[:：]\s*(.+)", analysis_text, flags=re.IGNORECASE)
    if not m:
        return ""
    return m.group(1).strip().splitlines()[0][:max_len]


def extract_next_level_nodes(analysis_text: str) -> list[str]:
    m_json = re.search(
        r"next_level_nodes_json\s*[:：]\s*(\[[\s\S]*?\])",
        analysis_text,
        flags=re.IGNORECASE,
    )
    raw = ""
    if m_json:
        raw = m_json.group(1).strip()
    else:
        m_line = re.search(
            r"next_level_nodes\s*[:：]\s*(.+)",
            analysis_text,
            flags=re.IGNORECASE,
        )
        if m_line:
            raw = m_line.group(1).strip()
    if not raw:
        return []

    items: list[str] = []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                items = [str(x).strip() for x in parsed]
        except Exception:
            items = []
    if not items:
        items = [p.strip() for p in raw.split(",")]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        node = re.sub(r"\s+", " ", item).strip().strip("-*'\"")
        if not node:
            continue
        key = node.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(node[:80])
    return cleaned


def merge_next_level_nodes(payload: dict, parent_node: str, children: list[str]) -> int:
    if not parent_node or not children:
        return 0
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        nodes = []
    edges = payload.get("edges", [])
    if not isinstance(edges, list):
        edges = []

    existing_node_names = {
        str(n.get("name", "")).strip().casefold()
        for n in nodes
        if isinstance(n, dict) and str(n.get("name", "")).strip()
    }
    existing_edges = {
        (
            str(e.get("src", "")).strip().casefold(),
            str(e.get("dst", "")).strip().casefold(),
        )
        for e in edges
        if isinstance(e, dict)
    }

    added = 0
    parent_key = parent_node.strip().casefold()
    for child in children:
        child_name = child.strip()
        if not child_name:
            continue
        child_key = child_name.casefold()
        if child_key == parent_key:
            continue
        if child_key not in existing_node_names:
            nodes.append({"name": child_name, "layer": "auto_generated"})
            existing_node_names.add(child_key)
        edge_key = (parent_key, child_key)
        if edge_key not in existing_edges:
            edges.append({"src": parent_node, "dst": child_name, "weight": 0.5})
            existing_edges.add(edge_key)
            added += 1

    payload["nodes"] = nodes
    payload["edges"] = edges
    return added


def _branch_item(row: dict, side: str, branch_id: str) -> str:
    node = escape(str(row["node"]))
    children = row["children"]
    if children:
        children_html = "".join(
            f"<li class='l2-node' data-node='{escape(str(c))}' data-parent='{branch_id}'>{escape(str(c))}</li>"
            for c in children
        )
    else:
        children_html = "<li class='l2-node' data-node='none'>鏆傛棤浜岀骇瀛愰」鐩?/li>"
    return (
        f"<div class='branch-item {side}'>"
        f"<button type='button' class='l1-node branch-toggle' data-node='{node}' data-side='{side}' data-target='{branch_id}' aria-expanded='true'>{node}</button>"
        f"<ul id='{branch_id}' class='l2-list'>{children_html}</ul>"
        "</div>"
    )


def _tree_html(root: str, rows: list[dict]) -> str:
    if not root:
        return "<div class='empty'>鏆傛棤鏍戠粨鏋勬暟鎹紝璇峰厛鍒涘缓骞堕€夋嫨椤圭洰銆?/div>"
    if not rows:
        return (
            "<div class='mindmap'>"
            "<svg class='link-layer' aria-hidden='true'></svg>"
            f"<div id='center-node' class='center-node' data-node='{escape(root)}'>{escape(root)}</div>"
            "</div>"
        )
    left_rows = rows[::2]
    right_rows = rows[1::2]
    left_html = "".join(
        _branch_item(row, "left", f"branch-left-{i}") for i, row in enumerate(left_rows)
    )
    right_html = "".join(
        _branch_item(row, "right", f"branch-right-{i}") for i, row in enumerate(right_rows)
    )
    return (
        "<div class='mindmap'>"
        "<svg class='link-layer' aria-hidden='true'></svg>"
        f"<div class='branch-column left'>{left_html}</div>"
        f"<div id='center-node' class='center-node' data-node='{escape(root)}'>{escape(root)}</div>"
        f"<div class='branch-column right'>{right_html}</div>"
        "</div>"
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fill_tokens(template: str, tokens: dict[str, str]) -> str:
    result = template
    for key, value in tokens.items():
        result = result.replace(key, value)
    return result


def render_page(
    projects: list[str],
    selected_project: str | None,
    selected_provider: str,
    payload: dict,
    message: str = "",
    level: str = "info",
) -> bytes:
    tone = "#0f766e" if level == "success" else "#b45309" if level == "warn" else "#334155"
    safe_message = escape(message) if message else ""
    project_name = selected_project or ""
    options_html = _project_options(projects, selected_project)
    provider_options_html = _provider_options(project_name or None, selected_provider)
    provider_simple_html = _provider_options_simple(project_name or None, selected_provider)
    core_intro = str(payload.get("core_impetus_intro", "")).strip()
    impetus_type = str(payload.get("impetus_type", "")).strip()
    impetus_type_label = _impetus_type_label(impetus_type)
    duration_estimate = str(payload.get("duration_estimate", "")).strip()
    force_pattern = str(payload.get("force_pattern", "")).strip()
    impact_range = str(payload.get("impact_market_cap_change_range_usd", "")).strip()
    direct_spec_targets = str(payload.get("direct_spec_targets", "")).strip()
    next_level_nodes = payload.get("next_level_nodes", [])
    if not isinstance(next_level_nodes, list):
        next_level_nodes = []
    next_level_nodes_text = ", ".join(str(x) for x in next_level_nodes if str(x).strip())
    analysis_log = payload.get("analysis_log", [])
    button_text = "分析节点" if len(analysis_log) == 0 else "再分析节点"

    latest_analysis = ""
    analysis_results = payload.get("analysis_results", [])
    analysis_by_node: dict[str, str] = {}
    if isinstance(analysis_results, list) and analysis_results:
        latest = analysis_results[-1]
        if isinstance(latest, dict):
            latest_analysis = str(latest.get("analysis_text", "")).strip()
        for item in analysis_results:
            if not isinstance(item, dict):
                continue
            node_name = str(item.get("node", "")).strip()
            node_text = str(item.get("analysis_text", "")).strip()
            if node_name and node_text:
                analysis_by_node[node_name] = node_text
    last_selected_node = str(payload.get("last_selected_node", "")).strip()
    root, rows = build_tree_view(payload)
    tree_html = _tree_html(root, rows)
    latest_analysis_html = escape(latest_analysis) if latest_analysis else "暂无分析结果"
    message_html = f'<div class="msg">{safe_message}</div>' if safe_message else ""
    app_state_json = _json_for_script(
        {
            "analysisByNode": analysis_by_node,
            "lastSelectedNode": last_selected_node,
            "projectName": project_name,
        }
    )
    template = _read_text(TEMPLATE_PATH)
    html = _fill_tokens(
        template,
        {
            "__MSG_TONE__": tone,
            "__OPTIONS_HTML__": options_html,
            "__PROJECT_NAME__": escape(project_name),
            "__PROVIDER_OPTIONS_HTML__": provider_options_html,
            "__PROVIDER_SIMPLE_HTML__": provider_simple_html,
            "__BUTTON_TEXT__": escape(button_text),
            "__CORE_INTRO__": escape(core_intro),
            "__IMPETUS_TYPE_LABEL__": escape(impetus_type_label),
            "__DURATION_ESTIMATE__": escape(duration_estimate or "未识别"),
            "__FORCE_PATTERN__": escape(force_pattern or "未识别"),
            "__IMPACT_RANGE__": escape(impact_range or "未识别"),
            "__DIRECT_SPEC_TARGETS__": escape(direct_spec_targets or "未识别"),
            "__NEXT_LEVEL_NODES_TEXT__": escape(next_level_nodes_text or "未识别"),
            "__MESSAGE_HTML__": message_html,
            "__LATEST_ANALYSIS__": latest_analysis_html,
            "__TREE_HTML__": tree_html,
            "__APP_STATE_JSON__": app_state_json,
        },
    )
    return html.encode("utf-8")


def run_node_analysis(
    project: str,
    selected_node: str,
    provider: str,
    channel: str | None = None,
) -> tuple[bool, str]:
    def _progress(msg: str) -> None:
        if channel:
            WS_BROKER.publish_text(channel, msg)

    if channel:
        WS_BROKER.publish_text(channel, f"分析开始：节点={selected_node}，provider={provider}")
    payload = load_chain_project(project)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    core_intro = str(payload.get("core_impetus_intro", "")).strip()
    strategy_text = read_text_file(project_strategy_path(project))
    prompt_script_text = read_text_file(project_ai_prompt_path(project))
    project_api_key = get_project_api_key(project, provider)
    analysis_text = analyze_node_with_ai_five_steps(
        provider_id=provider,
        project=project,
        node=selected_node,
        core_intro=core_intro,
        strategy_text=strategy_text,
        prompt_script_text=prompt_script_text,
        api_key_override=project_api_key,
        progress=_progress if channel else None,
    )
    result_path = save_analysis_result(
        project=project,
        run_id=run_id,
        provider=provider,
        node=selected_node,
        analysis_text=analysis_text,
    )
    impetus_type = extract_impetus_type(analysis_text)
    duration_estimate = extract_duration_estimate(analysis_text)
    force_pattern = extract_force_pattern(analysis_text)
    impact_range = extract_impact_range(analysis_text)
    direct_spec_targets = _extract_field(analysis_text, "direct_spec_targets", max_len=400)
    next_level_nodes = extract_next_level_nodes(analysis_text)
    added_edge_count = merge_next_level_nodes(
        payload=payload, parent_node=selected_node, children=next_level_nodes
    )
    if impetus_type:
        payload["impetus_type"] = impetus_type
    if duration_estimate:
        payload["duration_estimate"] = duration_estimate
    if force_pattern:
        payload["force_pattern"] = force_pattern
    if impact_range:
        payload["impact_market_cap_change_range_usd"] = impact_range
    if direct_spec_targets:
        payload["direct_spec_targets"] = direct_spec_targets
    payload["next_level_nodes"] = next_level_nodes
    payload["last_selected_node"] = selected_node
    task_map = payload.get("task_ai_mapping", {})
    if not isinstance(task_map, dict):
        task_map = {}
    task_map["node_speculation"] = provider
    payload["task_ai_mapping"] = task_map
    log = payload.get("analysis_log", [])
    if not isinstance(log, list):
        log = []
    log.append(
        {
            "run_id": run_id,
            "task": "node_speculation",
            "provider": provider,
            "node": selected_node,
            "impetus_type": impetus_type or "unspecified",
            "duration_estimate": duration_estimate or "unspecified",
            "force_pattern": force_pattern or "unspecified",
            "impact_market_cap_change_range_usd": impact_range or "unspecified",
            "direct_spec_targets": direct_spec_targets or "unspecified",
            "next_level_nodes": next_level_nodes,
            "added_edge_count": added_edge_count,
            "status": "success",
            "api_key_source": "project" if project_api_key else "env",
            "result_file": result_path.as_posix(),
            "at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    payload["analysis_log"] = log
    results = payload.get("analysis_results", [])
    if not isinstance(results, list):
        results = []
    results.append(
        {
            "run_id": run_id,
            "task": "node_speculation",
            "provider": provider,
            "node": selected_node,
            "impetus_type": impetus_type or "unspecified",
            "duration_estimate": duration_estimate or "unspecified",
            "force_pattern": force_pattern or "unspecified",
            "impact_market_cap_change_range_usd": impact_range or "unspecified",
            "direct_spec_targets": direct_spec_targets or "unspecified",
            "next_level_nodes": next_level_nodes,
            "added_edge_count": added_edge_count,
            "analysis_text": analysis_text,
            "api_key_source": "project" if project_api_key else "env",
            "result_file": result_path.as_posix(),
            "at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    payload["analysis_results"] = results
    save_chain_project(project, payload)
    message = (
        f"节点分析完成: {selected_node} ({provider})，"
        f"新增下级连线 {added_edge_count} 条，已保存: {result_path.as_posix()}"
    )
    if channel:
        WS_BROKER.publish_text(channel, message)
    return True, message


class UIHandler(BaseHTTPRequestHandler):
    def _send_html(self, body: bytes, status: int = HTTPStatus.OK) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, socket.timeout):
            # Client disconnected while response was being written; safe to ignore.
            return

    def _send_js(self, body: bytes, status: int = HTTPStatus.OK) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, socket.timeout):
            return

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, socket.timeout):
            return

    def _websocket_channel(self, project: str | None) -> str:
        return f"project:{project or ''}"

    def _handle_websocket(self, parsed) -> None:
        qs = parse_qs(parsed.query)
        project = (qs.get("project") or [""])[0].strip()
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing websocket key")
            return
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")).digest()
        ).decode("ascii")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        conn = self.connection
        conn.settimeout(None)
        client = _WebSocketClient(conn)
        channel = self._websocket_channel(project)
        WS_BROKER.subscribe(channel, client)
        try:
            while True:
                opcode, payload = _ws_read_frame(conn)
                if opcode == 0x8:
                    break
                if opcode == 0x9:
                    _ws_send_frame(conn, payload, opcode=0xA)
                    continue
                if opcode != 0x1:
                    continue
                try:
                    message = json.loads(payload.decode("utf-8"))
                except Exception:
                    WS_BROKER.publish_text(channel, "WS 消息解析失败")
                    continue
                if not isinstance(message, dict):
                    continue
                if message.get("action") != "analyze_node":
                    continue
                selected_node = str(message.get("selected_node", "")).strip()
                provider = str(message.get("provider", "")).strip()
                if not project or not selected_node or selected_node == "none" or not provider:
                    WS_BROKER.publish_event(
                        channel, {"type": "analysis_error", "message": "WS 分析参数无效"}
                    )
                    continue

                def _run() -> None:
                    try:
                        ok, done_message = run_node_analysis(
                            project=project,
                            selected_node=selected_node,
                            provider=provider,
                            channel=channel,
                        )
                        WS_BROKER.publish_event(
                            channel,
                            {
                                "type": "analysis_done" if ok else "analysis_error",
                                "message": done_message,
                            },
                        )
                    except Exception as exc:
                        err = f"节点分析失败: {exc}"
                        WS_BROKER.publish_text(channel, err)
                        WS_BROKER.publish_event(
                            channel, {"type": "analysis_error", "message": err}
                        )

                threading.Thread(target=_run, daemon=True).start()
        except Exception:
            pass
        finally:
            WS_BROKER.unsubscribe(channel, client)

    def _render(
        self,
        requested_project: str | None,
        requested_provider: str | None = None,
        message: str = "",
        level: str = "info",
        status: int = HTTPStatus.OK,
    ) -> None:
        projects = list_existing_projects()
        selected_project = resolve_selected_project(requested_project, projects)
        payload = load_project_view(selected_project)
        selected_provider = resolve_selected_provider(
            selected_project, payload, requested_provider
        )
        body = render_page(
            projects=projects,
            selected_project=selected_project,
            selected_provider=selected_provider,
            payload=payload,
            message=message,
            level=level,
        )
        self._send_html(body, status=status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/ws":
            self._handle_websocket(parsed)
            return
        if parsed.path == "/static/app.js":
            if not APP_JS_PATH.exists():
                self._render(
                    None, message="静态资源不存在。", level="warn", status=HTTPStatus.NOT_FOUND
                )
                return
            self._send_js(_read_text(APP_JS_PATH).encode("utf-8"))
            return
        if parsed.path != "/":
            self._render(None, message="页面不存在。", level="warn", status=HTTPStatus.NOT_FOUND)
            return
        qs = parse_qs(parsed.query)
        requested_project = (qs.get("project") or [None])[0]
        requested_provider = (qs.get("provider") or [None])[0]
        self._render(requested_project, requested_provider=requested_provider)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        ajax = (qs.get("ajax") or [""])[0] == "1"
        content_length = int(self.headers.get("Content-Length", "0"))
        body_raw = self.rfile.read(content_length).decode("utf-8")
        form = parse_qs(body_raw)

        if parsed.path == "/projects":
            project_name = (form.get("project_name") or [""])[0]
            try:
                chain_path, req_path, strategy_path, prompt_path = create_project(
                    project_name, force=False
                )
                self._render(
                    project_name.strip(),
                    message=(
                        "创建成功。"
                        f" chain: {chain_path.as_posix()} | requirements: {req_path.as_posix()}"
                        f" | strategy: {strategy_path.as_posix()} | prompt: {prompt_path.as_posix()}"
                    ),
                    level="success",
                )
            except FileExistsError as exc:
                self._render(None, message=str(exc), level="warn", status=HTTPStatus.CONFLICT)
            except ValueError as exc:
                self._render(None, message=str(exc), level="warn", status=HTTPStatus.BAD_REQUEST)
            except Exception:
                self._render(
                    None,
                    message="创建失败，请检查输入或查看服务日志。",
                    level="warn",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if parsed.path == "/save-api-key":
            project = (form.get("project") or [""])[0].strip()
            provider = (form.get("provider") or [""])[0].strip()
            api_key = (form.get("api_key") or [""])[0]
            if not project:
                self._render(None, message="请先选择项目。", level="warn", status=HTTPStatus.BAD_REQUEST)
                return
            if provider not in PROVIDERS:
                self._render(project, message="无效的 AI 提供方。", level="warn", status=HTTPStatus.BAD_REQUEST)
                return
            try:
                save_project_api_key(project, provider, api_key)
                self._render(
                    project,
                    requested_provider=provider,
                    message=f"API Key 已加密保存到项目 core: {provider}",
                    level="success",
                )
            except Exception as exc:
                self._render(
                    project,
                    requested_provider=provider,
                    message=f"保存 API Key 失败: {exc}",
                    level="warn",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if parsed.path == "/project-meta":
            project = (form.get("project") or [""])[0].strip()
            core_intro = (form.get("core_intro") or [""])[0].strip()
            if not project:
                self._render(None, message="请先选择项目。", level="warn", status=HTTPStatus.BAD_REQUEST)
                return
            try:
                payload = load_chain_project(project)
                payload["core_impetus_intro"] = core_intro
                save_chain_project(project, payload)
                self._render(project, message="项目核心推力简介已保存。", level="success")
            except Exception:
                self._render(
                    project,
                    message="保存失败，请检查项目数据文件。",
                    level="warn",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if parsed.path == "/analyze-node":
            project = (form.get("project") or [""])[0].strip()
            selected_node = (form.get("selected_node") or [""])[0].strip()
            provider = (form.get("provider") or [""])[0].strip()
            channel = self._websocket_channel(project)
            if not project:
                if ajax:
                    self._send_json(
                        {"ok": False, "message": "请先选择项目。"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                else:
                    self._render(
                        None, message="请先选择项目。", level="warn", status=HTTPStatus.BAD_REQUEST
                    )
                return
            if not selected_node or selected_node == "none":
                if ajax:
                    self._send_json(
                        {"ok": False, "message": "请先在树图中单击选择一个有效节点。"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                else:
                    self._render(
                        project,
                        requested_provider=provider,
                        message="请先在树图中单击选择一个有效节点。",
                        level="warn",
                        status=HTTPStatus.BAD_REQUEST,
                    )
                return
            try:
                _, message = run_node_analysis(
                    project=project,
                    selected_node=selected_node,
                    provider=provider,
                    channel=channel,
                )
                if ajax:
                    self._send_json({"ok": True, "message": message}, status=HTTPStatus.OK)
                else:
                    self._render(
                        project,
                        requested_provider=provider,
                        message=message,
                        level="success",
                    )
            except Exception as exc:
                message = f"节点分析失败: {exc}"
                WS_BROKER.publish_text(channel, message)
                if ajax:
                    self._send_json(
                        {"ok": False, "message": message},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                else:
                    self._render(
                        project,
                        requested_provider=provider,
                        message=message,
                        level="warn",
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
            return

        self._render(None, message="页面不存在。", level="warn", status=HTTPStatus.NOT_FOUND)


def run_ui_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), UIHandler)
    print(f"UI server running at http://{host}:{port}")
    server.serve_forever()




