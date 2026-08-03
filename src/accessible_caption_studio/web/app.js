const state = {
  project: null,
  projects: [],
  undo: [],
  activeJob: null,
  pollTimer: null,
  saveTimer: null,
  overlapProposal: null,
  speakerProposal: null,
  speakerProposalJobId: null,
  transcriptProposal: null,
  transcriptProposalJobId: null,
  speakerEvidence: [],
  evidenceWindow: null,
  followPlayback: true,
  followPlaybackSuspended: false,
  playbackCueId: null,
};

const $ = (selector) => document.querySelector(selector);
const homeView = $("#homeView");
const workspaceView = $("#workspaceView");
const mediaPlayer = $("#mediaPlayer");
const audioPlayer = $("#audioPlayer");
const themeStorageKey = "accessible-caption-theme";
const activeSpeakerStorageKey = "accessible-caption-active-speaker";
const followPlaybackStorageKey = "accessible-caption-follow-playback";
const youtubeBrowserSignInStorageKey = "accessible-caption-youtube-browser-sign-in";
const youtubeCookieBrowserStorageKey = "accessible-caption-youtube-cookie-browser";

document.addEventListener("DOMContentLoaded", init);

async function init() {
  applyTheme(document.documentElement.dataset.theme || "light", false);
  try { $("#activeSpeakerSetting").checked = localStorage.getItem(activeSpeakerStorageKey) === "true"; } catch (_) {}
  try { state.followPlayback = localStorage.getItem(followPlaybackStorageKey) !== "false"; } catch (_) {}
  restoreBrowserSignIn();
  bindEvents();
  updateFollowPlaybackButton();
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
  $("#useBrowserSignIn").addEventListener("change", updateBrowserSignIn);
  $("#cookieBrowser").addEventListener("change", saveBrowserSignIn);
  $("#mediaInput").addEventListener("change", updateFileLabel);
  bindDropZone();
  $("#settingsButton").addEventListener("click", openSettings);
  $("#darkModeSetting").addEventListener("change", (event) => applyTheme(event.target.checked ? "dark" : "light"));
  $("#activeSpeakerSetting").addEventListener("change", toggleActiveSpeaker);
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
  $("#followPlaybackButton").addEventListener("click", toggleFollowPlayback);
  $("#improveTranscriptButton").addEventListener("click", improveTranscript);
  $("#redetectSpeakersButton").addEventListener("click", openSpeakerSetup);
  $("#renameSpeakersButton").addEventListener("click", openRenameSpeakers);
  $("#renameSpeakersForm").addEventListener("submit", saveSpeakerNames);
  $("#closeRenameSpeakers").addEventListener("click", () => $("#renameSpeakersDialog").close());
  $("#cancelRenameSpeakers").addEventListener("click", () => $("#renameSpeakersDialog").close());
  $("#speakerSetupForm").addEventListener("submit", startSpeakerReanalysis);
  document.querySelectorAll('input[name="speakerCountMode"]').forEach((input) =>
    input.addEventListener("change", updateSpeakerCountMode)
  );
  $("#closeSpeakerSetup").addEventListener("click", () => $("#speakerSetupDialog").close());
  $("#cancelSpeakerSetup").addEventListener("click", () => $("#speakerSetupDialog").close());
  $("#applySpeakerProposal").addEventListener("click", applySpeakerProposal);
  $("#discardSpeakerProposal").addEventListener("click", discardSpeakerProposal);
  $("#discardSpeakerProposalTop").addEventListener("click", discardSpeakerProposal);
  $("#applyTranscriptProposal").addEventListener("click", applyTranscriptProposal);
  $("#discardTranscriptProposal").addEventListener("click", discardTranscriptProposal);
  $("#discardTranscriptProposalTop").addEventListener("click", discardTranscriptProposal);
  $("#undoButton").addEventListener("click", undo);
  $("#cancelJob").addEventListener("click", cancelJob);
  $("#applyOverlap").addEventListener("click", applyOverlapProposal);
  $("#discardOverlap").addEventListener("click", discardOverlapProposal);
  $("#discardOverlapTop").addEventListener("click", discardOverlapProposal);
  [mediaPlayer, audioPlayer].forEach((player) => player.addEventListener("timeupdate", syncPlayback));
  document.addEventListener("keydown", playbackKeys);
  ["wheel", "touchstart"].forEach((eventName) =>
    $("#cueList").addEventListener(eventName, suspendTimelineFollowing, { passive: true })
  );
}

function applyTheme(theme, persist = true) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
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
      body: JSON.stringify({
        url: $("#youtubeUrl").value,
        cookie_browser: $("#useBrowserSignIn").checked ? $("#cookieBrowser").value : null,
      }),
    });
    state.project = payload.project;
    showWorkspace();
    monitorJob(payload.job);
    $("#youtubeUrl").value = "";
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(form, false);
  }
}

function restoreBrowserSignIn() {
  try {
    $("#useBrowserSignIn").checked = localStorage.getItem(youtubeBrowserSignInStorageKey) === "true";
    const browser = localStorage.getItem(youtubeCookieBrowserStorageKey);
    if (["brave", "chrome", "safari", "firefox", "edge"].includes(browser)) {
      $("#cookieBrowser").value = browser;
    }
  } catch (_) { /* Browser storage may be unavailable in private mode. */ }
  updateBrowserSignIn(false);
}

function updateBrowserSignIn(persist = true) {
  const enabled = $("#useBrowserSignIn").checked;
  $("#browserChoice").hidden = !enabled;
  $("#cookieBrowser").disabled = !enabled;
  if (persist) saveBrowserSignIn();
}

function saveBrowserSignIn() {
  try {
    localStorage.setItem(youtubeBrowserSignInStorageKey, String($("#useBrowserSignIn").checked));
    localStorage.setItem(youtubeCookieBrowserStorageKey, $("#cookieBrowser").value);
  } catch (_) { /* The choice still applies for this session. */ }
}

function setBusy(form, busy, label = "") {
  form.querySelectorAll("button, input, select").forEach((element) => { element.disabled = busy; });
  const submit = form.querySelector("button[type=submit]");
  if (!submit) return;
  if (!submit.dataset.label) submit.dataset.label = submit.textContent;
  submit.textContent = busy ? label : submit.dataset.label;
  if (!busy && form.id === "youtubeForm") updateBrowserSignIn(false);
}

async function openProject(id) {
  try {
    state.project = await api(`/api/projects/${id}`);
    showWorkspace();
    if (state.project.latest_job_id) {
      const job = await api(`/api/projects/${id}/jobs/${state.project.latest_job_id}`);
      if (["queued", "running", "cancelling"].includes(job.state)) monitorJob(job);
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
  state.speakerEvidence = [];
  state.evidenceWindow = null;
  $("#renameSpeakersButton").disabled = !project.cues.some((cue) => cue.speaker);
}

function renderCues() {
  const list = $("#cueList");
  list.replaceChildren();
  state.playbackCueId = null;
  $("#emptyCues").hidden = state.project.cues.length > 0;
  const flagged = new Set(state.project.findings.filter((item) => item.cue_id).map((item) => item.cue_id));
  state.project.cues.forEach((cue, index) => {
    const row = document.createElement("article");
    row.className = `cue-row${flagged.has(cue.id) ? " flagged" : ""}`;
    row.dataset.cueId = cue.id;
    row.id = `cue-${cue.id}`;
    if (cue.overlap_group_id) {
      row.classList.add("simultaneous");
      const badge = document.createElement("span");
      badge.className = "simultaneous-badge";
      badge.textContent = "Simultaneous speech";
      row.append(badge);
    }

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
    const turn = bestSpeakerTurn(cue);
    const evidence = document.createElement("span");
    evidence.className = "evidence-badge";
    evidence.textContent = ({
      voice_face: "Voice + face",
      voice_only: "Voice only",
      face_only: "Face only",
      uncertain: "Uncertain",
      audio_visual: "Voice + face",
      visual_fallback: "Face only",
    })[turn?.method] || "Voice only";
    const display = state.project.speaker_names?.[cue.speaker];
    if (display) speaker.title = `Displayed as ${display}`;
    meta.append(speaker, confidence, evidence);

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
      actionButton("Merge next", () => mergeCue(index), index === state.project.cues.length - 1 || Boolean(cue.overlap_group_id)),
      cue.overlap_group_id
        ? actionButton("Ungroup simultaneous", () => ungroupCue(index))
        : actionButton("Group with next", () => groupWithNext(index), index === state.project.cues.length - 1),
      actionButton("Analyze overlapping voices", () => analyzeOverlap(index)),
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
  state.project.cues.push({ id: crypto.randomUUID().replaceAll("-", ""), start, end: Math.min(start + 2, state.project.media?.duration || start + 2), text: "New caption", speaker: null, source: "manual", confidence: null, sound_event_id: null, overlap_group_id: null });
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

function groupWithNext(index) {
  const cue = state.project.cues[index];
  const next = state.project.cues[index + 1];
  if (!cue || !next) return;
  remember();
  const group = crypto.randomUUID().replaceAll("-", "");
  const start = Math.min(cue.start, next.start);
  const end = Math.max(cue.end, next.end);
  [cue, next].forEach((item) => {
    item.start = start;
    item.end = end;
    item.overlap_group_id = group;
    item.source = "manual";
  });
  renderCues();
  scheduleSave();
}

function ungroupCue(index) {
  const group = state.project.cues[index]?.overlap_group_id;
  if (!group) return;
  remember();
  state.project.cues.forEach((cue) => {
    if (cue.overlap_group_id === group) cue.overlap_group_id = null;
  });
  renderCues();
  scheduleSave();
}

async function analyzeOverlap(index) {
  const cue = state.project.cues[index];
  if (!cue) return;
  try {
    await saveProject();
    const job = await api(`/api/projects/${state.project.id}/analyze-overlap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start: cue.start, end: cue.end }),
    });
    monitorJob(job);
  } catch (error) { toast(error.message); }
}

function showOverlapProposal(result) {
  state.overlapProposal = result;
  const container = $("#overlapProposal");
  container.replaceChildren();
  result.cues.forEach((cue, index) => {
    const item = document.createElement("section");
    const heading = document.createElement("strong");
    heading.textContent = `Voice ${index + 1}`;
    const speaker = document.createElement("input");
    speaker.setAttribute("aria-label", `Proposed voice ${index + 1} speaker`);
    speaker.value = cue.speaker || `Speaker ${index + 1}`;
    speaker.addEventListener("input", () => { cue.speaker = speaker.value; });
    const text = document.createElement("textarea");
    text.setAttribute("aria-label", `Proposed voice ${index + 1} caption text`);
    text.value = cue.text;
    text.addEventListener("input", () => { cue.text = text.value; });
    item.append(heading, speaker, text);
    container.append(item);
  });
  $("#overlapDialog").showModal();
}

async function applyOverlapProposal() {
  const result = state.overlapProposal;
  if (!result) return;
  if (result.cues.some((cue) => !cue.speaker?.trim() || !cue.text?.trim())) {
    toast("Both proposed lines need a speaker and caption text.");
    return;
  }
  remember();
  const replaced = new Set(result.replace_cue_ids || []);
  state.project.cues = state.project.cues.filter((cue) => !replaced.has(cue.id));
  state.project.cues.push(...result.cues);
  state.project.cues.sort((left, right) => left.start - right.start || left.end - right.end);
  $("#overlapDialog").close();
  state.overlapProposal = null;
  renderCues();
  await saveProject();
  toast("Two simultaneous speaker lines applied.");
}

function discardOverlapProposal() {
  state.overlapProposal = null;
  $("#overlapDialog").close();
  toast("Overlap proposal discarded. Original captions were not changed.");
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
  cue.overlap_group_id = null;
  second.overlap_group_id = null;
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
      body: JSON.stringify({ name: $("#projectTitle").value, cues: state.project.cues, speaker_names: state.project.speaker_names || {} }),
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

function openSpeakerSetup() {
  if (!state.project?.words?.length) {
    toast("Run automatic caption analysis before re-detecting speakers.");
    return;
  }
  const exact = state.project.expected_speaker_count;
  const mode = exact ? "exact" : "auto";
  const radio = document.querySelector(`input[name="speakerCountMode"][value="${mode}"]`);
  if (radio) radio.checked = true;
  $("#exactSpeakerCount").value = exact || 2;
  updateSpeakerCountMode();
  $("#speakerSetupDialog").showModal();
}

function updateSpeakerCountMode() {
  const mode = document.querySelector('input[name="speakerCountMode"]:checked')?.value;
  $("#exactSpeakerCount").disabled = mode !== "exact";
}

async function startSpeakerReanalysis(event) {
  event.preventDefault();
  const mode = document.querySelector('input[name="speakerCountMode"]:checked')?.value;
  const exact = Number($("#exactSpeakerCount").value);
  if (mode === "exact" && (!Number.isInteger(exact) || exact < 1 || exact > 8)) {
    toast("Choose an exact speaker count from 1 to 8.");
    return;
  }
  try {
    await saveProject();
    const job = await api(`/api/projects/${state.project.id}/reanalyze-speakers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_speaker_count: mode === "exact" ? exact : null }),
    });
    $("#speakerSetupDialog").close();
    monitorJob(job);
  } catch (error) { toast(error.message); }
}

function showSpeakerProposal(result, jobId) {
  state.speakerProposal = result;
  state.speakerProposalJobId = jobId;
  const summary = result.change_summary || {};
  const fusion = result.fusion_summary || {};
  const nameWarning = result.name_review_warnings?.length
    ? ` ${result.name_review_warnings.join(" ")}`
    : "";
  $("#speakerProposalSummary").textContent = `${result.detected_count} ${result.detected_count === 1 ? "speaker was" : "speakers were"} detected from ${fusion.voice_cluster_count || 0} voice clusters and ${fusion.face_identity_count || 0} recurring speaking faces. Your saved captions remain unchanged until you apply this preview.${nameWarning}`;
  const stats = $("#speakerChangeStats");
  stats.replaceChildren();
  [
    ["Voice clusters", fusion.voice_cluster_count || 0],
    ["Face identities", fusion.face_identity_count || 0],
    ["Final speakers", fusion.final_speaker_count || result.detected_count || 0],
    ["Label changes", summary.label_changes || 0],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    const strong = document.createElement("strong");
    const span = document.createElement("span");
    strong.textContent = value;
    span.textContent = label;
    item.append(strong, span);
    stats.append(item);
  });

  const list = $("#speakerProposalList");
  list.replaceChildren();
  const originals = new Map(state.project.cues.map((cue) => [cue.id, cue]));
  const changed = result.cues.filter((cue) => {
    const original = originals.get(cue.id);
    return !original || original.speaker !== cue.speaker || original.text !== cue.text
      || original.start !== cue.start || original.end !== cue.end;
  });
  (changed.length ? changed : result.cues.slice(0, 8)).slice(0, 100).forEach((cue) => {
    const original = originals.get(cue.id);
    const row = document.createElement("article");
    const time = document.createElement("span");
    const before = document.createElement("p");
    const after = document.createElement("p");
    time.textContent = `${Number(cue.start).toFixed(3)}–${Number(cue.end).toFixed(3)}`;
    before.textContent = original
      ? `Before: ${original.speaker || "No speaker"}: ${original.text}`
      : "Before: New split caption";
    after.textContent = `After: ${cue.speaker || "No speaker"}: ${cue.text}`;
    row.append(time, before, after);
    list.append(row);
  });
  if (changed.length > 100) {
    const note = document.createElement("p");
    note.textContent = `${changed.length - 100} additional changes are included.`;
    list.append(note);
  }
  $("#speakerProposalDialog").showModal();
}

async function applySpeakerProposal() {
  if (!state.speakerProposalJobId) return;
  try {
    remember();
    state.project = await api(`/api/projects/${state.project.id}/speaker-proposals/${state.speakerProposalJobId}/apply`, { method: "POST" });
    $("#speakerProposalDialog").close();
    state.speakerProposal = null;
    state.speakerProposalJobId = null;
    renderProject();
    toast("Speaker changes applied and saved.");
  } catch (error) { toast(error.message); }
}

function discardSpeakerProposal() {
  state.speakerProposal = null;
  state.speakerProposalJobId = null;
  $("#speakerProposalDialog").close();
  toast("Speaker preview discarded. Saved captions were not changed.");
}

async function improveTranscript() {
  if (!state.project?.words?.length) {
    toast("Run automatic caption analysis before improving the transcript.");
    return;
  }
  try {
    await saveProject();
    const job = await api(`/api/projects/${state.project.id}/repair-transcript`, {
      method: "POST",
    });
    monitorJob(job);
  } catch (error) { toast(error.message); }
}

function showTranscriptProposal(result, jobId) {
  state.transcriptProposal = result;
  state.transcriptProposalJobId = jobId;
  const recovery = result.recovery_summary || {};
  const conflicts = result.edit_conflicts || [];
  $("#transcriptProposalSummary").textContent = `${recovery.inserted || 0} missing words recovered and ${recovery.replaced || 0} low-confidence words improved across ${(recovery.regions || []).length} regions. ${conflicts.length ? `${conflicts.length} edited captions were preserved for review.` : "Saved captions remain unchanged until you apply this preview."}`;
  const stats = $("#transcriptChangeStats");
  stats.replaceChildren();
  [
    ["Recovered words", recovery.inserted || 0],
    ["Improved words", recovery.replaced || 0],
    ["Checked regions", (recovery.regions || []).length],
    ["Edit conflicts", conflicts.length],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    const strong = document.createElement("strong");
    const span = document.createElement("span");
    strong.textContent = value;
    span.textContent = label;
    item.append(strong, span);
    stats.append(item);
  });
  const list = $("#transcriptProposalList");
  list.replaceChildren();
  const originals = new Map(state.project.cues.map((cue) => [cue.id, cue]));
  const changed = result.cues.filter((cue) => {
    const original = originals.get(cue.id);
    return !original || original.speaker !== cue.speaker || original.text !== cue.text
      || original.start !== cue.start || original.end !== cue.end;
  });
  (changed.length ? changed : result.cues.slice(0, 8)).slice(0, 100).forEach((cue) => {
    const original = originals.get(cue.id);
    const row = document.createElement("article");
    const time = document.createElement("span");
    const before = document.createElement("p");
    const after = document.createElement("p");
    time.textContent = `${Number(cue.start).toFixed(3)}–${Number(cue.end).toFixed(3)}`;
    before.textContent = original
      ? `Before: ${original.speaker || "No speaker"}: ${original.text}`
      : "Before: Missing dialogue";
    after.textContent = `After: ${cue.speaker || "No speaker"}: ${cue.text}`;
    row.append(time, before, after);
    list.append(row);
  });
  $("#transcriptProposalDialog").showModal();
}

async function applyTranscriptProposal() {
  if (!state.transcriptProposalJobId) return;
  try {
    remember();
    state.project = await api(`/api/projects/${state.project.id}/transcript-proposals/${state.transcriptProposalJobId}/apply`, { method: "POST" });
    $("#transcriptProposalDialog").close();
    state.transcriptProposal = null;
    state.transcriptProposalJobId = null;
    renderProject();
    toast("Recovered dialogue and speaker changes applied and saved.");
  } catch (error) { toast(error.message); }
}

function discardTranscriptProposal() {
  state.transcriptProposal = null;
  state.transcriptProposalJobId = null;
  $("#transcriptProposalDialog").close();
  toast("Transcript preview discarded. Saved captions were not changed.");
}

function renderFindings() {
  const list = $("#findingList");
  const overview = $("#findingOverview");
  list.replaceChildren();
  overview.replaceChildren();
  const findings = state.project.findings || [];
  $("#findingCount").textContent = `${findings.length} ${findings.length === 1 ? "finding" : "findings"}`;
  if (!findings.length) {
    overview.hidden = true;
    list.removeAttribute("tabindex");
    const success = document.createElement("p");
    success.className = "success-note";
    success.textContent = "No automatic accessibility issues found.";
    list.append(success);
    return;
  }
  overview.hidden = false;
  list.tabIndex = 0;
  ["error", "warning", "info"].forEach((severity) => {
    const count = findings.filter((finding) => finding.severity === severity).length;
    if (!count) return;
    const summary = document.createElement("span");
    summary.className = `finding-summary ${severity}`;
    summary.textContent = `${count} ${severity}${count === 1 ? "" : "s"}`;
    overview.append(summary);
  });
  const severityOrder = { error: 0, warning: 1, info: 2 };
  [...findings]
    .sort((left, right) => severityOrder[left.severity] - severityOrder[right.severity])
    .forEach((finding) => {
      const item = document.createElement("div");
      item.className = `finding ${finding.severity}`;
      const severity = document.createElement("span");
      severity.className = "finding-severity";
      severity.textContent = finding.severity;
      const message = document.createElement("p");
      message.textContent = finding.message;
      item.append(severity, message);
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
function displaySpeaker(speaker) { return state.project?.speaker_names?.[speaker] || speaker; }
function bestSpeakerTurn(cue) {
  return (state.project?.speakers || []).reduce((best, turn) => {
    const overlap = Math.max(0, Math.min(cue.end, turn.end) - Math.max(cue.start, turn.start));
    return overlap > (best?.overlap || 0) ? { ...turn, overlap } : best;
  }, null);
}
function seekTo(seconds) { const player = activePlayer(); if (player?.src) player.currentTime = seconds; }

function updateFollowPlaybackButton() {
  const button = $("#followPlaybackButton");
  if (!button) return;
  const activelyFollowing = state.followPlayback && !state.followPlaybackSuspended;
  button.setAttribute("aria-pressed", String(activelyFollowing));
  button.textContent = activelyFollowing
    ? "Following playback"
    : state.followPlayback ? "Resume following" : "Follow playback";
}

function toggleFollowPlayback() {
  if (state.followPlayback && state.followPlaybackSuspended) {
    state.followPlaybackSuspended = false;
  } else {
    state.followPlayback = !state.followPlayback;
    state.followPlaybackSuspended = false;
    try { localStorage.setItem(followPlaybackStorageKey, String(state.followPlayback)); }
    catch (_) { /* The selection still applies for this session. */ }
  }
  state.playbackCueId = null;
  updateFollowPlaybackButton();
  if (state.followPlayback) syncPlayback();
}

function suspendTimelineFollowing() {
  if (!state.followPlayback || activePlayer()?.paused) return;
  state.followPlaybackSuspended = true;
  updateFollowPlaybackButton();
}

function followActiveCue(cue) {
  if (!cue || !state.followPlayback || state.followPlaybackSuspended) return;
  if (state.playbackCueId === cue.id) return;
  state.playbackCueId = cue.id;
  const list = $("#cueList");
  const focused = document.activeElement?.closest?.(".cue-row");
  if (focused && list.contains(focused)) return;
  const row = document.querySelector(`[data-cue-id="${CSS.escape(cue.id)}"]`);
  if (!row) return;
  const listBox = list.getBoundingClientRect();
  const rowBox = row.getBoundingClientRect();
  const rowTopInsideList = rowBox.top - listBox.top + list.scrollTop;
  const target = rowTopInsideList - (list.clientHeight - rowBox.height) / 2;
  const maximum = Math.max(0, list.scrollHeight - list.clientHeight);
  list.scrollTo({
    top: Math.min(maximum, Math.max(0, target)),
    behavior: "auto",
  });
}

function syncPlayback() {
  if (!state.project) return;
  const time = activePlayer().currentTime;
  const active = state.project.cues.filter((cue) => time >= cue.start && time < cue.end);
  const primary = active[0];
  const visible = primary?.overlap_group_id
    ? active.filter((cue) => cue.overlap_group_id === primary.overlap_group_id)
    : primary ? [primary] : [];
  $("#captionOverlay").textContent = visible
    .map((cue) => `${cue.speaker ? `${displaySpeaker(cue.speaker)}: ` : ""}${cue.text}`)
    .join("\n");
  updateActiveFace(time);
  document.querySelectorAll(".cue-row.active").forEach((row) => {
    row.classList.remove("active");
    row.removeAttribute("aria-current");
  });
  visible.forEach((cue) => {
    const row = document.querySelector(`[data-cue-id="${CSS.escape(cue.id)}"]`);
    row?.classList.add("active");
    row?.setAttribute("aria-current", "true");
  });
  followActiveCue(primary);
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
    if (["queued", "running", "cancelling"].includes(job.state)) {
      state.pollTimer = setTimeout(pollJob, 1100);
      return;
    }
    if (job.state === "completed") {
      state.project = await api(`/api/projects/${state.project.id}`);
      renderProject();
      if (job.kind === "mp4-export") {
        const artifact = state.project.exports.find((item) => item.format === "mp4");
        if (artifact) showExportComplete(artifact);
      } else if (job.kind === "overlap-analysis" && job.result) {
        showOverlapProposal(job.result);
      } else if (job.kind === "speaker-reanalysis" && job.result) {
        showSpeakerProposal(job.result, job.id);
      } else if (job.kind === "transcript-repair" && job.result) {
        showTranscriptProposal(job.result, job.id);
      } else {
        toast("Automatic captions are ready.");
      }
    } else if (job.state === "failed") {
      toast(job.error || "Processing could not be completed.");
    } else if (job.state === "cancelled") {
      toast("Processing cancelled. Saved work was not changed.");
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
  $("#cancelJob").hidden = !["queued", "running", "cancelling"].includes(job.state);
  $("#cancelJob").disabled = job.state === "cancelling";
  $("#cancelJob").textContent = job.state === "cancelling" ? "Cancelling…" : "Cancel";
}

async function cancelJob() {
  if (!state.activeJob) return;
  try {
    state.activeJob = await api(`/api/projects/${state.project.id}/jobs/${state.activeJob.id}/cancel`, { method: "POST" });
    updateJobPanel(state.activeJob);
    toast("Cancellation requested…");
  } catch (error) { toast(error.message); }
}

function toggleActiveSpeaker(event) {
  try { localStorage.setItem(activeSpeakerStorageKey, String(event.target.checked)); } catch (_) {}
  if (!event.target.checked) $("#activeFaceOverlay").hidden = true;
  else syncPlayback();
}

async function updateActiveFace(time) {
  const overlay = $("#activeFaceOverlay");
  if (!$("#activeSpeakerSetting").checked || !state.project?.media?.has_video) { overlay.hidden = true; return; }
  const windowStart = Math.floor(time / 30) * 30;
  if (state.evidenceWindow !== windowStart) {
    state.evidenceWindow = windowStart;
    try {
      const data = await api(`/api/projects/${state.project.id}/speaker-evidence?start=${windowStart}&end=${windowStart + 30}`);
      state.speakerEvidence = data.tracks || [];
    } catch (_) { state.speakerEvidence = []; }
  }
  let best = null;
  state.speakerEvidence.forEach((track) => track.samples.forEach((sample) => {
    const distance = Math.abs(sample.time - time);
    if (distance <= .22 && sample.active_confidence >= .35 && (!best || sample.active_confidence > best.sample.active_confidence)) best = { track, sample };
  }));
  if (!best) { overlay.hidden = true; return; }
  overlay.style.left = `${best.sample.x * 100}%`;
  overlay.style.top = `${best.sample.y * 100}%`;
  overlay.style.width = `${best.sample.width * 100}%`;
  overlay.style.height = `${best.sample.height * 100}%`;
  overlay.querySelector("span").textContent = displaySpeaker(best.track.speaker) || "Possible speaker";
  overlay.hidden = false;
}

function openRenameSpeakers() {
  const speakers = [...new Set(state.project.cues.map((cue) => cue.speaker).filter(Boolean))].sort();
  const fields = $("#speakerNameFields");
  fields.replaceChildren();
  speakers.forEach((speaker) => {
    const label = document.createElement("label");
    label.append(document.createTextNode(speaker));
    const input = document.createElement("input");
    input.name = speaker;
    input.maxLength = 80;
    input.placeholder = `Optional name for ${speaker}`;
    input.value = state.project.speaker_names?.[speaker] || "";
    label.append(input);
    fields.append(label);
  });
  $("#renameSpeakersDialog").showModal();
}

async function saveSpeakerNames(event) {
  event.preventDefault();
  const names = {};
  new FormData(event.currentTarget).forEach((value, key) => { if (String(value).trim()) names[key] = String(value).trim(); });
  state.project.speaker_names = names;
  await saveProject();
  $("#renameSpeakersDialog").close();
  renderProject();
  toast("Speaker names saved.");
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
    $("#speakerModelStatus").textContent = health.speaker_token_required
      ? "Speaker labeling needs additional setup."
      : "Token-free local speaker labeling is enabled.";
  } catch (error) { toast(error.message); }
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
