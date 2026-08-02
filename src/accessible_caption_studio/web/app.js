const state = {
  project: null,
  projects: [],
  undo: [],
  activeJob: null,
  pollTimer: null,
  saveTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const homeView = $("#homeView");
const workspaceView = $("#workspaceView");
const mediaPlayer = $("#mediaPlayer");
const audioPlayer = $("#audioPlayer");
const themeStorageKey = "accessible-caption-theme";

document.addEventListener("DOMContentLoaded", init);

async function init() {
  applyTheme(document.documentElement.dataset.theme || "light", false);
  bindEvents();
  await loadProjects();
}

function bindEvents() {
  $("#homeButton").addEventListener("click", showHome);
  $("#backButton").addEventListener("click", showHome);
  $("#refreshProjects").addEventListener("click", loadProjects);
  $("#fileTab").addEventListener("click", () => selectTab("file"));
  $("#youtubeTab").addEventListener("click", () => selectTab("youtube"));
  $("#uploadForm").addEventListener("submit", uploadMedia);
  $("#youtubeForm").addEventListener("submit", importYouTube);
  $("#mediaInput").addEventListener("change", updateFileLabel);
  bindDropZone();
  $("#settingsButton").addEventListener("click", openSettings);
  $("#themeToggle").addEventListener("click", toggleTheme);
  $("#darkModeSetting").addEventListener("change", (event) => applyTheme(event.target.checked ? "dark" : "light"));
  $("#saveToken").addEventListener("click", saveToken);
  $("#clearModels").addEventListener("click", () => clearStorage("models"));
  $("#clearTemporary").addEventListener("click", () => clearStorage("temporary"));
  $("#projectTitle").addEventListener("input", scheduleSave);
  $("#analyzeButton").addEventListener("click", runAnalysis);
  $("#validateButton").addEventListener("click", validateProject);
  $("#exportButton").addEventListener("click", openExports);
  $("#closeExportComplete").addEventListener("click", () => $("#exportCompleteDialog").close());
  document.querySelectorAll("[data-export]").forEach((button) =>
    button.addEventListener("click", () => createExport(button.dataset.export))
  );
  $("#addCueButton").addEventListener("click", addCue);
  $("#undoButton").addEventListener("click", undo);
  $("#cancelJob").addEventListener("click", cancelJob);
  [mediaPlayer, audioPlayer].forEach((player) => player.addEventListener("timeupdate", syncPlayback));
  document.addEventListener("keydown", playbackKeys);
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

function applyTheme(theme, persist = true) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("#themeToggle").setAttribute("aria-pressed", String(dark));
  $("#themeIcon").textContent = dark ? "☀" : "☾";
  $("#themeLabel").textContent = dark ? "Light mode" : "Dark mode";
  $("#darkModeSetting").checked = dark;
  if (persist) {
    try { localStorage.setItem(themeStorageKey, dark ? "dark" : "light"); }
    catch (_) { /* The selected theme still applies for this session. */ }
  }
}

function selectTab(name) {
  const file = name === "file";
  $("#fileTab").setAttribute("aria-selected", String(file));
  $("#youtubeTab").setAttribute("aria-selected", String(!file));
  $("#filePanel").hidden = !file;
  $("#youtubePanel").hidden = file;
  (file ? $("#mediaInput") : $("#youtubeUrl")).focus();
}

function bindDropZone() {
  const zone = $("#dropZone");
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
  }));
  zone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    $("#mediaInput").files = transfer.files;
    updateFileLabel();
  });
}

function updateFileLabel() {
  const file = $("#mediaInput").files[0];
  if (!file) return;
  $("#dropZone strong").textContent = file.name;
  $("#dropZone > span:last-of-type").textContent = formatBytes(file.size);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = payload.detail?.message || payload.detail || detail;
    } catch (_) { /* Keep the status message. */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function loadProjects() {
  try {
    state.projects = await api("/api/projects");
    renderProjects();
  } catch (error) {
    toast(error.message);
  }
}

function renderProjects() {
  const list = $("#projectList");
  list.replaceChildren();
  $("#emptyProjects").hidden = state.projects.length > 0;
  state.projects.forEach((project) => {
    const wrapper = document.createElement("article");
    wrapper.className = "project-card";
    const open = document.createElement("button");
    open.type = "button";
    open.className = "project-open";
    open.style.cssText = "border:0;background:transparent;text-align:left;width:100%;padding:0;color:inherit";
    const type = document.createElement("span");
    type.className = "project-type";
    type.textContent = project.media?.has_video ? "▶" : "♪";
    const title = document.createElement("strong");
    title.textContent = project.name;
    const meta = document.createElement("span");
    meta.textContent = `${project.cues.length} captions · ${relativeDate(project.updated_at)}`;
    open.append(type, title, meta);
    open.addEventListener("click", () => openProject(project.id));
    const actions = document.createElement("div");
    actions.className = "button-row";
    actions.style.marginTop = ".8rem";
    actions.append(
      smallAction("Duplicate", () => duplicateProject(project.id)),
      smallAction("Delete", () => deleteProject(project.id), true),
    );
    wrapper.append(open, actions);
    list.append(wrapper);
  });
}

function smallAction(label, handler, danger = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = danger ? "danger-secondary" : "secondary";
  button.style.padding = ".35rem .55rem";
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

async function uploadMedia(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!$("#mediaInput").files[0]) return;
  setBusy(form, true, "Importing…");
  try {
    const payload = await api("/api/projects/upload", { method: "POST", body: new FormData(form) });
    state.project = payload.project;
    showWorkspace();
    if (payload.job) monitorJob(payload.job);
    form.reset();
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(form, false);
  }
}

async function importYouTube(event) {
  event.preventDefault();
  const form = event.currentTarget;
  setBusy(form, true, "Importing…");
  try {
    const payload = await api("/api/projects/youtube", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: $("#youtubeUrl").value }),
    });
    state.project = payload.project;
    showWorkspace();
    monitorJob(payload.job);
    form.reset();
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(form, false);
  }
}

function setBusy(form, busy, label = "") {
  form.querySelectorAll("button, input").forEach((element) => { element.disabled = busy; });
  const submit = form.querySelector("button[type=submit]");
  if (!submit) return;
  if (!submit.dataset.label) submit.dataset.label = submit.textContent;
  submit.textContent = busy ? label : submit.dataset.label;
}

async function openProject(id) {
  try {
    state.project = await api(`/api/projects/${id}`);
    showWorkspace();
    if (state.project.latest_job_id) {
      const job = await api(`/api/projects/${id}/jobs/${state.project.latest_job_id}`);
      if (["queued", "running"].includes(job.state)) monitorJob(job);
    }
  } catch (error) {
    toast(error.message);
  }
}

function showWorkspace() {
  homeView.hidden = true;
  workspaceView.hidden = false;
  state.undo = [];
  $("#undoButton").disabled = true;
  renderProject();
  $("#main").focus();
}

async function showHome() {
  clearTimeout(state.pollTimer);
  workspaceView.hidden = true;
  homeView.hidden = false;
  state.project = null;
  mediaPlayer.pause();
  audioPlayer.pause();
  await loadProjects();
  $("#homeTitle").focus?.();
}

function renderProject() {
  const project = state.project;
  if (!project) return;
  $("#projectTitle").value = project.name;
  const hasMedia = Boolean(project.media);
  if (hasMedia) {
    const source = `/api/projects/${project.id}/media`;
    mediaPlayer.hidden = !project.media.has_video;
    audioPlayer.hidden = project.media.has_video;
    const active = project.media.has_video ? mediaPlayer : audioPlayer;
    if (!active.src.endsWith(source)) active.src = source;
  } else {
    mediaPlayer.hidden = true;
    audioPlayer.hidden = true;
  }
  renderCues();
  renderFindings();
  renderSummary();
  renderExportResults();
}

function renderCues() {
  const list = $("#cueList");
  list.replaceChildren();
  $("#emptyCues").hidden = state.project.cues.length > 0;
  const flagged = new Set(state.project.findings.filter((item) => item.cue_id).map((item) => item.cue_id));
  state.project.cues.forEach((cue, index) => {
    const row = document.createElement("article");
    row.className = `cue-row${flagged.has(cue.id) ? " flagged" : ""}`;
    row.dataset.cueId = cue.id;
    row.id = `cue-${cue.id}`;

    const times = document.createElement("div");
    times.className = "time-inputs";
    times.append(timeField("In", cue.start, (value) => updateCue(index, "start", value)), timeField("Out", cue.end, (value) => updateCue(index, "end", value)));
    const text = document.createElement("textarea");
    text.className = "cue-text";
    text.setAttribute("aria-label", `Caption ${index + 1} text`);
    text.value = cue.text;
    text.addEventListener("focus", () => seekTo(cue.start));
    text.addEventListener("input", () => updateCue(index, "text", text.value));

    const meta = document.createElement("div");
    meta.className = "cue-meta";
    const speaker = document.createElement("input");
    speaker.className = "cue-speaker";
    speaker.setAttribute("aria-label", `Caption ${index + 1} speaker`);
    speaker.placeholder = "No speaker";
    speaker.value = cue.speaker || "";
    speaker.addEventListener("input", () => updateCue(index, "speaker", speaker.value || null));
    const confidence = document.createElement("span");
    confidence.className = `confidence${cue.confidence !== null && cue.confidence < .7 ? " low" : ""}`;
    confidence.textContent = cue.confidence === null ? humanSource(cue.source) : `${Math.round(cue.confidence * 100)}% confidence`;
    meta.append(speaker, confidence);

    const menu = document.createElement("button");
    menu.type = "button";
    menu.className = "cue-menu";
    menu.textContent = "×";
    menu.setAttribute("aria-label", `Delete caption ${index + 1}`);
    menu.addEventListener("click", () => deleteCue(index));

    const actions = document.createElement("div");
    actions.className = "cue-actions";
    actions.append(
      actionButton("Split", () => splitCue(index)),
      actionButton("Merge next", () => mergeCue(index), index === state.project.cues.length - 1),
      actionButton("Move up", () => moveCue(index, -1), index === 0),
      actionButton("Move down", () => moveCue(index, 1), index === state.project.cues.length - 1),
    );
    row.append(times, text, meta, menu, actions);
    row.addEventListener("click", () => seekTo(cue.start));
    list.append(row);
  });
}

function timeField(label, value, onChange) {
  const wrapper = document.createElement("label");
  wrapper.append(document.createTextNode(label));
  const input = document.createElement("input");
  input.type = "number";
  input.step = ".001";
  input.min = "0";
  input.value = Number(value).toFixed(3);
  input.addEventListener("change", () => onChange(Math.max(0, Number(input.value) || 0)));
  wrapper.append(input);
  return wrapper;
}

function actionButton(label, handler, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener("click", (event) => { event.stopPropagation(); handler(); });
  return button;
}

function humanSource(source) {
  return ({ transcription: "Whisper", imported: "Imported", manual: "Manual", sound: "Sound cue" })[source] || "Caption";
}

function remember() {
  state.undo.push(JSON.stringify(state.project.cues));
  if (state.undo.length > 30) state.undo.shift();
  $("#undoButton").disabled = false;
}

function updateCue(index, field, value) {
  if (!state.project.cues[index]) return;
  if (!state.project.cues[index]._editing) remember();
  state.project.cues[index]._editing = true;
  state.project.cues[index][field] = value;
  scheduleSave();
}

function addCue() {
  remember();
  const player = activePlayer();
  const start = player.currentTime || 0;
  state.project.cues.push({ id: crypto.randomUUID().replaceAll("-", ""), start, end: Math.min(start + 2, state.project.media?.duration || start + 2), text: "New caption", speaker: null, source: "manual", confidence: null, sound_event_id: null });
  state.project.cues.sort((a, b) => a.start - b.start);
  renderCues();
  scheduleSave();
}

function deleteCue(index) {
  remember();
  state.project.cues.splice(index, 1);
  renderCues();
  scheduleSave();
}

function splitCue(index) {
  const cue = state.project.cues[index];
  if (!cue) return;
  remember();
  const words = cue.text.split(/\s+/);
  const split = Math.max(1, Math.floor(words.length / 2));
  const middle = (cue.start + cue.end) / 2;
  const second = { ...cue, id: crypto.randomUUID().replaceAll("-", ""), start: middle, text: words.slice(split).join(" ") || "Continued caption", source: "manual" };
  cue.end = middle;
  cue.text = words.slice(0, split).join(" ");
  cue.source = "manual";
  state.project.cues.splice(index + 1, 0, second);
  renderCues();
  scheduleSave();
}

function mergeCue(index) {
  const cue = state.project.cues[index];
  const next = state.project.cues[index + 1];
  if (!cue || !next) return;
  remember();
  cue.end = Math.max(cue.end, next.end);
  cue.text = `${cue.text} ${next.text}`.trim();
  cue.source = "manual";
  state.project.cues.splice(index + 1, 1);
  renderCues();
  scheduleSave();
}

function moveCue(index, offset) {
  const target = index + offset;
  if (target < 0 || target >= state.project.cues.length) return;
  remember();
  [state.project.cues[index], state.project.cues[target]] = [state.project.cues[target], state.project.cues[index]];
  renderCues();
  scheduleSave();
}

function undo() {
  const snapshot = state.undo.pop();
  if (!snapshot) return;
  state.project.cues = JSON.parse(snapshot);
  $("#undoButton").disabled = state.undo.length === 0;
  renderCues();
  scheduleSave();
}

function scheduleSave() {
  $("#saveStatus").textContent = "Saving…";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveProject, 500);
}

async function saveProject() {
  if (!state.project) return;
  state.project.cues.forEach((cue) => delete cue._editing);
  try {
    state.project = await api(`/api/projects/${state.project.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("#projectTitle").value, cues: state.project.cues }),
    });
    $("#saveStatus").textContent = "Saved";
    renderFindings();
    renderSummary();
  } catch (error) {
    $("#saveStatus").textContent = "Not saved";
    toast(error.message);
  }
}

async function validateProject() {
  try {
    await saveProject();
    state.project = await api(`/api/projects/${state.project.id}/validate`, { method: "POST" });
    renderFindings();
    toast(state.project.findings.length ? "Caption check complete." : "No accessibility issues found.");
  } catch (error) { toast(error.message); }
}

async function runAnalysis() {
  if (!state.project?.media) {
    toast("Wait for the media import to finish before starting analysis.");
    return;
  }
  $("#analyzeButton").disabled = true;
  try {
    const job = await api(`/api/projects/${state.project.id}/analyze`, { method: "POST" });
    monitorJob(job);
  } catch (error) {
    toast(error.message);
  } finally {
    $("#analyzeButton").disabled = false;
  }
}

function renderFindings() {
  const list = $("#findingList");
  list.replaceChildren();
  const findings = state.project.findings || [];
  $("#findingCount").textContent = `${findings.length} ${findings.length === 1 ? "finding" : "findings"}`;
  if (!findings.length) {
    const success = document.createElement("p");
    success.className = "success-note";
    success.textContent = "No automatic accessibility issues found.";
    list.append(success);
    return;
  }
  findings.slice(0, 12).forEach((finding) => {
    const item = document.createElement("div");
    item.className = `finding ${finding.severity}`;
    item.textContent = finding.message;
    if (finding.cue_id) {
      const jump = document.createElement("button");
      jump.type = "button";
      jump.textContent = "Go to caption";
      jump.addEventListener("click", () => focusCue(finding.cue_id));
      item.append(jump);
    }
    list.append(item);
  });
}

function renderSummary() {
  const cues = state.project.cues || [];
  const low = cues.filter((cue) => cue.confidence !== null && cue.confidence < .7).length;
  const speakers = new Set(cues.map((cue) => cue.speaker).filter(Boolean)).size;
  $("#qualitySummary").innerHTML = `
    <div class="quality-stat"><strong>${cues.length}</strong><span>Caption cues</span></div>
    <div class="quality-stat"><strong>${speakers}</strong><span>Speakers</span></div>
    <div class="quality-stat"><strong>${low}</strong><span>Low confidence</span></div>`;
}

function focusCue(id) {
  const element = document.querySelector(`[data-cue-id="${CSS.escape(id)}"]`);
  element?.scrollIntoView({ behavior: "smooth", block: "center" });
  element?.querySelector("textarea")?.focus();
}

function activePlayer() { return state.project?.media?.has_video ? mediaPlayer : audioPlayer; }
function seekTo(seconds) { const player = activePlayer(); if (player?.src) player.currentTime = seconds; }

function syncPlayback() {
  if (!state.project) return;
  const time = activePlayer().currentTime;
  const active = state.project.cues.find((cue) => time >= cue.start && time < cue.end);
  $("#captionOverlay").textContent = active ? `${active.speaker ? `${active.speaker}: ` : ""}${active.text}` : "";
  document.querySelectorAll(".cue-row.active").forEach((row) => row.classList.remove("active"));
  if (active) document.querySelector(`[data-cue-id="${CSS.escape(active.id)}"]`)?.classList.add("active");
}

function playbackKeys(event) {
  if (workspaceView.hidden || ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
  const player = activePlayer();
  if (!player?.src) return;
  if (event.code === "Space") { event.preventDefault(); player.paused ? player.play() : player.pause(); }
  if (event.code === "ArrowLeft") { event.preventDefault(); player.currentTime = Math.max(0, player.currentTime - 5); }
  if (event.code === "ArrowRight") { event.preventDefault(); player.currentTime = Math.min(player.duration || Infinity, player.currentTime + 5); }
}

function monitorJob(job) {
  state.activeJob = job;
  $("#jobPanel").hidden = false;
  updateJobPanel(job);
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(pollJob, 900);
}

async function pollJob() {
  if (!state.activeJob || !state.project) return;
  try {
    const job = await api(`/api/projects/${state.project.id}/jobs/${state.activeJob.id}`);
    state.activeJob = job;
    updateJobPanel(job);
    if (["queued", "running"].includes(job.state)) {
      state.pollTimer = setTimeout(pollJob, 1100);
      return;
    }
    if (job.state === "completed") {
      state.project = await api(`/api/projects/${state.project.id}`);
      renderProject();
      if (job.kind === "mp4-export") {
        const artifact = state.project.exports.find((item) => item.format === "mp4");
        if (artifact) showExportComplete(artifact);
      } else {
        toast("Automatic captions are ready.");
      }
    } else if (job.state === "failed") {
      toast(job.error || "Processing could not be completed.");
      if (["hf_token_required", "pyannote_access_required"].includes(job.error_code)) openSettings();
    }
    setTimeout(() => { $("#jobPanel").hidden = true; }, 1800);
  } catch (error) { toast(error.message); }
}

function updateJobPanel(job) {
  $("#jobStage").textContent = job.stage;
  $("#jobMessage").textContent = job.message || job.state;
  $("#jobProgress").value = job.progress;
  $("#jobProgress").textContent = `${job.progress}%`;
  $("#jobPercent").textContent = `${job.progress}%`;
  $("#cancelJob").hidden = !["queued", "running"].includes(job.state);
}

async function cancelJob() {
  if (!state.activeJob) return;
  try {
    state.activeJob = await api(`/api/projects/${state.project.id}/jobs/${state.activeJob.id}/cancel`, { method: "POST" });
    updateJobPanel(state.activeJob);
  } catch (error) { toast(error.message); }
}

async function duplicateProject(id) {
  try {
    const project = await api(`/api/projects/${id}/duplicate`, { method: "POST" });
    toast("Project duplicated.");
    await loadProjects();
    await openProject(project.id);
  } catch (error) { toast(error.message); }
}

async function deleteProject(id) {
  const project = state.projects.find((item) => item.id === id);
  if (!confirm(`Delete “${project?.name || "this project"}” and its local media? This cannot be undone.`)) return;
  try {
    await api(`/api/projects/${id}`, { method: "DELETE" });
    toast("Project deleted.");
    await loadProjects();
  } catch (error) { toast(error.message); }
}

async function openSettings() {
  if (!$("#settingsDialog").open) $("#settingsDialog").showModal();
  try {
    const [storage, health] = await Promise.all([api("/api/storage"), api("/api/health")]);
    $("#storageStats").innerHTML = `
      <div><strong>${formatBytes(storage.projects_bytes)}</strong><span>Projects</span></div>
      <div><strong>${formatBytes(storage.models_bytes)}</strong><span>Models</span></div>
      <div><strong>${formatBytes(storage.temporary_bytes)}</strong><span>Temporary</span></div>`;
    $("#tokenStatus").textContent = health.hf_token_configured ? "A token is saved on this Mac." : "No token is configured yet.";
  } catch (error) { toast(error.message); }
}

async function saveToken() {
  try {
    await api("/api/settings/hugging-face-token", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: $("#hfToken").value }) });
    $("#hfToken").value = "";
    $("#tokenStatus").textContent = "Token saved securely for local model downloads.";
  } catch (error) { $("#tokenStatus").textContent = error.message; }
}

async function clearStorage(target) {
  const label = target === "models" ? "downloaded model cache" : "temporary files";
  if (!confirm(`Clear the ${label}? Saved projects will not be deleted.`)) return;
  try {
    await api(`/api/storage/${target}`, { method: "DELETE" });
    toast(`${label[0].toUpperCase()}${label.slice(1)} cleared.`);
    await openSettings();
  } catch (error) { toast(error.message); }
}

function openExports() {
  renderExportResults();
  $("#exportDialog").showModal();
}

async function createExport(format) {
  const button = document.querySelector(`[data-export="${format}"]`);
  button.disabled = true;
  try {
    await saveProject();
    const result = await api(`/api/projects/${state.project.id}/exports/${format}`, { method: "POST" });
    if (format === "mp4") {
      $("#exportDialog").close();
      monitorJob(result);
    } else {
      state.project = await api(`/api/projects/${state.project.id}`);
      $("#exportDialog").close();
      const artifact = state.project.exports.find((item) => item.format === format);
      if (artifact) showExportComplete(artifact);
    }
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
}

function showExportComplete(artifact) {
  const isVideo = artifact.format === "mp4";
  $("#exportCompleteTitle").textContent = isVideo ? "Your captioned video is ready" : `Your ${artifact.format.toUpperCase()} file is ready`;
  $("#exportCompleteMessage").textContent = `${artifact.filename} · ${formatBytes(artifact.size_bytes)}`;
  $("#exportSavedLocation").textContent = `Saved in the project at storage/projects/${state.project.id}/exports/${artifact.filename}. Downloading saves another copy to your browser’s Downloads folder.`;
  const link = $("#downloadCompletedExport");
  link.href = `/api/projects/${state.project.id}/exports/${encodeURIComponent(artifact.filename)}`;
  link.download = artifact.filename;
  link.textContent = isVideo ? "Download video" : `Download ${artifact.format.toUpperCase()}`;
  const dialog = $("#exportCompleteDialog");
  if (!dialog.open) dialog.showModal();
  link.focus();
}

function renderExportResults() {
  const results = $("#exportResults");
  results.replaceChildren();
  if (!state.project?.exports?.length) return;
  state.project.exports.forEach((artifact) => {
    const row = document.createElement("div");
    row.className = "download-link";
    const text = document.createElement("span");
    text.textContent = `${artifact.format.toUpperCase()} · ${formatBytes(artifact.size_bytes)}`;
    const link = document.createElement("a");
    link.href = `/api/projects/${state.project.id}/exports/${encodeURIComponent(artifact.filename)}`;
    link.textContent = "Download";
    row.append(text, link);
    results.append(row);
  });
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function relativeDate(value) {
  const date = new Date(value);
  const seconds = Math.round((date - new Date()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const divisions = [[60, "second"], [60, "minute"], [24, "hour"], [7, "day"], [4.345, "week"], [12, "month"], [Infinity, "year"]];
  let duration = seconds;
  for (const [amount, unit] of divisions) {
    if (Math.abs(duration) < amount) return formatter.format(Math.round(duration), unit);
    duration /= amount;
  }
}

let toastTimer;
function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 5000);
}
