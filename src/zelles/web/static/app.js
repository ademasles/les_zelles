// les_zelles web UI: no build step, no framework, talks to /api/v1.
const API = "/api/v1";
const key = new URLSearchParams(location.search).get("api_key") || localStorage.getItem("zelles_api_key") || "";
if (key) localStorage.setItem("zelles_api_key", key);
const headers = key ? { "X-API-Key": key } : {};
const withKey = (url) => (key ? `${url}${url.includes("?") ? "&" : "?"}api_key=${encodeURIComponent(key)}` : url);

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
let current = null;

async function api(path, options = {}) {
  const res = await fetch(API + path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

// ------------------------------------------------------------------ documents
async function refreshDocs() {
  const docs = await api("/documents");
  $("docs").innerHTML = docs.map((d) => `
    <li data-id="${d.id}" class="${current?.sheet.document_id === d.id ? "active" : ""}">
      <div class="name">${esc(d.title || d.filename)}</div>
      ${d.title ? `<div class="small muted">${esc(d.filename)}</div>` : ""}
      <div class="small muted">${d.status} · ${d.requirements} values · ${esc(d.model || "")}</div>
    </li>`).join("");
  document.querySelectorAll("#docs li").forEach((li) => li.addEventListener("click", () => openDoc(li.dataset.id)));
}

async function upload(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/documents`, { method: "POST", body: form, headers });
  const body = await res.json();
  if (!res.ok) return alert(body.detail || "Upload failed");
  if (body.cached) return openDoc(body.document_id);
  follow(body.job_id, body.document_id);
}

function follow(jobId, docId) {
  $("job").classList.remove("hidden");
  const source = new EventSource(withKey(`${API}/jobs/${jobId}/events`));
  source.addEventListener("progress", async (e) => {
    const ev = JSON.parse(e.data);
    if (ev.message) $("job-msg").textContent = ev.message;
    if (ev.progress != null) $("job-bar").style.width = `${Math.round(ev.progress * 100)}%`;
    if (ev.status === "done" || ev.status === "failed") {
      source.close();
      if (ev.status === "failed") $("job-msg").textContent = `Failed: ${ev.error}`;
      else { setTimeout(() => $("job").classList.add("hidden"), 800); await openDoc(docId); }
      refreshDocs();
    }
  });
  refreshDocs();
}

async function openDoc(id) {
  current = await api(`/documents/${id}`);
  const s = current.sheet;
  $("empty").classList.add("hidden");
  $("doc").classList.remove("hidden");
  $("doc-title").textContent = s.title || s.filename;
  $("doc-meta").textContent = [s.title ? s.filename : null, s.lots.join(" · ") || "No lot detected", `analysed with ${s.model}`].filter(Boolean).join(" · ");
  for (const fmt of ["xlsx", "csv", "json"]) $(`x-${fmt}`).href = withKey(`${API}/documents/${id}/export.${fmt}`);
  const verified = s.requirements.filter((r) => r.status === "verified").length;
  const cost = s.usage.cost_usd == null ? "n/a" : `$${s.usage.cost_usd.toFixed(4)}`;
  $("stats").innerHTML = [
    ["Requirements", s.requirements.length], ["Verified", `${verified}/${s.requirements.length}`],
    ["Field coverage", `${Math.round(current.coverage * 100)}%`], ["Conflicts", current.conflicts.length],
    ["LLM cost", cost], ["Time", `${s.usage.seconds.toFixed(1)} s`],
  ].map(([k, v]) => `<div class="stat"><span class="small muted">${k}</span><b>${v}</b></div>`).join("");
  $("summary").classList.toggle("hidden", !s.summary);
  $("summary").textContent = s.summary || "";
  renderSheet();
  refreshDocs();
  graphLoaded = false;
  if (!$("tab-questions").classList.contains("hidden")) loadQuestions();
  if (!$("tab-graph").classList.contains("hidden")) loadGraph();
}

// ------------------------------------------------------------------ spec sheet
const CATEGORY_LABELS = {
  materials: "Materials and finishes", glazing: "Glazing", thermal: "Thermal and solar", weather_tightness: "Weather tightness (AEV)",
  acoustics: "Acoustics", security: "Security and hardware", equipment: "Shutters and ventilation", accessibility: "Accessibility",
  installation: "Installation", compliance: "Standards, labels and regulations",
};
const FIELD_CATEGORY = {
  frame_material: "materials", opening_type: "materials", profile_system: "materials", color: "materials", finish: "materials",
  glazing_composition: "glazing", glazing_type: "glazing", safety_glazing: "glazing", spacer: "glazing",
  uw: "thermal", ug: "thermal", ujn: "thermal", sw: "thermal", tlw: "thermal", aev: "weather_tightness", acoustic: "acoustics",
  security_class: "security", hardware: "security", shutters: "equipment", air_inlets: "equipment",
  accessibility: "accessibility", installation: "installation", standards: "compliance", certifications: "compliance", regulation: "compliance",
};

function renderSheet() {
  const q = $("filter").value.toLowerCase();
  const onlyVerified = $("only-verified").checked;
  const groups = {};
  current.sheet.requirements.forEach((r, i) => {
    if (onlyVerified && r.status !== "verified") return;
    const hay = `${r.field} ${r.value} ${r.scope || ""} ${r.citation?.quote || ""}`.toLowerCase();
    if (q && !hay.includes(q)) return;
    (groups[FIELD_CATEGORY[r.field]] ||= []).push([r, i]);
  });
  $("sheet").innerHTML = Object.keys(CATEGORY_LABELS).filter((c) => groups[c]).map((c) => `
    <div class="category"><h4>${CATEGORY_LABELS[c]}</h4>
      <table><thead><tr><th>Field</th><th>Value</th><th>Applies to</th><th>Source</th><th>Status</th><th></th></tr></thead>
      <tbody>${groups[c].map(([r, i]) => `
        <tr class="req" data-i="${i}">
          <td>${esc(r.field.replaceAll("_", " "))}</td><td><b>${esc(r.value)}</b></td><td>${esc(r.scope || "")}</td>
          <td class="small">${esc(r.citation?.locator || "")}</td>
          <td><span class="badge ${r.status}">${r.status}</span><span class="src">${r.source} · ${Math.round(r.confidence * 100)}%</span></td>
          <td><button class="fb" data-v="correct" data-i="${i}" title="Correct">👍</button><button class="fb" data-v="incorrect" data-i="${i}" title="Wrong">👎</button></td>
        </tr>`).join("")}</tbody></table></div>`).join("") || `<p class="muted">No requirement matches.</p>`;
  document.querySelectorAll("tr.req").forEach((tr) => tr.addEventListener("click", (e) => {
    if (e.target.classList.contains("fb")) return;
    const r = current.sheet.requirements[tr.dataset.i];
    showSource(r.citation, r.notes);
  }));
  document.querySelectorAll(".fb").forEach((b) => b.addEventListener("click", () => sendFeedback(b.dataset.i, b.dataset.v, b)));
}

async function sendFeedback(i, verdict, button) {
  const r = current.sheet.requirements[i];
  await api(`/documents/${current.sheet.document_id}/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field: r.field, value: r.value, verdict, chunk_id: r.citation?.chunk_id }),
  });
  button.parentElement.innerHTML = `<span class="small muted">thanks</span>`;
}

async function showSource(citation, notes = []) {
  if (!citation) return;
  const id = current.sheet.document_id;
  $("viewer").classList.remove("hidden");
  $("viewer-title").textContent = citation.locator || citation.chunk_id;
  $("viewer-quote").textContent = citation.quote;
  $("viewer-notes").textContent = [`match ${Math.round(citation.match_score * 100)}%`, ...notes].join(" · ");
  if (current.paginated && citation.page) {
    $("viewer-img").classList.remove("hidden");
    $("viewer-text").classList.add("hidden");
    $("viewer-img").src = withKey(`${API}/documents/${id}/pages/${citation.page}.png?chunk_id=${citation.chunk_id}&quote=${encodeURIComponent(citation.quote.slice(0, 200))}`);
  } else {
    const chunk = await api(`/documents/${id}/chunks/${citation.chunk_id}`);
    $("viewer-img").classList.add("hidden");
    $("viewer-text").classList.remove("hidden");
    $("viewer-text").textContent = chunk.text;
  }
}

// ------------------------------------------------------------------ ask, product, questions
$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = $("question").value;
  $("answer").innerHTML = `<p class="muted">Thinking…</p>`;
  try {
    if ($("use-agent").checked) {
      const res = await api("/agent", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, document_id: current.sheet.document_id }) });
      $("answer").innerHTML = `<div class="answer">${esc(res.answer)}</div>
        <details class="small"><summary>${res.steps.length} steps</summary>${res.steps.map((s) => `<div>· ${esc(s.action)} ${esc(JSON.stringify(s.arguments))}</div>`).join("")}</details>`;
      return;
    }
    const res = await api(`/documents/${current.sheet.document_id}/ask`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
    $("answer").innerHTML = `<div class="answer">${esc(res.answer)}
      ${res.citations.map((c, i) => `<a class="cite" data-i="${i}">${c.match_score >= 0.88 ? "✓" : "?"} [${esc(c.chunk_id)}] ${esc(c.locator)}</a>`).join("")}</div>`;
    document.querySelectorAll(".cite").forEach((a) => a.addEventListener("click", () => showSource(res.citations[a.dataset.i])));
  } catch (err) { $("answer").innerHTML = `<p class="badge invalid">${esc(err.message)}</p>`; }
});

$("product-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  const product = { name: data.name, colors: data.colors ? data.colors.split(",").map((c) => c.trim()) : [] };
  for (const k of ["frame_material", "aev", "security_class"]) if (data[k]) product[k] = data[k];
  for (const k of ["uw", "ug", "sw", "tlw", "acoustic_db"]) if (data[k]) product[k] = Number(data[k]);
  const checks = await api(`/documents/${current.sheet.document_id}/check-product`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(product) });
  $("product-result").innerHTML = checks.length ? `<table><thead><tr><th>Field</th><th>Required</th><th>Applies to</th><th>Offered</th><th>Verdict</th><th>Why</th></tr></thead><tbody>
    ${checks.map((c) => `<tr><td>${esc(c.field)}</td><td>${esc(c.required)}</td><td>${esc(c.scope || "")}</td><td>${esc(c.offered || "")}</td>
      <td><span class="badge ${c.verdict}">${c.verdict}</span></td><td class="small">${esc(c.reason)}</td></tr>`).join("")}</tbody></table>`
    : `<p class="muted">Nothing to compare: fill in some performances.</p>`;
});

async function loadQuestions() {
  const qs = await api(`/documents/${current.sheet.document_id}/clarifications`);
  $("questions").innerHTML = qs.length
    ? `<p class="muted small">Draft questions for the project owner, in French, ready to paste into a request for clarification.</p>` +
      qs.map((q) => `<div class="question"><span class="badge ${q.reason === "missing" ? "unverified" : "invalid"}">${q.reason}</span> ${esc(q.question)}</div>`).join("")
    : `<p class="muted">No missing or conflicting requirement detected.</p>`;
}

// ------------------------------------------------------------------ graph (small force layout)
let graphLoaded = false;
async function loadGraph() {
  if (graphLoaded) return;
  graphLoaded = true;
  const data = await api(`/documents/${current.sheet.document_id}/graph`);
  drawGraph(data);
}

function drawGraph({ nodes, links }) {
  const canvas = $("graph");
  const ratio = window.devicePixelRatio || 1;
  const W = canvas.clientWidth, H = 560;
  canvas.width = W * ratio; canvas.height = H * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const colors = { Document: "#2f6fde", Lot: "#7c4dff", Section: "#5c6bc0", Passage: "#9aa5b1", Requirement: "#1f8a4c",
    Standard: "#d97706", Certification: "#c2410c", Material: "#0891b2", Topic: "#db2777" };
  const byId = Object.fromEntries(nodes.map((n, i) => [n.id, Object.assign(n, { x: W / 2 + Math.cos(i) * 200 * Math.random(), y: H / 2 + Math.sin(i) * 200 * Math.random(), vx: 0, vy: 0 })]));
  const edges = links.map((l) => [byId[l.source], byId[l.target], l.type]).filter(([a, b]) => a && b);
  let dragging = null, ticks = 0;
  function step() {
    for (const a of nodes) for (const b of nodes) {
      if (a === b) continue;
      const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 0.01;
      if (d2 < 40000) { const f = 120 / d2; a.vx += dx * f; a.vy += dy * f; }
    }
    for (const [a, b] of edges) {
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1, f = (d - 50) * 0.01;
      a.vx += (dx / d) * f; a.vy += (dy / d) * f; b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
    }
    for (const n of nodes) {
      if (n === dragging) continue;
      n.vx += (W / 2 - n.x) * 0.002; n.vy += (H / 2 - n.y) * 0.002;
      n.x = Math.max(8, Math.min(W - 8, n.x + (n.vx *= 0.82))); n.y = Math.max(8, Math.min(H - 8, n.y + (n.vy *= 0.82)));
    }
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(128,128,128,.25)";
    for (const [a, b, t] of edges) {
      ctx.strokeStyle = t === "CONFLICTS_WITH" ? "#c53030" : t === "REFERS_TO" ? "#7c4dff" : "rgba(128,128,128,.25)";
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    for (const n of nodes) {
      ctx.fillStyle = colors[n.type] || "#888";
      ctx.beginPath(); ctx.arc(n.x, n.y, n.type === "Passage" ? 3 : 6, 0, Math.PI * 2); ctx.fill();
      if (["Lot", "Standard", "Topic", "Material", "Certification"].includes(n.type)) {
        ctx.fillStyle = getComputedStyle(document.body).color; ctx.font = "11px sans-serif"; ctx.fillText(n.label.slice(0, 28), n.x + 8, n.y + 4);
      }
    }
  }
  (function loop() { if (ticks++ < 400 || dragging) step(); draw(); requestAnimationFrame(loop); })();
  const pick = (e) => { const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    return nodes.find((n) => (n.x - x) ** 2 + (n.y - y) ** 2 < 64); };
  canvas.onmousedown = (e) => { dragging = pick(e); if (dragging) showNode(dragging); };
  canvas.onmousemove = (e) => { if (!dragging) return; const r = canvas.getBoundingClientRect(); dragging.x = e.clientX - r.left; dragging.y = e.clientY - r.top; };
  canvas.onmouseup = () => { dragging = null; ticks = 300; };
  function showNode(n) {
    const rel = edges.filter(([a, b]) => a === n || b === n).map(([a, b, t]) => `${t} → ${esc((a === n ? b : a).label)}`);
    $("graph-detail").innerHTML = `<b>${esc(n.type)}</b>: ${esc(n.label)}<br>${rel.slice(0, 12).join("<br>")}`;
  }
  const legend = Object.entries(colors).map(([k, c]) => `<span style="color:${c}">●</span> ${k}`).join("  ");
  $("graph-detail").innerHTML = `<span class="muted">${legend}</span>`;
}

// ------------------------------------------------------------------ wiring
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== `tab-${b.dataset.tab}`));
  if (b.dataset.tab === "questions") loadQuestions();
  if (b.dataset.tab === "graph") loadGraph();
}));
$("filter").addEventListener("input", renderSheet);
$("only-verified").addEventListener("change", renderSheet);
$("viewer-close").addEventListener("click", () => $("viewer").classList.add("hidden"));
$("file").addEventListener("change", (e) => e.target.files[0] && upload(e.target.files[0]));
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); });

api("/info").then((i) => { $("engine").textContent = `model: ${i.llm} · embeddings: ${i.embeddings} · v${i.version}`; }).catch(() => {});
refreshDocs().catch(() => {});
