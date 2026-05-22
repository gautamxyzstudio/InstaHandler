// MOZART Multi-Platform Handler — UI logic

const state = {
  brands: [],
  currentBrandId: null,
  jobs: [],
  pollTimer: null,
};

function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return [...root.querySelectorAll(sel)]; }
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  return r.json();
}
function escapeHtml(s) {
  return (s ?? "").toString()
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

// ------------ view switching ------------
$$(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const v = btn.dataset.view;
    $$(".view").forEach(el => el.classList.add("hidden"));
    $(`#view-${v}`).classList.remove("hidden");
    if (v === "history") loadHistory();
    if (v === "settings") loadBrands();
  });
});

// ------------ sidebar brands ------------
async function loadBrandSidebar() {
  const cfg = await api("/api/config");
  state.brands = cfg.brands || [];
  const list = $("#brand-list");
  list.innerHTML = "";
  $("#no-brands-hint").style.display = state.brands.length ? "none" : "block";
  state.brands.forEach(b => {
    const ig = !!(b.ig && b.ig.ig_user_id);
    const yt = !!b.yt_connected;
    const li = document.createElement("li");
    li.dataset.id = b.id;
    li.innerHTML = `
      <span>${escapeHtml(b.name)}</span>
      <span class="niche-tag">${b.niche} · ${ig ? "IG" : ""}${ig && yt ? "+" : ""}${yt ? "YT" : ""}${!ig && !yt ? "no platforms" : ""}</span>`;
    li.addEventListener("click", () => selectBrand(b.id));
    if (b.id === state.currentBrandId) li.classList.add("active");
    list.appendChild(li);
  });
  if (!state.currentBrandId && state.brands.length) selectBrand(state.brands[0].id);
  if (!state.brands.length) {
    $("#current-brand-name").textContent = "Add a brand to start";
    $("#current-brand-meta").textContent = "";
    $("#btn-post-all").disabled = true;
  }
}

function selectBrand(id) {
  state.currentBrandId = id;
  $$("#brand-list li").forEach(li => li.classList.toggle("active", li.dataset.id === id));
  const b = state.brands.find(x => x.id === id);
  if (b) {
    $("#current-brand-name").textContent = b.name;
    const platforms = [];
    if (b.ig && b.ig.ig_user_id) platforms.push("Instagram");
    if (b.yt_connected) platforms.push("YouTube");
    $("#current-brand-meta").textContent =
      `${b.niche} · ${b.caption_style} · ${platforms.join(" + ") || "no platforms connected yet"}`;
  }
  loadJobs();
}

// ------------ upload ------------
const dz = $("#dropzone");
const fi = $("#file-input");
dz.addEventListener("click", () => fi.click());
dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", e => {
  e.preventDefault(); dz.classList.remove("drag");
  if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
});
fi.addEventListener("change", () => {
  if (fi.files.length) uploadFiles(fi.files);
  fi.value = "";
});

async function uploadFiles(files) {
  if (!state.currentBrandId) { alert("Pick a brand first."); return; }
  const fd = new FormData();
  fd.append("brand_id", state.currentBrandId);
  [...files].forEach(f => fd.append("videos", f));
  const tmp = document.createElement("div");
  tmp.className = "empty muted";
  tmp.textContent = `Uploading ${files.length} file(s)...`;
  $("#job-list").prepend(tmp);
  const res = await api("/api/upload", { method: "POST", body: fd });
  tmp.remove();
  if (!res.ok) { alert("Upload failed."); return; }
  await loadJobs();
}

// ------------ jobs ------------
async function loadJobs({ preserveDrafts = false } = {}) {
  if (!state.currentBrandId) return;
  const unsaved = {};
  if (preserveDrafts) {
    $$(".job").forEach(card => {
      const id = card.dataset.id;
      const orig = state.jobs.find(j => j.id === id);
      if (!orig) return;
      const ig = card.querySelector("[data-fld='ig_caption']");
      const ytT = card.querySelector("[data-fld='yt_title']");
      const ytD = card.querySelector("[data-fld='yt_description']");
      if (ig && ig.value !== orig.ig_caption) unsaved[id] = { ...(unsaved[id] || {}), ig_caption: ig.value };
      if (ytT && ytT.value !== orig.yt_title) unsaved[id] = { ...(unsaved[id] || {}), yt_title: ytT.value };
      if (ytD && ytD.value !== orig.yt_description) unsaved[id] = { ...(unsaved[id] || {}), yt_description: ytD.value };
    });
  }
  const res = await api(`/api/jobs?brand_id=${state.currentBrandId}`);
  state.jobs = res.jobs || [];
  Object.entries(unsaved).forEach(([id, fields]) => {
    const j = state.jobs.find(x => x.id === id);
    if (j && (j.status === "draft" || j.status === "failed")) Object.assign(j, fields);
  });
  renderJobs();
  $("#btn-post-all").disabled = !state.jobs.some(j => j.status === "draft");
}

function platformPill(p, status) {
  const map = { ig: "IG", yt: "YT" };
  const cls = status ? `status-${status}` : "status-draft";
  return `<span class="pill ${p} ${cls}">${map[p]}${status ? " " + status : ""}</span>`;
}

function renderJobs() {
  const list = $("#job-list");
  if (!state.jobs.length) {
    list.innerHTML = `<div class="empty muted">No videos uploaded yet for this brand.</div>`;
    return;
  }
  const brand = state.brands.find(b => b.id === state.currentBrandId) || {};
  const igAvailable = !!(brand.ig && brand.ig.ig_user_id);
  const ytAvailable = !!brand.yt_connected;

  list.innerHTML = "";
  state.jobs.forEach(job => {
    const card = document.createElement("div");
    card.className = "job dual";
    card.dataset.id = job.id;
    const canEdit = job.status === "draft" || job.status === "failed";
    const igOn = job.platforms?.includes("ig");
    const ytOn = job.platforms?.includes("yt");
    const psIg = (job.platform_status || {}).ig;
    const psYt = (job.platform_status || {}).yt;

    card.innerHTML = `
      <video src="/uploads/${encodeURIComponent(job.file)}" controls preload="metadata"></video>
      <div class="job-body">
        <div class="job-title" title="${escapeHtml(job.original_name)}">${escapeHtml(job.original_name)}</div>
        <div class="job-meta">
          <span class="status-pill status-${job.status}">${job.status}</span>
          ${igOn ? platformPill("ig", psIg) : ""}
          ${ytOn ? platformPill("yt", psYt) : ""}
          ${job.ig_result?.media_id ? `<span class="muted small">ig:${escapeHtml(job.ig_result.media_id)}</span>` : ""}
          ${job.yt_result?.url ? `<a class="muted small" href="${escapeHtml(job.yt_result.url)}" target="_blank">${escapeHtml(job.yt_result.url)}</a>` : ""}
        </div>

        <div class="dual-grid">
          <div class="dual-col">
            <div class="dual-label"><span class="pill ig">Instagram caption</span></div>
            <textarea data-fld="ig_caption" ${canEdit ? "" : "disabled"} rows="6">${escapeHtml(job.ig_caption)}</textarea>
          </div>
          <div class="dual-col">
            <div class="dual-label"><span class="pill yt">YouTube Short</span></div>
            <input data-fld="yt_title" placeholder="Title (under 100 chars, ends in #shorts)"
              ${canEdit ? "" : "disabled"} value="${escapeHtml(job.yt_title)}" />
            <textarea data-fld="yt_description" ${canEdit ? "" : "disabled"} rows="4"
              placeholder="Description">${escapeHtml(job.yt_description)}</textarea>
          </div>
        </div>

        ${job.error ? `<div class="error-text">⚠ ${escapeHtml(job.error)}</div>` : ""}
      </div>

      <div class="job-actions">
        ${canEdit ? `
          <label class="check"><input type="checkbox" data-toggle="ig" ${igOn ? "checked" : ""} ${igAvailable ? "" : "disabled"} /> Post to IG</label>
          <label class="check"><input type="checkbox" data-toggle="yt" ${ytOn ? "checked" : ""} ${ytAvailable ? "" : "disabled"} /> Post to YT</label>
          <label class="schedule-label">Schedule (optional)
            <input type="datetime-local" data-fld="scheduled_for" value="${job.scheduled_for ? toLocalDt(job.scheduled_for) : ""}" />
          </label>
          <button class="primary" data-act="queue">${job.scheduled_for ? "Schedule" : "Post now"}</button>
          <button class="icon-btn" data-act="regen">↻ Regenerate</button>
          <button class="icon-btn" data-act="save">Save edits</button>
          <button class="danger" data-act="delete">Remove</button>
        ` : `<button class="icon-btn" disabled>${job.status}</button>`}
      </div>`;
    list.appendChild(card);
  });

  $$("#job-list .job").forEach(card => {
    const id = card.dataset.id;
    card.querySelectorAll("button[data-act]").forEach(b =>
      b.addEventListener("click", () => handleJobAction(b.dataset.act, id, card))
    );
  });
}

function toLocalDt(iso) {
  // turn "2026-05-25T18:30:00" into a value compatible with datetime-local
  if (!iso) return "";
  try { return iso.slice(0, 16); } catch { return ""; }
}

async function collectJobFields(card, id) {
  const igVal = card.querySelector("[data-fld='ig_caption']")?.value ?? "";
  const ytT   = card.querySelector("[data-fld='yt_title']")?.value ?? "";
  const ytD   = card.querySelector("[data-fld='yt_description']")?.value ?? "";
  const sched = card.querySelector("[data-fld='scheduled_for']")?.value || null;
  const platforms = [];
  card.querySelectorAll("[data-toggle]").forEach(cb => {
    if (cb.checked && !cb.disabled) platforms.push(cb.dataset.toggle);
  });
  await api(`/api/jobs/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ig_caption: igVal, yt_title: ytT, yt_description: ytD,
      platforms, scheduled_for: sched,
    }),
  });
}

async function handleJobAction(act, id, card) {
  const job = state.jobs.find(j => j.id === id);
  if (!job) return;
  if (act === "save") { await collectJobFields(card, id); pulse(card); }
  else if (act === "queue") {
    await collectJobFields(card, id);
    const r = await api(`/api/jobs/${id}/queue`, { method: "POST" });
    if (!r.ok) alert(r.error || "could not queue");
    loadJobs();
  }
  else if (act === "delete") {
    if (!confirm("Remove this video from the queue?")) return;
    await api(`/api/jobs/${id}`, { method: "DELETE" });
    loadJobs();
  }
  else if (act === "regen") {
    const r = await api("/api/regenerate_caption", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brand_id: state.currentBrandId, filename: job.original_name }),
    });
    if (r.ok) {
      card.querySelector("[data-fld='ig_caption']").value = r.instagram.caption;
      card.querySelector("[data-fld='yt_title']").value = r.youtube.title;
      card.querySelector("[data-fld='yt_description']").value = r.youtube.description;
      pulse(card);
    }
  }
}

function pulse(el) {
  el.style.transition = "background-color 0.3s ease";
  el.style.backgroundColor = "rgba(46,204,113,0.08)";
  setTimeout(() => { el.style.backgroundColor = ""; }, 500);
}

$("#btn-post-all").addEventListener("click", async () => {
  if (!confirm("Queue all draft videos for this brand?")) return;
  // save all edits first
  for (const card of $$("#job-list .job")) {
    await collectJobFields(card, card.dataset.id);
  }
  await api("/api/jobs/queue_all", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brand_id: state.currentBrandId }),
  });
  loadJobs();
});

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    if ($("#view-dashboard").classList.contains("hidden")) return;
    if (!state.currentBrandId) return;
    if (state.jobs.some(j => !["posted", "failed", "draft", "partial"].includes(j.status))) {
      loadJobs({ preserveDrafts: true });
    }
  }, 3000);
}

// ------------ history ------------
async function loadHistory() {
  const res = await api("/api/log");
  const tbody = $("#history-body");
  if (!res.log || !res.log.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No posts yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = res.log.map(row => `
    <tr>
      <td>${escapeHtml((row.timestamp || "").replace("T", " "))}</td>
      <td>${escapeHtml(row.brand || "")}</td>
      <td>${escapeHtml(row.file || "")}</td>
      <td class="caption">${escapeHtml(row.caption_preview || "")}</td>
      <td>${row.ig_status === true ? "✓" : (row.ig_status === false ? "✗" : "—")}</td>
      <td>${row.yt_status === true ? (row.yt_url ? `<a href="${escapeHtml(row.yt_url)}" target="_blank">✓</a>` : "✓") : (row.yt_status === false ? "✗" : "—")}</td>
      <td><span class="status-pill status-${row.status}">${row.status}</span></td>
    </tr>`).join("");
}

// ------------ brands / settings ------------
async function loadBrands() {
  const cfg = await api("/api/config");
  const list = $("#brands-list");
  list.innerHTML = "";
  (cfg.brands || []).forEach(b => {
    const ig = !!(b.ig && b.ig.ig_user_id);
    const yt = !!b.yt_connected;
    const card = document.createElement("div");
    card.className = "account-card";
    card.innerHTML = `
      <div>
        <div class="name">${escapeHtml(b.name)}</div>
        <div class="muted">
          ${b.niche} · ${b.caption_style} ·
          ${ig ? `<span class="pill ig">IG ${escapeHtml(b.ig_token_preview || "")}</span>` : `<span class="muted small">no IG</span>`}
          ${yt ? `<span class="pill yt">YT connected</span>` : `<span class="muted small">no YT</span>`}
        </div>
      </div>
      <button class="icon-btn">Edit</button>`;
    card.querySelector("button").addEventListener("click", () => openEditor(b));
    list.appendChild(card);
  });
  if (!cfg.brands || !cfg.brands.length) {
    list.innerHTML = `<div class="muted">No brands yet. Click + Add brand.</div>`;
  }
}

$("#btn-add-brand").addEventListener("click", () => openEditor(null));
$("#ed-cancel").addEventListener("click", () => $("#brand-editor").classList.add("hidden"));
$("#ed-save").addEventListener("click", saveBrand);
$("#ed-delete").addEventListener("click", deleteBrand);
$("#btn-yt-connect").addEventListener("click", connectYouTube);
$("#btn-yt-disconnect").addEventListener("click", disconnectYouTube);

function openEditor(b) {
  $("#brand-editor").classList.remove("hidden");
  $("#editor-title").textContent = b ? `Edit: ${b.name}` : "Add brand";
  $("#ed-id").value = b ? b.id : "";
  $("#ed-name").value = b ? b.name : "";
  $("#ed-niche").value = b ? b.niche : "fitness";
  $("#ed-style").value = b ? b.caption_style : "energetic";
  $("#ed-cta").value = b ? (b.default_cta || "") : "";
  $("#ed-tags").value = b ? b.hashtag_count : 25;
  $("#ed-ig-id").value = b ? (b.ig?.ig_user_id || "") : "";
  $("#ed-ig-token").value = "";
  $("#ed-ig-tok-prev").textContent = b?.ig_token_preview ? `(current: ${b.ig_token_preview})` : "";
  $("#ed-yt-cid").value = b ? (b.yt?.client_id || "") : "";
  $("#ed-yt-secret").value = "";
  $("#ed-yt-sec-prev").textContent = b?.yt_client_secret_preview ? `(current: ${b.yt_client_secret_preview})` : "";
  $("#yt-status").innerHTML = b?.yt_connected ? `<span class="pill yt">connected ✓</span>` : "<span class='muted small'>not connected</span>";
  $("#btn-yt-disconnect").style.display = b?.yt_connected ? "" : "none";
  $("#ed-delete").style.display = b ? "" : "none";
  window.scrollTo({ top: $("#brand-editor").offsetTop - 20, behavior: "smooth" });
}

async function saveBrand() {
  const body = {
    id: $("#ed-id").value || null,
    name: $("#ed-name").value.trim(),
    niche: $("#ed-niche").value,
    caption_style: $("#ed-style").value,
    default_cta: $("#ed-cta").value.trim(),
    hashtag_count: parseInt($("#ed-tags").value, 10) || 25,
    ig: {
      ig_user_id: $("#ed-ig-id").value.trim(),
      access_token: $("#ed-ig-token").value.trim(),
    },
    yt: {
      client_id: $("#ed-yt-cid").value.trim(),
      client_secret: $("#ed-yt-secret").value.trim(),
    },
  };
  if (!body.name) { alert("Brand name is required."); return; }
  const res = await api("/api/brands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    $("#ed-id").value = res.id;  // keep the ID so subsequent OAuth ties to it
    await loadBrands();
    await loadBrandSidebar();
    alert("Brand saved.");
  }
}

async function deleteBrand() {
  const id = $("#ed-id").value;
  if (!id) return;
  if (!confirm("Delete this brand? IG and YT credentials will be removed.")) return;
  await api(`/api/brands/${id}`, { method: "DELETE" });
  $("#brand-editor").classList.add("hidden");
  if (state.currentBrandId === id) state.currentBrandId = null;
  await loadBrands();
  await loadBrandSidebar();
}

async function connectYouTube() {
  const id = $("#ed-id").value;
  const client_id = $("#ed-yt-cid").value.trim();
  const client_secret = $("#ed-yt-secret").value.trim();
  if (!id) { alert("Save the brand first (just click 'Save brand' once)."); return; }
  if (!client_id || !client_secret) { alert("Paste both OAuth Client ID and Client Secret first."); return; }
  // open the OAuth flow in a new tab
  const url = `/oauth/youtube/start?brand_id=${encodeURIComponent(id)}&client_id=${encodeURIComponent(client_id)}&client_secret=${encodeURIComponent(client_secret)}`;
  window.open(url, "_blank");
}

async function disconnectYouTube() {
  const id = $("#ed-id").value;
  if (!id) return;
  if (!confirm("Disconnect YouTube from this brand?")) return;
  await api(`/api/brands/${id}/disconnect_yt`, { method: "POST" });
  await loadBrands();
  await loadBrandSidebar();
  const cfg = await api("/api/config");
  openEditor(cfg.brands.find(b => b.id === id));
}

// ------------ boot ------------
loadBrandSidebar();
startPolling();
