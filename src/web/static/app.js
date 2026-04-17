// Minimal vanilla-JS node editor for Sparklehoof.
//
// Graph model:
//   nodes: [{ id, class, module, display_name, position:{x,y},
//             params:{name:value}, ports:{inputs,outputs}, el, previewEl }]
//   links: [{ src:nodeId, srcOut:idx, dst:nodeId, dstIn:idx, pathEl }]
//
// The graph is rendered by appending one <div class="node"> per node to
// #canvas and one <path> per link to the #links SVG overlay. Connections
// are drawn as cubic Béziers between port centers.

const state = {
  palette: {},        // section → [nodeType]
  typesByClass: {},   // className → nodeType descriptor
  nodes: new Map(),   // id → node
  links: [],          // [{src, srcOut, dst, dstIn, pathEl}]
  nextId: 1,
  drag: null,         // current interaction (node-drag / link-drag)
};

const canvas = document.getElementById("canvas");
const linksSvg = document.getElementById("links");
const statusEl = document.getElementById("status");
const flowSelect = document.getElementById("flow-select");
const flowName = document.getElementById("flow-name");

function setStatus(msg, kind) {
  statusEl.textContent = msg;
  statusEl.className = kind || "";
}

// ── API ───────────────────────────────────────────────────────────────────

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

async function loadPalette() {
  const data = await api("/api/nodes");
  state.palette = data.sections;
  state.typesByClass = {};
  const list = document.getElementById("palette-list");
  list.innerHTML = "";
  for (const [section, items] of Object.entries(data.sections)) {
    const sect = document.createElement("div");
    sect.className = "palette-section";
    const title = document.createElement("div");
    title.className = "palette-section-title";
    title.textContent = section;
    sect.appendChild(title);
    for (const t of items) {
      state.typesByClass[t.class] = t;
      const el = document.createElement("div");
      el.className = "palette-item";
      el.textContent = t.display_name;
      el.addEventListener("click", () => addNode(t, { x: 200, y: 200 }));
      sect.appendChild(el);
    }
    list.appendChild(sect);
  }
}

async function loadFlowList() {
  const data = await api("/api/flows");
  flowSelect.innerHTML = "";
  for (const name of data.flows) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    flowSelect.appendChild(opt);
  }
}

// ── Graph mutation ────────────────────────────────────────────────────────

function addNode(type, pos, existing) {
  const id = existing?.id ?? state.nextId++;
  if (existing?.id >= state.nextId) state.nextId = existing.id + 1;

  const params = {};
  for (const p of type.params) {
    params[p.name] = existing?.params?.[p.name] ?? p.default;
  }

  const node = {
    id,
    class: type.class,
    module: type.module,
    display_name: type.display_name,
    position: { x: pos.x, y: pos.y },
    params,
    ports: type.ports,
    paramDefs: type.params,
    el: null,
    previewEl: null,
  };
  renderNode(node);
  state.nodes.set(id, node);
  return node;
}

function removeNode(node) {
  state.links = state.links.filter(l => {
    if (l.src === node.id || l.dst === node.id) {
      l.pathEl.remove();
      return false;
    }
    return true;
  });
  node.el.remove();
  state.nodes.delete(node.id);
}

function addLink(src, srcOut, dst, dstIn) {
  if (src === dst) return;
  // Enforce one connection per input.
  state.links = state.links.filter(l => {
    if (l.dst === dst && l.dstIn === dstIn) {
      l.pathEl.remove();
      return false;
    }
    return true;
  });
  const pathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
  linksSvg.appendChild(pathEl);
  state.links.push({ src, srcOut, dst, dstIn, pathEl });
  redrawLinks();
}

function redrawLinks() {
  for (const link of state.links) {
    const src = state.nodes.get(link.src);
    const dst = state.nodes.get(link.dst);
    if (!src || !dst) continue;
    const a = portCenter(src, "output", link.srcOut);
    const b = portCenter(dst, "input", link.dstIn);
    const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
    link.pathEl.setAttribute("d",
      `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`);
  }
}

function portCenter(node, side, idx) {
  const dot = node.el.querySelector(
    `.port.${side}[data-idx="${idx}"] .port-dot`);
  if (!dot) return { x: node.position.x, y: node.position.y };
  const dotRect = dot.getBoundingClientRect();
  const wrapRect = canvas.parentElement.getBoundingClientRect();
  return {
    x: dotRect.left + dotRect.width / 2 - wrapRect.left + canvas.parentElement.scrollLeft,
    y: dotRect.top + dotRect.height / 2 - wrapRect.top + canvas.parentElement.scrollTop,
  };
}

// ── Rendering ─────────────────────────────────────────────────────────────

function renderNode(node) {
  const el = document.createElement("div");
  el.className = "node";
  el.style.left = node.position.x + "px";
  el.style.top = node.position.y + "px";

  const header = document.createElement("div");
  header.className = "node-header";
  const title = document.createElement("span");
  title.textContent = node.display_name;
  const close = document.createElement("span");
  close.className = "close";
  close.textContent = "×";
  close.addEventListener("click", e => {
    e.stopPropagation();
    removeNode(node);
    redrawLinks();
  });
  header.appendChild(title);
  header.appendChild(close);
  el.appendChild(header);

  const body = document.createElement("div");
  body.className = "node-body";

  const ports = document.createElement("div");
  ports.className = "node-ports";
  const inCol = document.createElement("div");
  inCol.className = "port-col";
  const outCol = document.createElement("div");
  outCol.className = "port-col";
  node.ports.inputs.forEach((p, idx) => inCol.appendChild(makePort(node, "input", idx, p)));
  node.ports.outputs.forEach((p, idx) => outCol.appendChild(makePort(node, "output", idx, p)));
  ports.appendChild(inCol);
  ports.appendChild(outCol);
  body.appendChild(ports);

  for (const def of node.paramDefs) {
    body.appendChild(makeParam(node, def));
  }

  const preview = document.createElement("img");
  preview.className = "node-preview";
  preview.style.display = "none";
  body.appendChild(preview);
  node.previewEl = preview;

  el.appendChild(body);
  canvas.appendChild(el);
  node.el = el;

  // Drag to move
  header.addEventListener("mousedown", e => {
    if (e.target === close) return;
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const origX = node.position.x;
    const origY = node.position.y;
    state.drag = {
      kind: "node",
      move(e) {
        node.position.x = origX + (e.clientX - startX);
        node.position.y = origY + (e.clientY - startY);
        el.style.left = node.position.x + "px";
        el.style.top = node.position.y + "px";
        redrawLinks();
      },
      end() { state.drag = null; },
    };
  });
}

function makePort(node, side, idx, portInfo) {
  const row = document.createElement("div");
  row.className = `port ${side}`;
  row.dataset.idx = idx;
  const dot = document.createElement("div");
  dot.className = "port-dot";
  const label = document.createElement("span");
  label.textContent = portInfo.name;
  row.appendChild(dot);
  row.appendChild(label);

  dot.addEventListener("mousedown", e => {
    e.preventDefault();
    e.stopPropagation();
    const tempPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    tempPath.classList.add("temp");
    linksSvg.appendChild(tempPath);
    state.drag = {
      kind: "link",
      fromNode: node,
      fromSide: side,
      fromIdx: idx,
      move(e) {
        const wrapRect = canvas.parentElement.getBoundingClientRect();
        const scrollX = canvas.parentElement.scrollLeft;
        const scrollY = canvas.parentElement.scrollTop;
        const a = portCenter(node, side, idx);
        const bx = e.clientX - wrapRect.left + scrollX;
        const by = e.clientY - wrapRect.top + scrollY;
        const dx = Math.max(40, Math.abs(bx - a.x) * 0.5);
        tempPath.setAttribute("d",
          `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${bx - dx} ${by}, ${bx} ${by}`);
      },
      end(e) {
        tempPath.remove();
        const target = document.elementFromPoint(e.clientX, e.clientY);
        if (target && target.classList.contains("port-dot")) {
          const row = target.closest(".port");
          const otherSide = row.classList.contains("input") ? "input" : "output";
          const otherNodeEl = target.closest(".node");
          const otherNode = [...state.nodes.values()].find(n => n.el === otherNodeEl);
          const otherIdx = parseInt(row.dataset.idx, 10);
          if (otherNode && otherSide !== side) {
            if (side === "output") {
              addLink(node.id, idx, otherNode.id, otherIdx);
            } else {
              addLink(otherNode.id, otherIdx, node.id, idx);
            }
          }
        }
        state.drag = null;
      },
    };
  });
  return row;
}

function makeParam(node, def) {
  const row = document.createElement("div");
  row.className = "param";
  const label = document.createElement("label");
  label.textContent = def.name;
  row.appendChild(label);

  let input;
  if (def.type === "ENUM" && def.choices) {
    input = document.createElement("select");
    for (const choice of def.choices) {
      const opt = document.createElement("option");
      opt.value = JSON.stringify(choice.value);
      opt.textContent = choice.name;
      input.appendChild(opt);
    }
    input.value = JSON.stringify(node.params[def.name]);
    input.addEventListener("change", () => {
      node.params[def.name] = JSON.parse(input.value);
    });
  } else if (def.type === "BOOL") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = !!node.params[def.name];
    input.addEventListener("change", () => { node.params[def.name] = input.checked; });
  } else if (def.type === "INT" || def.type === "FLOAT") {
    input = document.createElement("input");
    input.type = "number";
    if (def.type === "FLOAT") input.step = "any";
    input.value = node.params[def.name] ?? 0;
    input.addEventListener("change", () => {
      const v = input.value === "" ? null : Number(input.value);
      node.params[def.name] = v;
    });
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.value = node.params[def.name] ?? "";
    input.addEventListener("change", () => { node.params[def.name] = input.value; });
  }
  row.appendChild(input);
  return row;
}

// ── Interaction glue ──────────────────────────────────────────────────────

window.addEventListener("mousemove", e => {
  if (state.drag) state.drag.move(e);
});
window.addEventListener("mouseup", e => {
  if (state.drag) state.drag.end(e);
});

// ── Flow save / load / run ────────────────────────────────────────────────

function clearGraph() {
  for (const node of [...state.nodes.values()]) removeNode(node);
  state.links = [];
  state.nextId = 1;
}

function serializeGraph() {
  const nodes = [...state.nodes.values()];
  const idToIdx = new Map(nodes.map((n, i) => [n.id, i]));
  return {
    version: 1,
    name: flowName.value || "Untitled_flow",
    nodes: nodes.map((n, i) => ({
      id: i,
      module: n.module,
      class: n.class,
      position: [n.position.x, n.position.y],
      params: n.params,
    })),
    connections: state.links.map(l => ({
      src_node: idToIdx.get(l.src),
      src_output: l.srcOut,
      dst_node: idToIdx.get(l.dst),
      dst_input: l.dstIn,
    })),
  };
}

function loadGraphFromPayload(payload) {
  clearGraph();
  flowName.value = payload.name || "";
  const idxToNode = new Map();
  for (const entry of payload.nodes || []) {
    const type = state.typesByClass[entry.class];
    if (!type) {
      setStatus(`Unknown node type: ${entry.class}`, "err");
      continue;
    }
    const node = addNode(
      type,
      { x: entry.position?.[0] ?? 0, y: entry.position?.[1] ?? 0 },
      { id: entry.id, params: entry.params },
    );
    idxToNode.set(entry.id, node);
  }
  for (const c of payload.connections || []) {
    const s = idxToNode.get(c.src_node);
    const d = idxToNode.get(c.dst_node);
    if (s && d) addLink(s.id, c.src_output, d.id, c.dst_input);
  }
  redrawLinks();
}

document.getElementById("btn-clear").addEventListener("click", clearGraph);

document.getElementById("btn-load").addEventListener("click", async () => {
  const name = flowSelect.value;
  if (!name) return;
  try {
    const payload = await api(`/api/flows/${encodeURIComponent(name)}`);
    flowName.value = name;
    loadGraphFromPayload(payload);
    setStatus(`Loaded ${name}`, "ok");
  } catch (err) {
    setStatus(err.message, "err");
  }
});

document.getElementById("btn-save").addEventListener("click", async () => {
  const name = (flowName.value || "").trim();
  if (!name) { setStatus("Enter a flow name first", "err"); return; }
  try {
    await api(`/api/flows/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serializeGraph()),
    });
    setStatus(`Saved ${name}`, "ok");
    await loadFlowList();
  } catch (err) {
    setStatus(err.message, "err");
  }
});

document.getElementById("btn-run").addEventListener("click", async () => {
  setStatus("Running…");
  try {
    const data = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serializeGraph()),
    });
    for (const node of state.nodes.values()) {
      node.previewEl.style.display = "none";
      node.previewEl.src = "";
    }
    const nodes = [...state.nodes.values()];
    for (const [idxStr, previews] of Object.entries(data.previews || {})) {
      const node = nodes[Number(idxStr)];
      if (!node || !previews.length) continue;
      node.previewEl.src = "data:image/png;base64," + previews[0].png_b64;
      node.previewEl.style.display = "block";
    }
    setStatus("Run complete", "ok");
  } catch (err) {
    setStatus(err.message, "err");
  }
});

// ── Bootstrap ─────────────────────────────────────────────────────────────

(async () => {
  try {
    await loadPalette();
    await loadFlowList();
    setStatus("Ready", "ok");
  } catch (err) {
    setStatus("Failed to load: " + err.message, "err");
  }
})();
