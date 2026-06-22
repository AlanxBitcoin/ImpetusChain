(function () {
  const state = window.IMPETUS_APP_STATE || {};
  const analysisByNode = state.analysisByNode || {};
  const lastSelectedNode = state.lastSelectedNode || "";
  const projectName = state.projectName || "";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const mindmap = document.querySelector(".mindmap");
  const svg = document.querySelector(".link-layer");
  const toggles = document.querySelectorAll(".branch-toggle");
  const settingsModal = document.getElementById("settings-modal");
  const openSettings = document.getElementById("open-settings");
  const closeSettings = document.getElementById("close-settings");
  const analysisBox = document.getElementById("analysis-box");
  const apiLogBox = document.getElementById("api-log-box");
  const analyzeForm = document.getElementById("analyze-form");
  let ws = null;

  function appendApiLog(text) {
    if (!apiLogBox) return;
    const ts = new Date().toLocaleTimeString();
    apiLogBox.textContent += `\n[${ts}] ${text}`;
    apiLogBox.scrollTop = apiLogBox.scrollHeight;
  }

  function connectWs() {
    if (!projectName || !apiLogBox) return;
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${scheme}://${window.location.host}/ws?project=${encodeURIComponent(projectName)}`;
    ws = new WebSocket(url);
    ws.addEventListener("open", () => appendApiLog("WebSocket 已连接"));
    ws.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload && payload.type === "analysis_done") {
          appendApiLog(payload.message || "分析完成");
          window.location.reload();
          return;
        }
        if (payload && payload.type === "analysis_error") {
          appendApiLog(payload.message || "分析失败");
          return;
        }
        if (payload && payload.text) appendApiLog(payload.text);
      } catch {
        appendApiLog(String(event.data || ""));
      }
    });
    ws.addEventListener("close", () => appendApiLog("WebSocket 已断开"));
    ws.addEventListener("error", () => appendApiLog("WebSocket 连接错误"));
  }

  function setSettingsOpen(open) {
    if (!settingsModal) return;
    settingsModal.classList.toggle("open", open);
    settingsModal.setAttribute("aria-hidden", open ? "false" : "true");
  }

  if (openSettings) openSettings.addEventListener("click", () => setSettingsOpen(true));
  if (closeSettings) closeSettings.addEventListener("click", () => setSettingsOpen(false));
  if (settingsModal) {
    settingsModal.addEventListener("click", (e) => {
      if (e.target === settingsModal) setSettingsOpen(false);
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setSettingsOpen(false);
  });

  function edgePoint(rect, side) {
    if (side === "left") return { x: rect.left, y: rect.top + rect.height / 2 };
    return { x: rect.right, y: rect.top + rect.height / 2 };
  }

  function drawCurve(from, to, cssClass) {
    if (!svg || !mindmap) return;
    const mapRect = mindmap.getBoundingClientRect();
    const x1 = from.x - mapRect.left;
    const y1 = from.y - mapRect.top;
    const x2 = to.x - mapRect.left;
    const y2 = to.y - mapRect.top;
    const dx = Math.max(24, Math.abs(x2 - x1) * 0.5);
    const c1x = x1 + (x2 >= x1 ? dx : -dx);
    const c2x = x2 - (x2 >= x1 ? dx : -dx);
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", `M ${x1} ${y1} C ${c1x} ${y1}, ${c2x} ${y2}, ${x2} ${y2}`);
    path.setAttribute("class", cssClass);
    svg.appendChild(path);
  }

  function redrawLinks() {
    if (!svg || !mindmap) return;
    svg.innerHTML = "";
    const center = document.getElementById("center-node");
    if (!center) return;
    const centerRect = center.getBoundingClientRect();
    document.querySelectorAll(".branch-toggle").forEach((l1) => {
      const side = l1.getAttribute("data-side") === "left" ? "left" : "right";
      const l1Rect = l1.getBoundingClientRect();
      drawCurve(
        edgePoint(centerRect, side),
        edgePoint(l1Rect, side === "left" ? "right" : "left"),
        "link-root-l1"
      );
      const targetId = l1.getAttribute("data-target");
      const l2List = targetId ? document.getElementById(targetId) : null;
      if (!l2List || l2List.classList.contains("collapsed")) return;
      l2List.querySelectorAll(".l2-node").forEach((l2) => {
        const l2Rect = l2.getBoundingClientRect();
        drawCurve(
          edgePoint(l1Rect, side === "left" ? "right" : "left"),
          edgePoint(l2Rect, side === "left" ? "right" : "left"),
          "link-l1-l2"
        );
      });
    });
  }

  function setBranchState(target, expanded) {
    if (!target) return;
    target.classList.toggle("collapsed", !expanded);
    redrawLinks();
  }

  function setSelectedNode(node) {
    if (!node) return;
    document.querySelectorAll(".node-selected").forEach((el) => el.classList.remove("node-selected"));
    node.classList.add("node-selected");
    const nodeName = node.getAttribute("data-node") || node.textContent.trim();
    const input = document.getElementById("selected_node_input");
    const label = document.getElementById("selected_node_label");
    if (input) input.value = nodeName;
    if (label) label.textContent = `当前选中: ${nodeName}`;
    if (analysisBox) analysisBox.textContent = analysisByNode[nodeName] || "该节点暂无分析结果";
  }

  document.querySelectorAll("#center-node, .branch-toggle, .l2-node").forEach((node) => {
    node.addEventListener("click", () => setSelectedNode(node));
  });

  const defaultNode = document.getElementById("center-node");
  if (lastSelectedNode) {
    const escaped = window.CSS && window.CSS.escape
      ? window.CSS.escape(lastSelectedNode)
      : lastSelectedNode.replace(/["\\]/g, "\\$&");
    const target = document.querySelector(`[data-node="${escaped}"]`);
    if (target) setSelectedNode(target);
    else if (defaultNode) setSelectedNode(defaultNode);
  } else if (defaultNode) {
    setSelectedNode(defaultNode);
  }

  toggles.forEach((btn) => {
    btn.addEventListener("dblclick", () => {
      const id = btn.getAttribute("data-target");
      const target = document.getElementById(id);
      if (!target) return;
      const isExpanded = btn.getAttribute("aria-expanded") !== "false";
      btn.setAttribute("aria-expanded", String(!isExpanded));
      setBranchState(target, !isExpanded);
    });
  });

  if (analyzeForm) {
    analyzeForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        appendApiLog("WebSocket 未连接，无法发起分析");
        return;
      }
      const selectedInput = document.getElementById("selected_node_input");
      const selectedNode = selectedInput ? String(selectedInput.value || "").trim() : "";
      if (!selectedNode || selectedNode === "none") {
        appendApiLog("请先单击选择有效节点");
        return;
      }
      appendApiLog("开始分析节点...");
      const providerSelect = analyzeForm.querySelector('select[name="provider"]');
      const provider = providerSelect ? String(providerSelect.value || "").trim() : "";
      ws.send(
        JSON.stringify({
          action: "analyze_node",
          selected_node: selectedNode,
          provider: provider,
        })
      );
    });
  }

  connectWs();
  window.addEventListener("resize", redrawLinks);
  window.requestAnimationFrame(redrawLinks);
})();
