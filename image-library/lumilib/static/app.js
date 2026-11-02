"use strict";

const $ = (id) => document.getElementById(id);
const PAGE = 120;
const state = { q: "", offset: 0, total: 0, current: null, polling: null, jobWasRunning: false };

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) node.setAttribute(k, v);
  }
  for (const c of children) if (c) node.append(c);
  return node;
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function fmtSize(bytes) {
  if (!bytes) return "";
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function fmtDate(iso) {
  return iso ? iso.slice(0, 16).replace("T", " ") : "";
}

// ---- 搜尋 ----
async function runSearch(q, append = false) {
  state.q = q;
  if (!append) state.offset = 0;
  const params = new URLSearchParams({ q, limit: PAGE, offset: state.offset });
  if ($("semantic").checked) params.set("semantic", "1");
  const data = await api(`/api/search?${params}`);
  state.total = data.total;
  const grid = $("grid");
  if (!append) grid.replaceChildren();
  for (const r of data.results) grid.append(card(r));
  state.offset += data.results.length;
  $("more").hidden = state.offset >= state.total;
  $("summary").textContent = q
    ? `「${q}」找到 ${data.total} 張${data.mode === "hybrid" ? "（含語意相近）" : ""}`
    : `最近的照片，共 ${data.total} 張`;
  $("warning").hidden = !data.warning;
  $("warning").textContent = data.warning || "";
  const hash = q ? `#q=${encodeURIComponent(q)}` : "#";
  if (location.hash !== hash) history.replaceState(null, "", hash || "#");
}

function card(r) {
  const tags = [...r.user_tags, ...r.tags].slice(0, 6).join("、");
  const img = el("img", { loading: "lazy", alt: r.description || r.filename, src: `/thumb/${r.id}` });
  img.addEventListener("error", () => img.replaceWith(el("span", { class: "muted small", text: "無縮圖" })));
  const badge = r.status === "missing" ? "檔案遺失或硬碟未連接"
    : r.error && !r.analyzed ? "分析失敗"
    : !r.analyzed ? "待分析"
    : r.match === "semantic" ? "語意相近" : "";
  return el("button", {
    type: "button",
    class: `card${r.status === "missing" ? " missing" : ""}`,
    title: r.path,
    onclick: () => openDetail(r.id),
  },
    el("div", { class: "thumb" }, img),
    el("div", { class: "cap" },
      el("div", { class: "name", text: r.filename }),
      el("div", { class: "desc", text: r.description || tags || fmtDate(r.taken_at) }),
      badge ? el("div", { class: "badge", text: badge }) : null,
    ),
  );
}

// ---- 詳細資料 ----
async function openDetail(id) {
  const d = await api(`/api/image/${id}`);
  state.current = d;
  $("d-img").src = `/preview/${id}`;
  $("d-img").alt = d.description || d.filename;
  $("d-name").textContent = d.filename;
  $("d-path").textContent = d.path;
  $("d-desc").textContent = d.description || (d.error ? "" : "尚未分析");
  const status = !d.exists ? "目前找不到這個檔案：可能硬碟未連接、已被移動或刪除。重新掃描可以找回搬移過的檔案。"
    : d.error && !d.analyzed_at ? `分析失敗：${d.error}` : "";
  $("d-status").hidden = !status;
  $("d-status").textContent = status;
  $("d-reveal").disabled = $("d-open").disabled = !d.exists;

  const tagBox = $("d-tags");
  tagBox.replaceChildren();
  for (const t of d.user_tags) tagBox.append(tagButton(t, true));
  for (const t of d.tags) tagBox.append(tagButton(t, false));
  $("d-user-tags").value = d.user_tags.join(", ");
  $("d-note").value = d.note || "";
  $("d-saved").textContent = "";

  const meta = [
    ["拍攝時間", fmtDate(d.taken_at)],
    ["尺寸", d.width ? `${d.width} × ${d.height}` : ""],
    ["檔案大小", fmtSize(d.size)],
    ["相機", d.camera],
    ["鏡頭", d.lens],
    ["GPS", d.lat != null ? `${d.lat}, ${d.lon}` : ""],
    ["場景", d.scene],
    ["物品", (d.objects || []).join("、")],
    ["圖中文字", d.ocr_text],
    ["資料夾", d.root],
    ["分析模型", d.model ? `${d.model}（${fmtDate(d.analyzed_at)}）` : ""],
  ];
  const dl = $("d-meta");
  dl.replaceChildren();
  for (const [k, v] of meta) if (v) dl.append(el("dt", { text: k }), el("dd", { text: v }));
  if (!$("detail").open) $("detail").showModal();
}

function tagButton(tag, user) {
  return el("button", {
    type: "button",
    class: `chip${user ? " user" : ""}`,
    text: tag,
    title: `搜尋「${tag}」`,
    onclick: () => { $("detail").close(); setQuery(`tag:${quoteIfNeeded(tag)}`); },
  });
}

function quoteIfNeeded(s) {
  return /\s/.test(s) ? `"${s}"` : s;
}

async function saveDetail() {
  const d = state.current;
  if (!d) return;
  try {
    await api(`/api/image/${d.id}`, { user_tags: $("d-user-tags").value, note: $("d-note").value });
    await openDetail(d.id);
    $("d-saved").textContent = "已儲存";
    loadTags();
  } catch (e) {
    $("d-saved").textContent = `儲存失敗：${e.message}`;
  }
}

async function reveal(mode) {
  try {
    await api(`/api/open/${state.current.id}`, { mode });
  } catch (e) {
    alert(e.message);
  }
}

// ---- 側欄：統計、資料夾、工作 ----
async function loadStats() {
  const data = await api("/api/stats");
  const s = data.stats;
  $("stats").textContent = `${s.images} 張｜已分析 ${s.analyzed}｜待分析 ${s.pending}` +
    (s.failed ? `｜失敗 ${s.failed}` : "") + (s.missing ? `｜遺失 ${s.missing}` : "");
  const roots = $("roots");
  roots.replaceChildren();
  for (const r of data.roots) {
    roots.append(el("li", { class: r.online ? "" : "off", title: r.path },
      el("span", { class: "dot" }),
      el("strong", { text: r.name }),
      el("span", { class: "muted", text: ` ${r.images} 張${r.online ? "" : "（未連接）"}` }),
      el("div", { class: "muted small", text: r.path }),
    ));
  }
  $("models").textContent = `視覺模型：${data.models.vision}` + (data.models.embed ? `｜向量：${data.models.embed}` : "");
  $("semantic-wrap").hidden = !data.models.embed;
  $("empty").hidden = data.roots.length > 0;
  renderJob(data.job);
}

function renderJob(job) {
  const running = !!job.running;
  document.querySelectorAll("[data-job]").forEach((b) => { b.disabled = running; });
  $("stop-job").hidden = !running;
  $("job").textContent = job.message || "";
  $("job").classList.toggle("warning", !!job.error);
  if (running && !state.polling) {
    state.polling = setInterval(pollJob, 1500);
  }
  if (!running && state.polling) {
    clearInterval(state.polling);
    state.polling = null;
  }
  if (state.jobWasRunning && !running) {
    runSearch(state.q);
    loadTags();
  }
  state.jobWasRunning = running;
}

async function pollJob() {
  try {
    await loadStats();
  } catch {
    /* 伺服器暫時沒有回應，下次再試 */
  }
}

async function startJob(kind) {
  try {
    renderJob(await api(`/api/jobs/${kind}`, {}));
  } catch (e) {
    $("job").textContent = e.message;
  }
}

async function loadTags() {
  const tags = await api("/api/tags");
  const box = $("tags");
  box.replaceChildren();
  if (!tags.length) box.append(el("span", { class: "muted small", text: "分析後會出現" }));
  for (const { tag, count } of tags.slice(0, 50)) {
    box.append(el("button", { type: "button", onclick: () => setQuery(`tag:${quoteIfNeeded(tag)}`) },
      tag, el("span", { class: "n", text: String(count) })));
  }
}

function setQuery(q) {
  $("q").value = q;
  runSearch(q);
  window.scrollTo({ top: 0 });
}

// ---- 事件 ----
$("search-form").addEventListener("submit", (e) => { e.preventDefault(); runSearch($("q").value.trim()); });
$("semantic").addEventListener("change", () => runSearch($("q").value.trim()));
$("more").addEventListener("click", () => runSearch(state.q, true));
$("help-btn").addEventListener("click", () => $("help").showModal());
$("d-save").addEventListener("click", saveDetail);
$("d-reveal").addEventListener("click", () => reveal("reveal"));
$("d-open").addEventListener("click", () => reveal("open"));
$("d-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.current.path);
    $("d-saved").textContent = "已複製路徑";
  } catch {
    $("d-saved").textContent = state.current.path;
  }
});
$("stop-job").addEventListener("click", () => api("/api/jobs/stop", {}).then(renderJob));
document.querySelectorAll("[data-job]").forEach((b) => b.addEventListener("click", () => startJob(b.dataset.job)));
document.querySelectorAll("#quick [data-q]").forEach((b) => b.addEventListener("click", () => setQuery(b.dataset.q)));
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
    e.preventDefault();
    $("q").focus();
  }
});

const initial = new URLSearchParams(location.hash.slice(1)).get("q") || "";
$("q").value = initial;
loadStats().then(() => runSearch(initial)).catch((e) => { $("summary").textContent = e.message; });
loadTags().catch(() => {});
