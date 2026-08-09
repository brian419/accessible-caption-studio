const state = {
  project: null,
  projects: [],
  undo: [],
  activeJob: null,
  activeJobProjectId: null,
  activeJobProjectName: "",
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
  deleteProjectId: null,
  deleteTriggerButton: null,
  captionSamplePreview: false,
  captionFonts: [],
  captionFontsLoaded: false,
  captionFontsLoading: false,
  captionFontError: "",
  captionFontFilter: "all",
  captionFontVisibleCount: 80,
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
const transcriptionQualityStorageKey = "accessible-caption-transcription-quality";
const activeJobStates = new Set(["queued", "running", "cancelling"]);
const captionStyleStoragePrefix = "accessible-caption-style:";
const captionFontFavoritesStorageKey = "accessible-caption-font-favorites";
const captionFontRecentsStorageKey = "accessible-caption-font-recents";
const captionFontRenderBatchSize = 80;
const defaultCaptionStyle = Object.freeze({
  preset: "classic",
  font_family: "Arial",
  font_style: "Bold",
  bold: true,
  font_size_percent: 7.5,
  max_width_percent: 88,
  text_color: "#FFFFFF",
  background_color: "#000000",
  background_opacity: 0.78,
  outline_color: "#000000",
  outline_size_percent: 0.16,
  shadow_color: "#000000",
  shadow_size_percent: 0.18,
  padding_percent: 1.0,
  line_spacing_percent: 0.7,
  position: "bottom",
  alignment: "center",
  vertical_margin_percent: 10,
});
const captionStylePresets = Object.freeze({
  classic: { ...defaultCaptionStyle },
  high_contrast: {
    ...defaultCaptionStyle,
    preset: "high_contrast",
    font_size_percent: 8.2,
    text_color: "#FFFF00",
    background_opacity: 0.95,
    outline_size_percent: 0.2,
    shadow_size_percent: 0,
    padding_percent: 1.2,
  },
  clean: {
    ...defaultCaptionStyle,
    preset: "clean",
    font_family: "Helvetica",
    font_style: "Bold",
    font_size_percent: 7.0,
    background_color: "#111827",
    background_opacity: 0.55,
    outline_size_percent: 0,
    shadow_size_percent: 0.16,
    padding_percent: 0.8,
  },
  broadcast: {
    ...defaultCaptionStyle,
    preset: "broadcast",
    font_family: "Georgia",
    font_style: "Bold",
    font_size_percent: 7.6,
    background_color: "#172554",
    background_opacity: 0.88,
    outline_size_percent: 0.12,
    shadow_size_percent: 0.14,
    padding_percent: 1.15,
  },
});

document.addEventListener("DOMContentLoaded", init);

async function init() {
  applyTheme(document.documentElement.dataset.theme || "light", false);
  try { $("#activeSpeakerSetting").checked = localStorage.getItem(activeSpeakerStorageKey) === "true"; } catch (_) {}
  try { state.followPlayback = localStorage.getItem(followPlaybackStorageKey) !== "false"; } catch (_) {}
  restoreBrowserSignIn();
  restoreTranscriptionQuality();
  bindEvents();
  setupJobPanelStickiness();
  updateFollowPlaybackButton();
  await loadProjects();
}

function bindEvents() {
  $("#homeButton").addEventListener("click", showHome);
  $("#backButton").addEventListener("click", showHome);
  $("#refreshProjects").addEventListener("click", loadProjects);
  $("#deleteAllProjects").addEventListener("click", openDeleteAllProjectsDialog);
  $("#deleteAllConfirmDialog").addEventListener("close", handleDeleteAllProjectsDialogClose);
  $("#deleteConfirmDialog").addEventListener("close", handleDeleteProjectDialogClose);
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
  $("#transcriptionQualitySetting").addEventListener("change", saveTranscriptionQuality);
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
  mediaPlayer.addEventListener("loadedmetadata", refreshCaptionLayout);
  bindCaptionStyleControls();
  window.addEventListener("resize", refreshCaptionLayout);
  if (window.ResizeObserver) new ResizeObserver(refreshCaptionLayout).observe($("#mediaStage"));
  document.addEventListener("keydown", playbackKeys);
  ["wheel", "touchstart"].forEach((eventName) =>
    $("#cueList").addEventListener(eventName, suspendTimelineFollowing, { passive: true })
  );
}


function clampNumber(value, minimum, maximum, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(maximum, Math.max(minimum, number)) : fallback;
}

function normalizedHex(value, fallback) {
  return /^#[0-9a-f]{6}$/i.test(String(value || "")) ? String(value).toUpperCase() : fallback;
}

function normalizedCaptionFontName(value, fallback, maximumLength) {
  const cleaned = String(value || "").replace(/[\u0000-\u001f\u007f]/g, "").replace(/\s+/g, " ").trim();
  return cleaned ? cleaned.slice(0, maximumLength) : fallback;
}

function captionFontStyleDetails(value) {
  const name = normalizedCaptionFontName(value, "Regular", 80);
  const normalized = name.toLowerCase().replace(/[-_]+/g, " ");
  let weight = 400;
  if (/thin|hairline/.test(normalized)) weight = 100;
  else if (/extra light|ultra light|extralight|ultralight/.test(normalized)) weight = 200;
  else if (/light/.test(normalized)) weight = 300;
  else if (/medium/.test(normalized)) weight = 500;
  else if (/semi bold|semibold|demi bold|demibold/.test(normalized)) weight = 600;
  else if (/extra bold|extrabold|ultra bold/.test(normalized)) weight = 800;
  else if (/black|heavy/.test(normalized)) weight = 900;
  else if (/bold/.test(normalized)) weight = 700;
  return {
    name,
    weight,
    italic: /italic|oblique/.test(normalized),
  };
}

function captionFontFamilyCss(value) {
  const escaped = normalizedCaptionFontName(value, defaultCaptionStyle.font_family, 120)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\"');
  return `"${escaped}", Arial, sans-serif`;
}

function normalizeCaptionStyle(value = {}) {
  const style = { ...defaultCaptionStyle, ...(value || {}) };
  const presets = ["classic", "high_contrast", "clean", "broadcast", "custom"];
  const fontFamily = normalizedCaptionFontName(style.font_family, defaultCaptionStyle.font_family, 120);
  const fontStyle = normalizedCaptionFontName(
    style.font_style,
    style.bold === false ? "Regular" : defaultCaptionStyle.font_style,
    80,
  );
  return {
    preset: presets.includes(style.preset) ? style.preset : "custom",
    font_family: fontFamily,
    font_style: fontStyle,
    bold: captionFontStyleDetails(fontStyle).weight >= 600,
    font_size_percent: clampNumber(style.font_size_percent, 4, 12, defaultCaptionStyle.font_size_percent),
    max_width_percent: clampNumber(style.max_width_percent, 40, 96, defaultCaptionStyle.max_width_percent),
    text_color: normalizedHex(style.text_color, defaultCaptionStyle.text_color),
    background_color: normalizedHex(style.background_color, defaultCaptionStyle.background_color),
    background_opacity: clampNumber(style.background_opacity, 0, 1, defaultCaptionStyle.background_opacity),
    outline_color: normalizedHex(style.outline_color, defaultCaptionStyle.outline_color),
    outline_size_percent: clampNumber(style.outline_size_percent, 0, .6, defaultCaptionStyle.outline_size_percent),
    shadow_color: normalizedHex(style.shadow_color, defaultCaptionStyle.shadow_color),
    shadow_size_percent: clampNumber(style.shadow_size_percent, 0, .8, defaultCaptionStyle.shadow_size_percent),
    padding_percent: clampNumber(style.padding_percent, .2, 3, defaultCaptionStyle.padding_percent),
    line_spacing_percent: clampNumber(style.line_spacing_percent, 0, 3, defaultCaptionStyle.line_spacing_percent),
    position: ["top", "middle", "bottom"].includes(style.position) ? style.position : defaultCaptionStyle.position,
    alignment: ["left", "center", "right"].includes(style.alignment) ? style.alignment : defaultCaptionStyle.alignment,
    vertical_margin_percent: clampNumber(style.vertical_margin_percent, 2, 25, defaultCaptionStyle.vertical_margin_percent),
  };
}

function captionStyleStorageKey(projectId) {
  return `${captionStyleStoragePrefix}${projectId}`;
}

function loadCaptionStyle(project) {
  try {
    const stored = JSON.parse(localStorage.getItem(captionStyleStorageKey(project.id)) || "null");
    if (stored) return normalizeCaptionStyle(stored);
  } catch (_) { /* Fall back to the project data. */ }
  return normalizeCaptionStyle(project.caption_style);
}

function storeCaptionStyle(projectId, style) {
  try { localStorage.setItem(captionStyleStorageKey(projectId), JSON.stringify(style)); }
  catch (_) { /* Project saving still remains the primary persistence path. */ }
}

function bindCaptionStyleControls() {
  $("#captionStylePreset").addEventListener("change", applyCaptionStylePreset);
  document.querySelectorAll("[data-caption-style]").forEach((control) => {
    const eventName = control.matches('input[type="range"], input[type="color"]') ? "input" : "change";
    control.addEventListener(eventName, updateCaptionStyleFromControls);
  });
  $("#captionFontButton").addEventListener("click", toggleCaptionFontPicker);
  $("#captionFontSearch").addEventListener("input", () => {
    resetCaptionFontRenderWindow();
    renderCaptionFontList();
  });
  $("#captionFontClearSearch").addEventListener("click", () => {
    $("#captionFontSearch").value = "";
    resetCaptionFontRenderWindow();
    renderCaptionFontList();
    $("#captionFontSearch").focus();
  });
  $("#captionFontClose").addEventListener("click", closeCaptionFontPicker);
  $("#captionFontDialog").addEventListener("close", () => {
    $("#captionFontButton").setAttribute("aria-expanded", "false");
  });
  $("#captionFontDialog").addEventListener("click", (event) => {
    if (event.target === $("#captionFontDialog")) closeCaptionFontPicker();
  });
  $("#captionFontSearch").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const first = $("#captionFontList [data-font-family]");
    if (first) {
      event.preventDefault();
      chooseCaptionFont(first.dataset.fontFamily);
    }
  });
  document.querySelectorAll("[data-font-filter]").forEach((button) => {
    button.addEventListener("click", () => setCaptionFontFilter(button.dataset.fontFilter));
  });
  $("#captionFontList").addEventListener("click", handleCaptionFontListClick);
  $("#captionFontList").addEventListener("scroll", loadMoreCaptionFontsOnScroll, { passive: true });
  $("#captionPreviewSample").addEventListener("change", (event) => {
    state.captionSamplePreview = event.target.checked;
    syncPlayback();
  });
  $("#resetCaptionStyle").addEventListener("click", () => {
    if (!state.project) return;
    state.project.caption_style = normalizeCaptionStyle(defaultCaptionStyle);
    renderCaptionStyleControls();
    applyCaptionStyle();
    syncPlayback();
    storeCaptionStyle(state.project.id, state.project.caption_style);
    scheduleSave();
  });
}


function readCaptionFontList(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string").slice(0, 40) : [];
  } catch (_) { return []; }
}

function writeCaptionFontList(key, values) {
  try { localStorage.setItem(key, JSON.stringify(values)); }
  catch (_) { /* Font browsing still works without saved favorites. */ }
}

function captionFontRecord(family) {
  const normalized = String(family || "").toLocaleLowerCase();
  return state.captionFonts.find((font) => font.family.toLocaleLowerCase() === normalized) || null;
}

function captionFontStyles(family) {
  const record = captionFontRecord(family);
  const current = state.project ? normalizeCaptionStyle(state.project.caption_style).font_style : "Regular";
  return record && record.styles.length ? record.styles : [current];
}

function preferredCaptionFontStyle(styles, requested, preferBold) {
  const exact = styles.find((style) => style.toLocaleLowerCase() === String(requested || "").toLocaleLowerCase());
  if (exact) return exact;
  const preference = preferBold
    ? [/^bold$/i, /semi.*bold|demi.*bold/i, /bold/i, /black|heavy/i]
    : [/^regular$/i, /^book$/i, /^normal$/i, /regular|book|normal/i];
  for (const pattern of preference) {
    const match = styles.find((style) => pattern.test(style));
    if (match) return match;
  }
  return styles[0] || (preferBold ? "Bold" : "Regular");
}

function renderCaptionFontStyleOptions() {
  if (!state.project) return;
  const style = normalizeCaptionStyle(state.project.caption_style);
  const select = $("#captionFontStyle");
  const styles = captionFontStyles(style.font_family);
  const selected = preferredCaptionFontStyle(styles, style.font_style, style.bold);
  select.replaceChildren(...styles.map((fontStyle) => {
    const option = document.createElement("option");
    option.value = fontStyle;
    option.textContent = fontStyle;
    return option;
  }));
  select.value = selected;
  if (style.font_style !== selected) {
    state.project.caption_style = normalizeCaptionStyle({ ...style, font_style: selected });
  }
}

function renderCaptionFontButton() {
  if (!state.project) return;
  const style = normalizeCaptionStyle(state.project.caption_style);
  const details = captionFontStyleDetails(style.font_style);
  $("#captionFontFamily").value = style.font_family;
  const name = $("#captionFontButtonName");
  name.textContent = style.font_family;
  name.style.fontFamily = captionFontFamilyCss(style.font_family);
  name.style.fontWeight = String(details.weight);
  name.style.fontStyle = details.italic ? "italic" : "normal";
  $("#captionFontButtonMeta").textContent = style.font_style;
}

async function loadCaptionFonts() {
  if (state.captionFontsLoaded || state.captionFontsLoading) return;
  state.captionFontsLoading = true;
  state.captionFontError = "";
  $("#captionFontResultsCount").textContent = "Scanning installed fonts…";
  try {
    const result = await api("/api/caption-fonts");
    state.captionFonts = Array.isArray(result.fonts)
      ? result.fonts
        .filter((font) => font && typeof font.family === "string")
        .map((font) => ({
          family: normalizedCaptionFontName(font.family, "", 120),
          styles: Array.isArray(font.styles) && font.styles.length
            ? font.styles.map((style) => normalizedCaptionFontName(style, "Regular", 80))
            : ["Regular"],
        }))
        .filter((font) => font.family)
      : [];
    state.captionFontsLoaded = true;
    $("#captionFontCount").textContent = result.export_compatible === false
      ? `${state.captionFonts.length} fallback fonts · Font scan unavailable`
      : `${state.captionFonts.length} installed export-ready fonts`;
    renderCaptionFontStyleOptions();
    renderCaptionFontButton();
    renderCaptionFontList();
  } catch (error) {
    state.captionFontError = error.message || "Installed fonts could not be loaded.";
    $("#captionFontCount").textContent = "Font library unavailable";
    $("#captionFontResultsCount").textContent = state.captionFontError;
    renderCaptionFontList();
  } finally {
    state.captionFontsLoading = false;
  }
}

async function toggleCaptionFontPicker() {
  const dialog = $("#captionFontDialog");
  if (dialog.open) {
    closeCaptionFontPicker();
    return;
  }
  dialog.showModal();
  $("#captionFontButton").setAttribute("aria-expanded", "true");
  resetCaptionFontRenderWindow();
  await loadCaptionFonts();
  renderCaptionFontList();
  requestAnimationFrame(() => $("#captionFontSearch").focus());
}

function closeCaptionFontPicker() {
  const dialog = $("#captionFontDialog");
  if (!dialog || !dialog.open) return;
  dialog.close();
}

function resetCaptionFontRenderWindow() {
  state.captionFontVisibleCount = captionFontRenderBatchSize;
  const list = $("#captionFontList");
  if (list) list.scrollTop = 0;
}

function setCaptionFontFilter(filter) {
  state.captionFontFilter = ["all", "recent", "favorites"].includes(filter) ? filter : "all";
  document.querySelectorAll("[data-font-filter]").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.fontFilter === state.captionFontFilter));
  });
  resetCaptionFontRenderWindow();
  renderCaptionFontList();
}

function loadMoreCaptionFontsOnScroll(event) {
  const list = event.currentTarget;
  if (list.scrollTop + list.clientHeight < list.scrollHeight - 180) return;
  const total = Number(list.dataset.totalFonts || 0);
  if (state.captionFontVisibleCount >= total) return;
  state.captionFontVisibleCount = Math.min(total, state.captionFontVisibleCount + captionFontRenderBatchSize);
  renderCaptionFontList({ preserveScroll: true });
}

function renderCaptionFontList({ preserveScroll = false } = {}) {
  const list = $("#captionFontList");
  if (!list) return;
  const previousScrollTop = preserveScroll ? list.scrollTop : 0;
  list.replaceChildren();
  if (state.captionFontsLoading) {
    $("#captionFontResultsCount").textContent = "Scanning installed fonts…";
    $("#captionFontEmpty").hidden = true;
    return;
  }
  if (state.captionFontError) {
    $("#captionFontResultsCount").textContent = state.captionFontError;
    $("#captionFontEmpty").hidden = true;
    return;
  }
  const query = $("#captionFontSearch").value.trim().toLocaleLowerCase();
  const favorites = readCaptionFontList(captionFontFavoritesStorageKey);
  const recents = readCaptionFontList(captionFontRecentsStorageKey);
  let fonts = [...state.captionFonts];
  if (state.captionFontFilter === "favorites") {
    fonts = fonts.filter((font) => favorites.includes(font.family));
  } else if (state.captionFontFilter === "recent") {
    fonts = recents.map(captionFontRecord).filter(Boolean);
  }
  if (query) {
    fonts = fonts.filter((font) => `${font.family} ${font.styles.join(" ")}`.toLocaleLowerCase().includes(query));
  }

  const visibleFonts = fonts.slice(0, Math.max(captionFontRenderBatchSize, state.captionFontVisibleCount));
  const selectedFamily = state.project ? normalizeCaptionStyle(state.project.caption_style).font_family : "";
  const fragment = document.createDocumentFragment();
  visibleFonts.forEach((font) => {
    const row = document.createElement("div");
    row.className = "caption-font-option";
    row.classList.toggle("is-selected", font.family === selectedFamily);

    const choose = document.createElement("button");
    choose.className = "caption-font-option-main";
    choose.type = "button";
    choose.dataset.fontFamily = font.family;
    choose.setAttribute("role", "option");
    choose.setAttribute("aria-selected", String(font.family === selectedFamily));
    choose.title = `Choose ${font.family}`;
    const name = document.createElement("span");
    name.className = "caption-font-option-name";
    name.textContent = font.family;
    choose.append(name);

    const favorite = document.createElement("button");
    favorite.className = "caption-font-favorite";
    favorite.type = "button";
    favorite.dataset.favoriteFont = font.family;
    const isFavorite = favorites.includes(font.family);
    favorite.classList.toggle("is-favorite", isFavorite);
    favorite.setAttribute("aria-label", `${isFavorite ? "Remove" : "Add"} ${font.family} ${isFavorite ? "from" : "to"} favorites`);
    favorite.setAttribute("aria-pressed", String(isFavorite));
    favorite.textContent = isFavorite ? "★" : "☆";
    row.append(choose, favorite);
    fragment.append(row);
  });
  list.append(fragment);
  list.dataset.totalFonts = String(fonts.length);
  if (preserveScroll) list.scrollTop = previousScrollTop;

  const shown = visibleFonts.length;
  $("#captionFontResultsCount").textContent = shown < fonts.length
    ? `Showing ${shown} of ${fonts.length} fonts`
    : `${fonts.length} ${fonts.length === 1 ? "font" : "fonts"}`;
  $("#captionFontEmpty").hidden = fonts.length > 0;
}

function handleCaptionFontListClick(event) {
  const favoriteButton = event.target.closest("[data-favorite-font]");
  if (favoriteButton) {
    const family = favoriteButton.dataset.favoriteFont;
    const favorites = readCaptionFontList(captionFontFavoritesStorageKey);
    const next = favorites.includes(family)
      ? favorites.filter((item) => item !== family)
      : [family, ...favorites].slice(0, 40);
    writeCaptionFontList(captionFontFavoritesStorageKey, next);
    renderCaptionFontList();
    return;
  }
  const chooseButton = event.target.closest("[data-font-family]");
  if (!chooseButton || !state.project) return;
  chooseCaptionFont(chooseButton.dataset.fontFamily);
}

function chooseCaptionFont(family) {
  if (!state.project) return;
  const current = normalizeCaptionStyle(state.project.caption_style);
  const record = captionFontRecord(family);
  if (!record) return;
  const fontStyle = preferredCaptionFontStyle(record.styles, current.font_style, current.bold);
  state.project.caption_style = normalizeCaptionStyle({
    ...current,
    preset: "custom",
    font_family: family,
    font_style: fontStyle,
  });
  const recents = readCaptionFontList(captionFontRecentsStorageKey).filter((item) => item !== family);
  writeCaptionFontList(captionFontRecentsStorageKey, [family, ...recents].slice(0, 12));
  $("#captionStylePreset").value = "custom";
  renderCaptionStyleControls();
  applyCaptionStyle();
  syncPlayback();
  storeCaptionStyle(state.project.id, state.project.caption_style);
  scheduleSave();
  closeCaptionFontPicker();
}

function applyCaptionStylePreset(event) {
  if (!state.project || event.target.value === "custom") return;
  state.project.caption_style = normalizeCaptionStyle(captionStylePresets[event.target.value]);
  renderCaptionStyleControls();
  applyCaptionStyle();
  syncPlayback();
  storeCaptionStyle(state.project.id, state.project.caption_style);
  scheduleSave();
}

function updateCaptionStyleFromControls() {
  if (!state.project) return;
  state.project.caption_style = normalizeCaptionStyle({
    preset: "custom",
    font_family: $("#captionFontFamily").value,
    font_style: $("#captionFontStyle").value,
    font_size_percent: $("#captionFontSize").value,
    max_width_percent: $("#captionMaxWidth").value,
    text_color: $("#captionTextColor").value,
    background_color: $("#captionBackgroundColor").value,
    background_opacity: $("#captionBackgroundOpacity").value,
    outline_color: $("#captionOutlineColor").value,
    outline_size_percent: $("#captionOutlineSize").value,
    shadow_color: $("#captionShadowColor").value,
    shadow_size_percent: $("#captionShadowSize").value,
    padding_percent: $("#captionPadding").value,
    line_spacing_percent: $("#captionLineSpacing").value,
    position: $("#captionPosition").value,
    alignment: $("#captionAlignment").value,
    vertical_margin_percent: $("#captionVerticalMargin").value,
  });
  $("#captionStylePreset").value = "custom";
  updateCaptionStyleValueLabels();
  applyCaptionStyle();
  syncPlayback();
  storeCaptionStyle(state.project.id, state.project.caption_style);
  scheduleSave();
}

function renderCaptionStyleControls() {
  if (!state.project) return;
  const style = normalizeCaptionStyle(state.project.caption_style);
  state.project.caption_style = style;
  $("#captionStylePreset").value = style.preset;
  $("#captionFontFamily").value = style.font_family;
  $("#captionFontSize").value = style.font_size_percent;
  $("#captionMaxWidth").value = style.max_width_percent;
  renderCaptionFontStyleOptions();
  renderCaptionFontButton();
  $("#captionTextColor").value = style.text_color;
  $("#captionBackgroundColor").value = style.background_color;
  $("#captionBackgroundOpacity").value = style.background_opacity;
  $("#captionOutlineColor").value = style.outline_color;
  $("#captionOutlineSize").value = style.outline_size_percent;
  $("#captionShadowColor").value = style.shadow_color;
  $("#captionShadowSize").value = style.shadow_size_percent;
  $("#captionPadding").value = style.padding_percent;
  $("#captionLineSpacing").value = style.line_spacing_percent;
  $("#captionPosition").value = style.position;
  $("#captionAlignment").value = style.alignment;
  $("#captionVerticalMargin").value = style.vertical_margin_percent;
  updateCaptionStyleValueLabels();
}

function updateCaptionStyleValueLabels() {
  $("#captionFontSizeValue").textContent = `${Number($("#captionFontSize").value).toFixed(1)}%`;
  $("#captionBackgroundOpacityValue").textContent = `${Math.round(Number($("#captionBackgroundOpacity").value) * 100)}%`;
  $("#captionOutlineSizeValue").textContent = `${Number($("#captionOutlineSize").value).toFixed(2)}%`;
  $("#captionShadowSizeValue").textContent = `${Number($("#captionShadowSize").value).toFixed(2)}%`;
  $("#captionPaddingValue").textContent = `${Number($("#captionPadding").value).toFixed(1)}%`;
  $("#captionLineSpacingValue").textContent = `${Number($("#captionLineSpacing").value).toFixed(1)}%`;
  $("#captionVerticalMarginValue").textContent = `${Math.round(Number($("#captionVerticalMargin").value))}%`;
  $("#captionMaxWidthValue").textContent = `${Math.round(Number($("#captionMaxWidth").value))}%`;
}

function hexToRgba(hex, opacity) {
  const value = normalizedHex(hex, "#000000").slice(1);
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${opacity})`;
}

function applyCaptionStyle() {
  if (!state.project) return;
  const overlay = $("#captionOverlay");
  const style = normalizeCaptionStyle(state.project.caption_style);
  const stage = $("#mediaStage");
  const stageBox = stage.getBoundingClientRect();
  const videoBox = mediaPlayer.hidden ? stageBox : mediaPlayer.getBoundingClientRect();
  const videoHeight = Math.max(videoBox.height, 1);
  const videoWidth = Math.max(videoBox.width, 1);
  const videoTop = Math.max(0, videoBox.top - stageBox.top);
  const videoLeft = Math.max(0, videoBox.left - stageBox.left);
  const fontSize = Math.max(12, videoHeight * style.font_size_percent / 100);
  const padding = Math.max(1, videoHeight * style.padding_percent / 100);
  const outline = Math.max(0, videoHeight * style.outline_size_percent / 100);
  const shadow = Math.max(0, videoHeight * style.shadow_size_percent / 100);
  const lineSpacing = Math.max(0, videoHeight * style.line_spacing_percent / 100);

  const fontDetails = captionFontStyleDetails(style.font_style);
  overlay.style.fontFamily = captionFontFamilyCss(style.font_family);
  overlay.style.fontWeight = String(fontDetails.weight);
  overlay.style.fontStyle = fontDetails.italic ? "italic" : "normal";
  overlay.style.fontSize = `${fontSize}px`;
  overlay.style.lineHeight = `${fontSize}px`;
  overlay.style.color = style.text_color;
  overlay.style.maxWidth = `${videoWidth * style.max_width_percent / 100}px`;
  overlay.style.textAlign = style.alignment;
  overlay.style.alignItems = ({ left: "flex-start", center: "center", right: "flex-end" })[style.alignment];
  overlay.style.setProperty("--caption-line-gap", `${lineSpacing}px`);
  overlay.style.setProperty("--caption-line-padding", `${padding}px`);
  overlay.style.setProperty("--caption-line-background", hexToRgba(style.background_color, style.background_opacity));
  overlay.style.setProperty("--caption-line-outline", outline ? `${outline}px ${style.outline_color}` : "0 transparent");
  overlay.style.setProperty("--caption-line-shadow", shadow ? `${shadow}px ${shadow}px 0 ${style.shadow_color}` : "none");

  overlay.style.top = "auto";
  overlay.style.bottom = "auto";
  overlay.style.left = "auto";
  overlay.style.right = "auto";
  const transforms = [];
  const horizontalMargin = videoWidth * 0.06;
  const verticalMargin = videoHeight * style.vertical_margin_percent / 100;
  if (style.alignment === "left") overlay.style.left = `${videoLeft + horizontalMargin}px`;
  else if (style.alignment === "right") {
    overlay.style.right = `${Math.max(0, stageBox.width - videoLeft - videoWidth + horizontalMargin)}px`;
  } else {
    overlay.style.left = `${videoLeft + videoWidth / 2}px`;
    transforms.push("translateX(-50%)");
  }
  if (style.position === "top") overlay.style.top = `${videoTop + verticalMargin}px`;
  else if (style.position === "middle") {
    overlay.style.top = `${videoTop + videoHeight / 2}px`;
    transforms.push("translateY(-50%)");
  } else {
    overlay.style.bottom = `${Math.max(0, stageBox.height - videoTop - videoHeight + verticalMargin)}px`;
  }
  overlay.style.transform = transforms.length ? transforms.join(" ") : "none";
}

const captionMeasureCanvas = document.createElement("canvas");

function captionWrapMetrics() {
  if (!state.project) return null;
  const style = normalizeCaptionStyle(state.project.caption_style);
  const stage = $("#mediaStage");
  const stageBox = stage.getBoundingClientRect();
  const videoBox = mediaPlayer.hidden ? stageBox : mediaPlayer.getBoundingClientRect();
  const videoHeight = Math.max(videoBox.height, 1);
  const videoWidth = Math.max(videoBox.width, 1);
  const fontSize = Math.max(12, videoHeight * style.font_size_percent / 100);
  const padding = Math.max(1, videoHeight * style.padding_percent / 100);
  const outline = Math.max(0, videoHeight * style.outline_size_percent / 100);
  const shadow = Math.max(0, videoHeight * style.shadow_size_percent / 100);
  const maximumBoxWidth = Math.max(1, videoWidth * style.max_width_percent / 100);
  const maximumTextWidth = Math.max(1, maximumBoxWidth - (padding * 2) - (outline * 2) - shadow);
  const context = captionMeasureCanvas.getContext("2d");
  if (!context) return null;
  const fontDetails = captionFontStyleDetails(style.font_style);
  context.font = `${fontDetails.italic ? "italic " : ""}${fontDetails.weight} ${fontSize}px ${captionFontFamilyCss(style.font_family)}`;
  return { context, maximumTextWidth };
}

function splitCaptionWord(word, context, maximumTextWidth) {
  const pieces = [];
  let piece = "";
  [...word].forEach((character) => {
    const candidate = `${piece}${character}`;
    if (piece && context.measureText(candidate).width > maximumTextWidth) {
      pieces.push(piece);
      piece = character;
    } else piece = candidate;
  });
  if (piece) pieces.push(piece);
  return pieces;
}

function wrapCaptionText(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const metrics = captionWrapMetrics();
  if (!metrics) {
    const fallback = text.match(/.{1,42}(?:\s+|$)|\S+/g) || [text];
    return fallback.map((line) => line.trim()).filter(Boolean).join("\n");
  }

  const lines = [];
  text.split(/\r?\n/).forEach((paragraph) => {
    const words = paragraph.trim().split(/\s+/).filter(Boolean);
    if (!words.length) return;
    let line = "";
    words.forEach((word) => {
      const pieces = metrics.context.measureText(word).width > metrics.maximumTextWidth
        ? splitCaptionWord(word, metrics.context, metrics.maximumTextWidth)
        : [word];
      pieces.forEach((piece) => {
        const candidate = line ? `${line} ${piece}` : piece;
        if (line && metrics.context.measureText(candidate).width > metrics.maximumTextWidth) {
          lines.push(line);
          line = piece;
        } else line = candidate;
      });
    });
    if (line) lines.push(line);
  });
  return lines.join("\n");
}

function refreshCaptionLayout() {
  applyCaptionStyle();
  syncPlayback();
}

function formatCaptionCue(cue) {
  const speaker = cue.speaker ? `${displaySpeaker(cue.speaker)}: ` : "";
  return wrapCaptionText(`${speaker}${cue.text}`);
}

function renderCaptionOverlay(lines) {
  const overlay = $("#captionOverlay");
  overlay.replaceChildren();
  lines.filter(Boolean).forEach((line) => {
    const element = document.createElement("span");
    element.className = "caption-overlay-line";
    element.textContent = line;
    overlay.append(element);
  });
}

function setupJobPanelStickiness() {
  const panel = $("#jobPanel");
  const anchor = $("#jobPanelAnchor");

  const updateStuckState = () => {
    if (panel.hidden) {
      panel.classList.remove("is-stuck");
      return;
    }

    const panelStyle = getComputedStyle(panel);
    const stickyTop = Number.parseFloat(panelStyle.top) || 0;
    const marginTop = Number.parseFloat(panelStyle.marginTop) || 0;
    const naturalPanelTop = anchor.getBoundingClientRect().bottom + window.scrollY + marginTop;
    const isStuck = window.scrollY + stickyTop >= naturalPanelTop - 0.5;
    panel.classList.toggle("is-stuck", isStuck);
  };

  window.addEventListener("scroll", updateStuckState, { passive: true });
  window.addEventListener("resize", updateStuckState);
  new MutationObserver(updateStuckState).observe(panel, {
    attributes: true,
    attributeFilter: ["hidden"],
  });
  requestAnimationFrame(updateStuckState);
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

function apiErrorFieldLabel(value) {
  return String(value || "request")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function apiValidationErrorMessage(issue) {
  if (typeof issue === "string") return issue.trim();
  if (!issue || typeof issue !== "object") return "";

  const location = Array.isArray(issue.loc)
    ? issue.loc.filter((part) => !["body", "query", "path"].includes(String(part)))
    : [];
  const field = location.length ? String(location[location.length - 1]) : "";
  const message = String(issue.message || issue.msg || issue.error || "").trim();

  if (field === "media" && /field required/i.test(message)) {
    return "Choose a video or audio file before creating captions.";
  }
  if (field === "captions") {
    return "The optional caption file could not be read. Choose an SRT or VTT file and try again.";
  }
  if (field === "transcription_quality") {
    return "Choose a valid transcription quality and try again.";
  }
  if (!message) return "";
  return field ? `${apiErrorFieldLabel(field)}: ${message}` : message;
}

function apiErrorMessage(payload, fallback) {
  const detail = payload && typeof payload === "object" && "detail" in payload
    ? payload.detail
    : payload;

  if (typeof detail === "string" && detail.trim()) return detail.trim();

  if (Array.isArray(detail)) {
    const messages = detail.map(apiValidationErrorMessage).filter(Boolean);
    if (messages.length) return [...new Set(messages)].join(" ");
  }

  if (detail && typeof detail === "object") {
    for (const key of ["message", "error", "title"]) {
      if (typeof detail[key] === "string" && detail[key].trim()) return detail[key].trim();
    }
    if (detail.detail !== undefined) {
      const nested = apiErrorMessage(detail.detail, "");
      if (nested) return nested;
    }
    try {
      const serialized = JSON.stringify(detail);
      if (serialized && serialized !== "{}") return serialized;
    } catch (_) { /* Use the request fallback below. */ }
  }

  return fallback;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const fallback = `Request failed (${response.status})`;
    let detail = fallback;
    try {
      const body = await response.text();
      if (body) {
        let payload = body;
        try { payload = JSON.parse(body); }
        catch (_) { /* A plain-text server error is already readable. */ }
        detail = apiErrorMessage(payload, fallback);
      }
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
  const hasProjects = state.projects.length > 0;
  $("#emptyProjects").hidden = hasProjects;
  $("#deleteAllProjects").hidden = !hasProjects;
  state.projects.forEach((project) => {
    const wrapper = document.createElement("article");
    wrapper.className = "project-card";
    wrapper.dataset.projectId = project.id;
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
    const jobStatus = document.createElement("span");
    jobStatus.className = "project-job-status";
    jobStatus.hidden = true;
    const jobSpinner = document.createElement("span");
    jobSpinner.className = "project-job-spinner";
    jobSpinner.setAttribute("aria-hidden", "true");
    const jobStatusText = document.createElement("span");
    jobStatusText.className = "project-job-status-text";
    jobStatus.append(jobSpinner, jobStatusText);
    open.append(type, title, meta, jobStatus);
    open.addEventListener("click", () => openProject(project.id));
    const actions = document.createElement("div");
    actions.className = "button-row project-card-actions";
    actions.append(
      smallAction("Duplicate", () => duplicateProject(project.id)),
      smallAction("Delete", (event) => openDeleteProjectDialog(project.id, event.currentTarget), true),
    );
    wrapper.append(open, actions);
    list.append(wrapper);
    updateProjectCardJobStatus(wrapper, project.id);
  });
}

function isActiveJob(job = state.activeJob) {
  return Boolean(job && activeJobStates.has(job.state));
}

function projectHasActiveJob(projectId) {
  return isActiveJob() && String(state.activeJobProjectId) === String(projectId);
}

function activeJobDeletionMessage(projectName, deleteAll = false) {
  const name = projectName || state.activeJobProjectName || "This project";
  return deleteAll
    ? `“${name}” is still processing. Let it finish or cancel the active job before deleting all projects.`
    : `“${name}” is still processing. Let it finish or cancel the active job before deleting it.`;
}

function activeJobDuplicationMessage(projectName) {
  const name = projectName || state.activeJobProjectName || "This project";
  return `“${name}” is still processing. Let it finish or cancel the active job before duplicating it.`;
}

function updateProjectCardJobStatus(card, projectId) {
  const status = card.querySelector(".project-job-status");
  const statusText = card.querySelector(".project-job-status-text");
  if (!status || !statusText) return;
  const active = projectHasActiveJob(projectId);
  card.classList.toggle("has-active-job", active);
  status.hidden = !active;
  if (!active) return;
  const progress = Math.max(0, Math.min(100, Math.round(Number(state.activeJob.progress) || 0)));
  statusText.textContent = `${state.activeJob.stage || "Processing"} · ${progress}%`;
}

function syncActiveJobIndicators() {
  document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {
    updateProjectCardJobStatus(card, card.dataset.projectId);
  });
}

function smallAction(label, handler, danger = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = danger ? "project-action project-action-delete" : "project-action project-action-duplicate";
  button.textContent = label;
  button.addEventListener("click", (event) => handler(event));
  return button;
}

async function uploadMedia(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const mediaFile = $("#mediaInput").files[0];
  if (!mediaFile) return;
  setBusy(form, true, "Importing…");
  try {
    const formData = new FormData();
    formData.append("media", mediaFile, mediaFile.name);
    const captionFile = $("#captionInput").files[0];
    if (captionFile) formData.append("captions", captionFile, captionFile.name);
    formData.set("transcription_quality", $("#transcriptionQualitySetting").value);
    const payload = await api("/api/projects/upload", { method: "POST", body: formData });
    state.project = payload.project;
    showWorkspace();
    if (payload.job) monitorJob(payload.job);
    form.reset();
  } catch (error) {
    toast(error.message || "The selected file could not be imported.", "error");
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
        transcription_quality: $("#transcriptionQualitySetting").value,
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

function restoreTranscriptionQuality() {
  try {
    const saved = localStorage.getItem(transcriptionQualityStorageKey);
    $("#transcriptionQualitySetting").value = saved === "fast" ? "fast" : "accurate";
  } catch (_) { $("#transcriptionQualitySetting").value = "accurate"; }
}

function saveTranscriptionQuality() {
  try {
    localStorage.setItem(transcriptionQualityStorageKey, $("#transcriptionQualitySetting").value);
  } catch (_) { /* The selected quality still applies for this session. */ }
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
      if (activeJobStates.has(job.state)) monitorJob(job, id, state.project.name);
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
  workspaceView.hidden = true;
  homeView.hidden = false;
  state.project = null;
  state.captionSamplePreview = false;
  $("#captionPreviewSample").checked = false;
  $("#captionOverlay").textContent = "";
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
  project.caption_style = loadCaptionStyle(project);
  renderCaptionStyleControls();
  applyCaptionStyle();
  renderCues();
  renderFindings();
  renderSummary();
  renderExportResults();
  syncPlayback();
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
  syncPlayback();
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
    const captionStyle = normalizeCaptionStyle(state.project.caption_style);
    storeCaptionStyle(state.project.id, captionStyle);
    const savedProject = await api(`/api/projects/${state.project.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("#projectTitle").value,
        cues: state.project.cues,
        speaker_names: state.project.speaker_names || {},
        caption_style: captionStyle,
      }),
    });
    state.project = { ...savedProject, caption_style: captionStyle };
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
  const overlayLines = visible.flatMap((cue) => formatCaptionCue(cue).split("\n"));
  if (!overlayLines.length && state.captionSamplePreview) {
    overlayLines.push(...wrapCaptionText("Sample caption: customize this text before export.").split("\n"));
  }
  renderCaptionOverlay(overlayLines);
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

function monitorJob(job, projectId = state.project?.id, projectName = state.project?.name) {
  if (!job || !projectId) return;
  state.activeJob = job;
  state.activeJobProjectId = projectId;
  state.activeJobProjectName = projectName
    || state.projects.find((project) => String(project.id) === String(projectId))?.name
    || "Current project";
  $("#jobPanel").hidden = false;
  updateJobPanel(job);
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(pollJob, 900);
}

async function pollJob() {
  if (!state.activeJob || !state.activeJobProjectId) return;
  const trackedJobId = state.activeJob.id;
  const trackedProjectId = state.activeJobProjectId;
  const trackedProjectName = state.activeJobProjectName;
  try {
    const job = await api(`/api/projects/${trackedProjectId}/jobs/${trackedJobId}`);
    if (state.activeJob?.id !== trackedJobId || String(state.activeJobProjectId) !== String(trackedProjectId)) return;
    state.activeJob = job;
    updateJobPanel(job);
    if (activeJobStates.has(job.state)) {
      state.pollTimer = setTimeout(pollJob, 1100);
      return;
    }

    const viewingTrackedProject = !workspaceView.hidden
      && String(state.project?.id) === String(trackedProjectId);

    if (job.state === "completed") {
      const completedProject = await api(`/api/projects/${trackedProjectId}`);
      if (viewingTrackedProject) {
        state.project = completedProject;
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
      } else {
        if (!homeView.hidden) await loadProjects();
        toast(`${trackedProjectName} finished processing.`);
      }
    } else if (job.state === "failed") {
      toast(job.error || `${trackedProjectName} could not be processed.`);
    } else if (job.state === "cancelled") {
      toast(`Processing cancelled for ${trackedProjectName}. Saved work was not changed.`);
    }

    const finishedJobId = job.id;
    setTimeout(() => {
      if (state.activeJob?.id !== finishedJobId) return;
      $("#jobPanel").hidden = true;
      state.activeJob = null;
      state.activeJobProjectId = null;
      state.activeJobProjectName = "";
      syncActiveJobIndicators();
    }, 1800);
  } catch (error) { toast(error.message); }
}

function updateJobPanel(job) {
  $("#jobProjectName").textContent = state.activeJobProjectName ? `Project: ${state.activeJobProjectName}` : "";
  $("#jobStage").textContent = job.stage;
  $("#jobMessage").textContent = job.message || job.state;
  $("#jobProgress").value = job.progress;
  $("#jobProgress").textContent = `${job.progress}%`;
  $("#jobPercent").textContent = `${job.progress}%`;
  $("#cancelJob").hidden = !activeJobStates.has(job.state);
  $("#cancelJob").disabled = job.state === "cancelling";
  $("#cancelJob").textContent = job.state === "cancelling" ? "Cancelling…" : "Cancel";
  syncActiveJobIndicators();
}

async function cancelJob() {
  if (!state.activeJob || !state.activeJobProjectId) return;
  try {
    state.activeJob = await api(`/api/projects/${state.activeJobProjectId}/jobs/${state.activeJob.id}/cancel`, { method: "POST" });
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
  const projectToDuplicate = state.projects.find((item) => String(item.id) === String(id));
  if (projectHasActiveJob(id)) {
    toast(activeJobDuplicationMessage(projectToDuplicate?.name), "error");
    return;
  }

  try {
    const project = await api(`/api/projects/${id}/duplicate`, { method: "POST" });
    toast("Project duplicated.");
    await loadProjects();
    await openProject(project.id);
  } catch (error) { toast(error.message); }
}

function openDeleteProjectDialog(id, triggerButton) {
  const project = state.projects.find((item) => item.id === id);
  if (!project) return;

  if (projectHasActiveJob(id)) {
    toast(activeJobDeletionMessage(project.name), "error");
    triggerButton?.focus();
    return;
  }

  state.deleteProjectId = id;
  state.deleteTriggerButton = triggerButton;
  $("#deleteProjectName").textContent = project.name;

  const dialog = $("#deleteConfirmDialog");
  dialog.returnValue = "";
  dialog.showModal();
}

async function handleDeleteProjectDialogClose() {
  const dialog = $("#deleteConfirmDialog");
  const projectId = state.deleteProjectId;
  const triggerButton = state.deleteTriggerButton;
  const confirmed = dialog.returnValue === "confirm" && Boolean(projectId);

  if (!confirmed) {
    state.deleteProjectId = null;
    state.deleteTriggerButton = null;
    if (triggerButton?.isConnected) triggerButton.focus();
    return;
  }

  const project = state.projects.find((item) => String(item.id) === String(projectId));
  if (projectHasActiveJob(projectId)) {
    toast(activeJobDeletionMessage(project?.name), "error");
    state.deleteProjectId = null;
    state.deleteTriggerButton = null;
    if (triggerButton?.isConnected) triggerButton.focus();
    return;
  }

  const confirmButton = $("#confirmDeleteProject");
  confirmButton.disabled = true;
  confirmButton.textContent = "Deleting…";

  try {
    await api(`/api/projects/${projectId}`, { method: "DELETE" });
    toast("Project deleted.");
    await loadProjects();
  } catch (error) {
    toast(error.message);
  } finally {
    confirmButton.disabled = false;
    confirmButton.textContent = "Delete project";
    state.deleteProjectId = null;
    state.deleteTriggerButton = null;

    if (triggerButton?.isConnected) {
      triggerButton.focus();
    } else {
      $("#refreshProjects").focus();
    }
  }
}

function openDeleteAllProjectsDialog() {
  if (!state.projects.length) return;
  if (isActiveJob()) {
    toast(activeJobDeletionMessage(state.activeJobProjectName, true), "error");
    return;
  }
  const dialog = $("#deleteAllConfirmDialog");
  $("#deleteAllProjectCount").textContent = `${state.projects.length} ${state.projects.length === 1 ? "project" : "projects"}`;
  dialog.returnValue = "";
  dialog.showModal();
}

async function handleDeleteAllProjectsDialogClose() {
  const dialog = $("#deleteAllConfirmDialog");
  if (dialog.returnValue !== "confirm") return;

  if (isActiveJob()) {
    toast(activeJobDeletionMessage(state.activeJobProjectName, true), "error");
    return;
  }

  const confirmButton = $("#confirmDeleteAllProjects");
  const cancelButton = $("#cancelDeleteAllProjects");
  const ids = state.projects.map((project) => project.id);
  let deletedCount = 0;

  confirmButton.disabled = true;
  cancelButton.disabled = true;
  $("#deleteAllProjects").disabled = true;
  confirmButton.textContent = "Deleting…";

  try {
    for (const id of ids) {
      await api(`/api/projects/${id}`, { method: "DELETE" });
      deletedCount += 1;
    }
    toast(`Deleted ${deletedCount} ${deletedCount === 1 ? "project" : "projects"}.`);
  } catch (error) {
    toast(`Deleted ${deletedCount} of ${ids.length} projects. ${error.message}`);
  } finally {
    confirmButton.disabled = false;
    cancelButton.disabled = false;
    $("#deleteAllProjects").disabled = false;
    confirmButton.textContent = "Delete all projects";
    await loadProjects();
    $("#deleteAllProjects").focus();
  }
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

function toast(message, type = "info") {
  const region = $("#notificationRegion");
  if (!region) return;

  const notification = document.createElement("div");
  notification.className = `notification notification-${type}`;
  notification.setAttribute("role", type === "error" ? "alert" : "status");

  const icon = document.createElement("span");
  icon.className = "notification-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = type === "error" ? "!" : "i";

  const text = document.createElement("p");
  text.className = "notification-message";
  text.textContent = message;

  const dismissButton = document.createElement("button");
  dismissButton.type = "button";
  dismissButton.className = "notification-dismiss";
  dismissButton.setAttribute("aria-label", "Dismiss notification");
  dismissButton.textContent = "×";

  notification.append(icon, text, dismissButton);
  region.append(notification);
  requestAnimationFrame(() => notification.classList.add("is-visible"));

  let removalTimer;
  const dismiss = () => {
    clearTimeout(removalTimer);
    notification.classList.remove("is-visible");
    setTimeout(() => notification.remove(), 180);
  };

  dismissButton.addEventListener("click", dismiss);
  removalTimer = setTimeout(dismiss, 5000);
}

// major-iterations: productivity tools
(() => {
  const productivity = {
    projectQuery: "",
    projectType: "all",
    projectSort: "recent",
    captionSearchIndex: -1,
    captionSearchCueId: null,
    lowConfidenceIndex: -1,
  };

  state.redo = Array.isArray(state.redo) ? state.redo : [];

  const originalRenderProjects = renderProjects;
  renderProjects = function renderProjectsWithFilters() {
    const allProjects = state.projects;
    const query = productivity.projectQuery.trim().toLocaleLowerCase();
    const visibleProjects = allProjects
      .filter((project) => {
        if (query && !String(project.name || "").toLocaleLowerCase().includes(query)) return false;
        if (productivity.projectType === "video" && !project.media?.has_video) return false;
        if (productivity.projectType === "audio" && project.media?.has_video) return false;
        return true;
      })
      .sort((left, right) => {
        if (productivity.projectSort === "oldest") {
          return new Date(left.updated_at) - new Date(right.updated_at);
        }
        if (productivity.projectSort === "name") {
          return String(left.name || "").localeCompare(String(right.name || ""), undefined, { sensitivity: "base" });
        }
        if (productivity.projectSort === "captions") {
          return (right.cues?.length || 0) - (left.cues?.length || 0);
        }
        return new Date(right.updated_at) - new Date(left.updated_at);
      });

    state.projects = visibleProjects;
    try {
      originalRenderProjects();
    } finally {
      state.projects = allProjects;
    }

    const count = $("#projectFilterCount");
    if (count) count.textContent = `${visibleProjects.length} of ${allProjects.length} projects`;
    const noResults = $("#projectFilterEmpty");
    if (noResults) noResults.hidden = visibleProjects.length > 0 || allProjects.length === 0;
    $("#emptyProjects").hidden = allProjects.length > 0;
    $("#deleteAllProjects").hidden = allProjects.length === 0;
  };

  const originalRenderCues = renderCues;
  renderCues = function renderCuesWithProductivity() {
    originalRenderCues();
    updateCaptionProductivityStatus();
    if (productivity.captionSearchCueId) {
      document.querySelector(`#cue-${CSS.escape(productivity.captionSearchCueId)}`)?.classList.add("search-match");
    }
  };

  const originalRemember = remember;
  remember = function rememberWithRedoReset() {
    originalRemember();
    state.redo.length = 0;
    updateRedoButton();
  };

  const originalUndo = undo;
  undo = function undoWithRedo() {
    if (!state.project || !state.undo.length) return;
    state.redo.push(JSON.stringify(state.project.cues));
    if (state.redo.length > 30) state.redo.shift();
    originalUndo();
    updateRedoButton();
  };

  const originalOpenProject = openProject;
  openProject = async function openProjectWithProductivityReset(...args) {
    state.redo.length = 0;
    productivity.captionSearchIndex = -1;
    productivity.captionSearchCueId = null;
    productivity.lowConfidenceIndex = -1;
    updateRedoButton();
    return originalOpenProject(...args);
  };

  const originalPlaybackKeys = playbackKeys;
  playbackKeys = function playbackKeysWithPrecision(event) {
    if (workspaceView.hidden || ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) {
      originalPlaybackKeys(event);
      return;
    }
    const player = activePlayer();
    if (!player?.src) {
      originalPlaybackKeys(event);
      return;
    }

    if ((event.shiftKey || event.altKey) && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      const amount = event.altKey ? 0.5 : 0.1;
      const direction = event.key === "ArrowLeft" ? -1 : 1;
      player.currentTime = Math.max(0, Math.min(player.duration || Infinity, player.currentTime + amount * direction));
      return;
    }
    if (event.key === "[") {
      event.preventDefault();
      setCueBoundaryFromPlayhead("start");
      return;
    }
    if (event.key === "]") {
      event.preventDefault();
      setCueBoundaryFromPlayhead("end");
      return;
    }
    if (event.code === "KeyP") {
      event.preventDefault();
      moveToAdjacentCue(-1);
      return;
    }
    if (event.code === "KeyN") {
      event.preventDefault();
      moveToAdjacentCue(1);
      return;
    }
    originalPlaybackKeys(event);
  };

  const originalOpenSettings = openSettings;
  openSettings = async function openSettingsWithReadiness() {
    await originalOpenSettings();
    try {
      renderSystemReadiness(await api("/api/health"));
    } catch (error) {
      const list = $("#systemReadinessList");
      if (list) list.textContent = `Could not check system readiness: ${error.message}`;
    }
  };

  function installProjectControls() {
    if ($("#projectBrowserControls")) return;
    const container = document.querySelector(".project-list-container");
    if (!container) return;

    const controls = document.createElement("div");
    controls.id = "projectBrowserControls";
    controls.className = "project-browser-controls";
    controls.setAttribute("aria-label", "Project search and filters");
    controls.innerHTML = `
      <label class="project-search-field" for="projectSearch">
        <span class="sr-only">Search projects</span>
        <input id="projectSearch" type="search" placeholder="Search projects" autocomplete="off">
      </label>
      <div class="project-browser-actions">
        <label class="project-compact-select" for="projectTypeFilter">
          <span class="sr-only">Media</span>
          <select id="projectTypeFilter" aria-label="Media">
            <option value="all">All media</option>
            <option value="video">Video</option>
            <option value="audio">Audio only</option>
          </select>
        </label>
        <label class="project-compact-select" for="projectSort">
          <span class="sr-only">Sort</span>
          <select id="projectSort" aria-label="Sort">
            <option value="recent">Most recent</option>
            <option value="oldest">Oldest updated</option>
            <option value="name">Name A-Z</option>
            <option value="captions">Most captions</option>
          </select>
        </label>
        <span id="projectFilterCount" class="project-filter-count" role="status"></span>
      </div>`;
    container.before(controls);

    const noResults = document.createElement("p");
    noResults.id = "projectFilterEmpty";
    noResults.className = "empty-state project-filter-empty";
    noResults.hidden = true;
    noResults.textContent = "No projects match the current search and filters.";
    container.after(noResults);

    $("#projectSearch").addEventListener("input", (event) => {
      productivity.projectQuery = event.target.value;
      renderProjects();
    });
    $("#projectTypeFilter").addEventListener("change", (event) => {
      productivity.projectType = event.target.value;
      renderProjects();
    });
    $("#projectSort").addEventListener("change", (event) => {
      productivity.projectSort = event.target.value;
      renderProjects();
    });
  }

  function installCaptionTools() {
    if ($("#captionCommandBar")) return;
    const editorHeading = document.querySelector(".editor-heading");
    if (!editorHeading) return;

    const addButton = $("#addCueButton");
    const followButton = $("#followPlaybackButton");
    const undoButton = $("#undoButton");
    const improveButton = $("#improveTranscriptButton");
    const speakersButton = $("#redetectSpeakersButton");
    const renameButton = $("#renameSpeakersButton");
    const oldTools = editorHeading.querySelector(".editor-tools");

    const redoButton = document.createElement("button");
    redoButton.id = "redoButton";
    redoButton.className = "secondary editor-action editor-command-button";
    redoButton.type = "button";
    redoButton.textContent = "Redo";
    redoButton.disabled = true;

    const findButton = document.createElement("button");
    findButton.id = "captionFindToggle";
    findButton.className = "secondary editor-action editor-command-button";
    findButton.type = "button";
    findButton.setAttribute("aria-expanded", "false");
    findButton.setAttribute("aria-controls", "captionProductivityTools");
    findButton.textContent = "Find";

    const reviewButton = document.createElement("button");
    reviewButton.id = "lowConfidenceReview";
    reviewButton.className = "secondary editor-action editor-command-button editor-review-action";
    reviewButton.type = "button";
    reviewButton.textContent = "Review uncertain";

    [followButton, undoButton].forEach((button) => button?.classList.add("editor-command-button"));

    const commandBar = document.createElement("div");
    commandBar.id = "captionCommandBar";
    commandBar.className = "editor-command-bar";
    commandBar.setAttribute("role", "group");
    commandBar.setAttribute("aria-label", "Caption editor tools");

    const primary = document.createElement("div");
    primary.className = "editor-command-primary";
    [followButton, undoButton, redoButton, findButton, reviewButton].forEach((button) => {
      if (button) primary.append(button);
    });

    const secondary = document.createElement("div");
    secondary.className = "editor-command-secondary";

    const more = document.createElement("details");
    more.className = "editor-more-menu";
    more.innerHTML = `
      <summary class="editor-more-trigger" aria-label="More caption tools">More tools</summary>
      <div class="editor-more-popover" role="group" aria-label="More caption tools"></div>`;
    const popover = more.querySelector(".editor-more-popover");
    [improveButton, speakersButton, renameButton].forEach((button) => {
      if (!button) return;
      button.classList.add("editor-more-action");
      popover.append(button);
    });
    secondary.append(more);
    if (addButton) secondary.append(addButton);
    commandBar.append(primary, secondary);

    const findPanel = document.createElement("div");
    findPanel.id = "captionProductivityTools";
    findPanel.className = "caption-productivity-tools caption-find-panel";
    findPanel.hidden = true;
    findPanel.innerHTML = `
      <div class="caption-find-search">
        <label for="captionSearch"><span class="sr-only">Find caption text</span><input id="captionSearch" type="search" placeholder="Find in captions" autocomplete="off"></label>
        <span id="captionSearchStatus" class="caption-search-status" role="status"></span>
        <button id="captionFindNext" class="secondary editor-action" type="button">Next</button>
      </div>
      <div class="caption-find-replace">
        <label for="captionReplace"><span class="sr-only">Replace with</span><input id="captionReplace" type="text" placeholder="Replace with"></label>
        <button id="captionReplaceCurrent" class="secondary editor-action" type="button">Replace</button>
        <button id="captionReplaceAll" class="secondary editor-action" type="button">Replace all</button>
      </div>`;

    oldTools?.remove();
    editorHeading.append(commandBar, findPanel);

    const closeMoreMenu = () => { more.open = false; };
    more.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMoreMenu();
        more.querySelector("summary")?.focus();
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (more.open && !more.contains(event.target)) closeMoreMenu();
    });
    popover.querySelectorAll("button").forEach((button) => button.addEventListener("click", closeMoreMenu));

    findButton.addEventListener("click", () => {
      const opening = findPanel.hidden;
      findPanel.hidden = !opening;
      findButton.setAttribute("aria-expanded", String(opening));
      findButton.setAttribute("aria-pressed", String(opening));
      if (opening) $("#captionSearch")?.focus();
    });
    $("#captionSearch").addEventListener("input", () => {
      productivity.captionSearchIndex = -1;
      productivity.captionSearchCueId = null;
      updateCaptionProductivityStatus();
    });
    $("#captionSearch").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        findNextCaption();
      } else if (event.key === "Escape") {
        event.preventDefault();
        findPanel.hidden = true;
        findButton.setAttribute("aria-expanded", "false");
        findButton.setAttribute("aria-pressed", "false");
        findButton.focus();
      }
    });
    $("#captionFindNext").addEventListener("click", findNextCaption);
    $("#captionReplaceCurrent").addEventListener("click", replaceCurrentCaptionMatch);
    $("#captionReplaceAll").addEventListener("click", replaceAllCaptionMatches);
    $("#lowConfidenceReview").addEventListener("click", reviewNextLowConfidenceCue);
    redoButton.addEventListener("click", redoLastEdit);
    updateRedoButton();
  }

  function installSafeAreaGuide() {
    if ($("#safeAreaGuides")) return;
    const stage = $("#mediaStage");
    if (!stage) return;
    const guides = document.createElement("div");
    guides.id = "safeAreaGuides";
    guides.className = "safe-area-guides";
    guides.hidden = true;
    guides.setAttribute("aria-hidden", "true");
    guides.innerHTML = `
      <div class="safe-area-action"><span>Action safe</span></div>
      <div class="safe-area-title"><span>Title / caption safe</span></div>`;
    stage.append(guides);

    const help = document.querySelector(".playback-help");
    if (!help) return;

    const utility = document.createElement("div");
    utility.className = "preview-utility-tools";

    const safeButton = document.createElement("button");
    safeButton.id = "safeAreaToggle";
    safeButton.className = "text-button safe-area-toggle";
    safeButton.type = "button";
    safeButton.setAttribute("aria-pressed", "false");
    safeButton.textContent = "Safe areas";
    safeButton.addEventListener("click", () => {
      const enabled = guides.hidden;
      guides.hidden = !enabled;
      safeButton.setAttribute("aria-pressed", String(enabled));
    });

    const shortcuts = document.createElement("details");
    shortcuts.className = "shortcut-disclosure";
    shortcuts.innerHTML = `
      <summary>Shortcuts</summary>
      <div class="timing-shortcut-grid">
        <span><span><kbd>Shift</kbd> + <kbd>←/→</kbd></span><small>Nudge 0.1s</small></span>
        <span><span><kbd>Option/Alt</kbd> + <kbd>←/→</kbd></span><small>Nudge 0.5s</small></span>
        <span><span><kbd>[</kbd> / <kbd>]</kbd></span><small>Set cue start / end</small></span>
        <span><span><kbd>P</kbd> / <kbd>N</kbd></span><small>Previous / next caption</small></span>
      </div>`;
    shortcuts.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        shortcuts.open = false;
        shortcuts.querySelector("summary")?.focus();
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (shortcuts.open && !shortcuts.contains(event.target)) shortcuts.open = false;
    });

    utility.append(safeButton, shortcuts);
    help.append(utility);
  }

  function installSystemReadiness() {
    if ($("#systemReadiness")) return;
    const form = document.querySelector("#settingsDialog .dialog-card");
    if (!form) return;
    const section = document.createElement("section");
    section.id = "systemReadiness";
    section.innerHTML = `
      <h3>System readiness</h3>
      <p class="field-note">Check the local tools and storage used by analysis and export before starting a long job.</p>
      <div id="systemReadinessList" class="system-readiness-list" role="status">Open Settings to run the readiness check.</div>`;
    const storageSection = [...form.querySelectorAll("section")].find(
      (item) => item.querySelector("h3")?.textContent?.trim() === "Storage"
    );
    if (storageSection) form.insertBefore(section, storageSection);
    else form.append(section);
  }

  function updateCaptionProductivityStatus() {
    const status = $("#captionSearchStatus");
    const lowConfidenceButton = $("#lowConfidenceReview");
    if (!state.project) {
      if (status) status.textContent = "";
      if (lowConfidenceButton) lowConfidenceButton.textContent = "Review uncertain";
      return;
    }
    const query = $("#captionSearch")?.value.trim().toLocaleLowerCase() || "";
    const matches = query
      ? state.project.cues.filter((cue) => String(cue.text || "").toLocaleLowerCase().includes(query))
      : [];
    if (status) status.textContent = query ? `${matches.length} match${matches.length === 1 ? "" : "es"}` : "";
    const uncertain = lowConfidenceCues();
    if (lowConfidenceButton) {
      lowConfidenceButton.textContent = uncertain.length ? `Review uncertain (${uncertain.length})` : "No uncertain captions";
      lowConfidenceButton.disabled = uncertain.length === 0;
    }
  }

  function findNextCaption() {
    if (!state.project) return;
    const query = $("#captionSearch")?.value.trim().toLocaleLowerCase() || "";
    if (!query) {
      toast("Enter caption text to find.");
      $("#captionSearch")?.focus();
      return;
    }
    const cues = state.project.cues;
    for (let offset = 1; offset <= cues.length; offset += 1) {
      const index = (productivity.captionSearchIndex + offset + cues.length) % cues.length;
      if (String(cues[index].text || "").toLocaleLowerCase().includes(query)) {
        productivity.captionSearchIndex = index;
        focusCaptionCue(cues[index]);
        return;
      }
    }
    toast("No captions match that text.");
  }

  function replaceCurrentCaptionMatch() {
    if (!state.project) return;
    const query = $("#captionSearch")?.value || "";
    const replacement = $("#captionReplace")?.value ?? "";
    const cue = state.project.cues[productivity.captionSearchIndex];
    if (!query.trim() || !cue || !String(cue.text).toLocaleLowerCase().includes(query.toLocaleLowerCase())) {
      findNextCaption();
      return;
    }
    const nextText = replaceFirstInsensitive(String(cue.text), query, replacement).trim();
    if (!nextText) {
      toast("A caption cannot be empty. Enter replacement text or delete the caption instead.");
      return;
    }
    remember();
    cue.text = nextText;
    renderCues();
    scheduleSave();
    focusCaptionCue(cue);
  }

  function replaceAllCaptionMatches() {
    if (!state.project) return;
    const query = $("#captionSearch")?.value || "";
    const replacement = $("#captionReplace")?.value ?? "";
    if (!query.trim()) {
      toast("Enter caption text to replace.");
      return;
    }
    const matching = state.project.cues.filter((cue) =>
      String(cue.text || "").toLocaleLowerCase().includes(query.toLocaleLowerCase())
    );
    if (!matching.length) {
      toast("No captions match that text.");
      return;
    }
    const replacements = matching.map((cue) => replaceAllInsensitive(String(cue.text), query, replacement).trim());
    if (replacements.some((text) => !text)) {
      toast("Replace all would create an empty caption. Use a non-empty replacement.");
      return;
    }
    remember();
    matching.forEach((cue, index) => { cue.text = replacements[index]; });
    productivity.captionSearchIndex = -1;
    productivity.captionSearchCueId = null;
    renderCues();
    scheduleSave();
    toast(`Replaced text in ${matching.length} caption${matching.length === 1 ? "" : "s"}.`);
  }

  function replaceFirstInsensitive(text, query, replacement) {
    const index = text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
    if (index < 0) return text;
    return text.slice(0, index) + replacement + text.slice(index + query.length);
  }

  function replaceAllInsensitive(text, query, replacement) {
    let remaining = text;
    let result = "";
    const normalizedQuery = query.toLocaleLowerCase();
    while (remaining.toLocaleLowerCase().includes(normalizedQuery)) {
      const index = remaining.toLocaleLowerCase().indexOf(normalizedQuery);
      result += remaining.slice(0, index) + replacement;
      remaining = remaining.slice(index + query.length);
    }
    return result + remaining;
  }

  function lowConfidenceCues() {
    if (!state.project) return [];
    return state.project.cues.filter(
      (cue) => cue.source !== "sound" && cue.confidence != null && Number(cue.confidence) < 0.75
    );
  }

  function reviewNextLowConfidenceCue() {
    const cues = lowConfidenceCues();
    if (!cues.length) {
      toast("No low-confidence captions need review.");
      return;
    }
    productivity.lowConfidenceIndex = (productivity.lowConfidenceIndex + 1) % cues.length;
    focusCaptionCue(cues[productivity.lowConfidenceIndex]);
  }

  function focusCaptionCue(cue) {
    productivity.captionSearchCueId = cue.id;
    const player = activePlayer();
    if (player?.src) player.currentTime = Math.max(0, Number(cue.start) || 0);
    document.querySelectorAll(".cue-row.search-match").forEach((row) => row.classList.remove("search-match"));
    const row = document.querySelector(`#cue-${CSS.escape(cue.id)}`);
    if (row) {
      row.classList.add("search-match");
      row.scrollIntoView({ block: "center", behavior: "smooth" });
      row.querySelector("textarea")?.focus({ preventScroll: true });
    }
  }

  function redoLastEdit() {
    if (!state.project || !state.redo.length) return;
    state.undo.push(JSON.stringify(state.project.cues));
    if (state.undo.length > 30) state.undo.shift();
    state.project.cues = JSON.parse(state.redo.pop());
    $("#undoButton").disabled = state.undo.length === 0;
    updateRedoButton();
    renderCues();
    scheduleSave();
  }

  function updateRedoButton() {
    const button = $("#redoButton");
    if (button) button.disabled = !state.redo?.length;
  }

  function cueIndexAtPlayhead() {
    if (!state.project?.cues.length) return -1;
    const time = activePlayer()?.currentTime ?? 0;
    const direct = state.project.cues.findIndex((cue) => time >= cue.start && time <= cue.end);
    if (direct >= 0) return direct;
    let bestIndex = 0;
    let bestDistance = Infinity;
    state.project.cues.forEach((cue, index) => {
      const distance = Math.min(Math.abs(time - cue.start), Math.abs(time - cue.end));
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });
    return bestIndex;
  }

  function setCueBoundaryFromPlayhead(boundary) {
    if (!state.project) return;
    const index = cueIndexAtPlayhead();
    if (index < 0) return;
    const cue = state.project.cues[index];
    const player = activePlayer();
    const time = Math.max(0, player?.currentTime || 0);
    remember();
    if (boundary === "start") cue.start = Math.min(time, Math.max(0, cue.end - 0.05));
    else cue.end = Math.max(time, cue.start + 0.05);
    renderCues();
    scheduleSave();
    focusCaptionCue(cue);
  }

  function moveToAdjacentCue(direction) {
    if (!state.project?.cues.length) return;
    const current = cueIndexAtPlayhead();
    const index = Math.max(0, Math.min(state.project.cues.length - 1, current + direction));
    focusCaptionCue(state.project.cues[index]);
  }

  function renderSystemReadiness(health) {
    const list = $("#systemReadinessList");
    if (!list) return;
    const status = (ready) => ready ? '<span class="readiness-ok">Ready</span>' : '<span class="readiness-warning">Needs attention</span>';
    list.innerHTML = `
      <div><strong>FFmpeg</strong>${status(Boolean(health.ffmpeg))}</div>
      <div><strong>FFprobe</strong>${status(Boolean(health.ffprobe))}</div>
      <div><strong>Python runtime</strong><span>${health.python_version || "Unknown"}</span></div>
      <div><strong>Free disk space</strong><span>${formatBytes(Number(health.free_disk_bytes) || 0)}</span></div>
      <div><strong>Local model cache</strong><span>${formatBytes(Number(health.model_cache_bytes) || 0)}</span></div>
      <div><strong>Recovered interrupted jobs</strong><span>${Number(health.recovered_jobs) || 0}</span></div>`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    installProjectControls();
    installCaptionTools();
    installSafeAreaGuide();
    installSystemReadiness();
    renderProjects();
    updateCaptionProductivityStatus();
  });
})();

// major-iterations: readability and finding fixes
(() => {
  const baseRenderFindings = renderFindings;

  function colorChannels(hex) {
    const value = normalizedHex(hex, "#000000").slice(1);
    return [0, 2, 4].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16) / 255);
  }

  function relativeLuminance(hex) {
    const linear = colorChannels(hex).map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    );
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  }

  function captionContrastRatio(first, second) {
    const firstLuminance = relativeLuminance(first);
    const secondLuminance = relativeLuminance(second);
    const lighter = Math.max(firstLuminance, secondLuminance);
    const darker = Math.min(firstLuminance, secondLuminance);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function captionStyleReadabilityFindings() {
    if (!state.project) return [];
    const style = normalizeCaptionStyle(state.project.caption_style);
    const findings = [];
    const contrast = captionContrastRatio(style.text_color, style.background_color);
    if (style.background_opacity >= 0.65 && contrast < 4.5) {
      findings.push({
        code: "style_low_contrast",
        severity: "warning",
        message: `Caption text and background colors have ${contrast.toFixed(2)}:1 contrast when the background is opaque. Choose colors with at least 4.5:1 contrast for normal-size text.`,
      });
    }
    if (style.background_opacity < 0.55 && style.outline_size_percent < 0.1 && style.shadow_size_percent < 0.1) {
      findings.push({
        code: "style_weak_video_separation",
        severity: "warning",
        message: "The caption background is highly transparent and the text has little outline or shadow. Moving video may make the caption difficult to read.",
      });
    }
    if (style.font_size_percent < 5) {
      findings.push({
        code: "style_small_text",
        severity: "info",
        message: "Caption text is very small relative to the video frame. Preview the result at the intended viewing size or increase the caption size.",
      });
    }
    if (style.max_width_percent > 94) {
      findings.push({
        code: "style_edge_crowding",
        severity: "info",
        message: "Captions can extend very close to the video edge. Reduce maximum caption width to leave a safer visual margin.",
      });
    }
    return findings;
  }

  function findingFixLabel(finding) {
    if (!finding?.cue_id) return null;
    const cue = state.project?.cues.find((item) => item.id === finding.cue_id);
    if (!cue) return null;
    const index = state.project.cues.indexOf(cue);
    const previous = index > 0 ? state.project.cues[index - 1] : null;
    const next = index + 1 < state.project.cues.length ? state.project.cues[index + 1] : null;
    const duration = Number(state.project.media?.duration || 0);
    if (["reading_speed", "long_line", "line_count"].includes(finding.code)) return "Split caption";
    if (finding.code === "too_long") return "Limit to 7 seconds";
    if (finding.code === "outside_media" && duration > cue.start) return "Clamp to media";
    if (finding.code === "too_short") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target > cue.end && (!next || target <= next.start)) return "Extend to 1 second";
    }
    if (finding.code === "overlap" && previous && previous.end < cue.end) return "Resolve overlap";
    if (finding.code === "invalid_interval") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target > cue.start && (!next || target <= next.start)) return "Repair interval";
    }
    return null;
  }

  async function applyFindingFix(finding) {
    if (!state.project || !finding?.cue_id) return;
    const cue = state.project.cues.find((item) => item.id === finding.cue_id);
    if (!cue) return;
    const index = state.project.cues.indexOf(cue);
    const previous = index > 0 ? state.project.cues[index - 1] : null;
    const next = index + 1 < state.project.cues.length ? state.project.cues[index + 1] : null;
    const duration = Number(state.project.media?.duration || 0);

    if (["reading_speed", "long_line", "line_count"].includes(finding.code)) {
      splitCue(index);
      await validateProject();
      return;
    }

    remember();
    if (finding.code === "too_long") {
      cue.end = Math.min(duration || Infinity, cue.start + 7);
    } else if (finding.code === "outside_media" && duration > cue.start) {
      cue.end = duration;
    } else if (finding.code === "too_short") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target <= cue.end || (next && target > next.start)) return;
      cue.end = target;
    } else if (finding.code === "overlap" && previous && previous.end < cue.end) {
      cue.start = previous.end;
    } else if (finding.code === "invalid_interval") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target <= cue.start || (next && target > next.start)) return;
      cue.end = target;
    } else {
      return;
    }
    renderCues();
    await validateProject();
  }

  async function applyStyleFindingFix(code) {
    if (!state.project) return;
    const style = normalizeCaptionStyle(state.project.caption_style);
    if (code === "style_low_contrast") {
      state.project.caption_style = normalizeCaptionStyle(captionStylePresets.high_contrast);
    } else if (code === "style_weak_video_separation") {
      state.project.caption_style = normalizeCaptionStyle({
        ...style,
        preset: "custom",
        background_opacity: Math.max(style.background_opacity, 0.78),
        outline_size_percent: Math.max(style.outline_size_percent, 0.16),
      });
    } else if (code === "style_small_text") {
      state.project.caption_style = normalizeCaptionStyle({
        ...style,
        preset: "custom",
        font_size_percent: Math.max(style.font_size_percent, 7.5),
      });
    } else if (code === "style_edge_crowding") {
      state.project.caption_style = normalizeCaptionStyle({
        ...style,
        preset: "custom",
        max_width_percent: Math.min(style.max_width_percent, 88),
      });
    } else return;

    renderCaptionStyleControls();
    applyCaptionStyle();
    syncPlayback();
    storeCaptionStyle(state.project.id, state.project.caption_style);
    await saveProject();
    renderFindings();
    toast("Caption appearance updated.");
  }

  function styleFixLabel(code) {
    return ({
      style_low_contrast: "Use high-contrast preset",
      style_weak_video_separation: "Strengthen background",
      style_small_text: "Increase caption size",
      style_edge_crowding: "Restore safe width",
    })[code] || null;
  }

  function appendFixButton(item, label, handler) {
    if (!label || item.querySelector(".finding-fix")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "finding-fix";
    button.textContent = label;
    button.addEventListener("click", handler);
    item.append(button);
  }

  function rebuildFindingSummary(allFindings) {
    const overview = $("#findingOverview");
    overview.replaceChildren();
    $("#findingCount").textContent = `${allFindings.length} ${allFindings.length === 1 ? "finding" : "findings"}`;
    if (!allFindings.length) {
      overview.hidden = true;
      return;
    }
    overview.hidden = false;
    ["error", "warning", "info"].forEach((severity) => {
      const count = allFindings.filter((finding) => finding.severity === severity).length;
      if (!count) return;
      const summary = document.createElement("span");
      summary.className = `finding-summary ${severity}`;
      summary.textContent = `${count} ${severity}${count === 1 ? "" : "s"}`;
      overview.append(summary);
    });
  }

  renderFindings = function renderFindingsWithAppearanceChecks() {
    baseRenderFindings();
    if (!state.project) return;
    const list = $("#findingList");
    const severityOrder = { error: 0, warning: 1, info: 2 };
    const cueFindings = [...(state.project.findings || [])]
      .sort((left, right) => severityOrder[left.severity] - severityOrder[right.severity]);
    const renderedCueFindings = [...list.querySelectorAll(".finding")];
    renderedCueFindings.forEach((item, index) => {
      const finding = cueFindings[index];
      const label = findingFixLabel(finding);
      appendFixButton(item, label, () => applyFindingFix(finding));
    });

    const styleFindings = captionStyleReadabilityFindings();
    if (styleFindings.length) {
      list.querySelector(".success-note")?.remove();
      list.tabIndex = 0;
      styleFindings.forEach((finding) => {
        const item = document.createElement("div");
        item.className = `finding ${finding.severity} style-finding`;
        const severity = document.createElement("span");
        severity.className = "finding-severity";
        severity.textContent = `${finding.severity} · caption appearance`;
        const message = document.createElement("p");
        message.textContent = finding.message;
        item.append(severity, message);
        appendFixButton(item, styleFixLabel(finding.code), () => applyStyleFindingFix(finding.code));
        list.append(item);
      });
    }
    rebuildFindingSummary([...(state.project.findings || []), ...styleFindings]);
  };

  function scheduleAppearanceCheck() {
    requestAnimationFrame(() => {
      if (state.project && !workspaceView.hidden) renderFindings();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-caption-style]").forEach((control) => {
      control.addEventListener("input", scheduleAppearanceCheck);
      control.addEventListener("change", scheduleAppearanceCheck);
    });
    $("#captionStylePreset")?.addEventListener("change", scheduleAppearanceCheck);
    $("#resetCaptionStyle")?.addEventListener("click", scheduleAppearanceCheck);
  });
})();

// major-iterations: failed job retry
(() => {
  const baseUpdateJobPanel = updateJobPanel;
  const retryableJobKinds = new Set(["analysis", "mp4-export", "transcript-repair", "speaker-reanalysis"]);

  function installJobRecoveryActions() {
    if ($("#jobRecoveryActions")) return;
    const panel = $("#jobPanel");
    if (!panel) return;
    const actions = document.createElement("div");
    actions.id = "jobRecoveryActions";
    actions.className = "job-recovery-actions";
    actions.hidden = true;

    const retry = document.createElement("button");
    retry.id = "retryJob";
    retry.type = "button";
    retry.className = "secondary";
    retry.textContent = "Retry";
    retry.addEventListener("click", retryFailedJob);

    const dismiss = document.createElement("button");
    dismiss.id = "dismissFailedJob";
    dismiss.type = "button";
    dismiss.className = "text-button";
    dismiss.textContent = "Dismiss";
    dismiss.addEventListener("click", dismissFailedJob);

    actions.append(retry, dismiss);
    panel.append(actions);
  }

  updateJobPanel = function updateJobPanelWithRecovery(job) {
    baseUpdateJobPanel(job);
    installJobRecoveryActions();
    const actions = $("#jobRecoveryActions");
    const retry = $("#retryJob");
    const failed = job?.state === "failed";
    actions.hidden = !failed;
    if (!failed) return;
    const retryable = retryableJobKinds.has(job.kind);
    retry.hidden = !retryable;
    if (retryable) {
      retry.textContent = job.error_code === "job_interrupted" ? "Retry interrupted job" : "Retry";
    }
  };

  pollJob = async function pollJobWithFailureRecovery() {
    if (!state.activeJob || !state.activeJobProjectId) return;
    const trackedJobId = state.activeJob.id;
    const trackedProjectId = state.activeJobProjectId;
    const trackedProjectName = state.activeJobProjectName;
    try {
      const job = await api(`/api/projects/${trackedProjectId}/jobs/${trackedJobId}`);
      if (state.activeJob?.id !== trackedJobId || String(state.activeJobProjectId) !== String(trackedProjectId)) return;
      state.activeJob = job;
      updateJobPanel(job);
      if (activeJobStates.has(job.state)) {
        state.pollTimer = setTimeout(pollJob, 1100);
        return;
      }

      const viewingTrackedProject = !workspaceView.hidden
        && String(state.project?.id) === String(trackedProjectId);

      if (job.state === "completed") {
        const completedProject = await api(`/api/projects/${trackedProjectId}`);
        if (viewingTrackedProject) {
          state.project = completedProject;
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
        } else {
          if (!homeView.hidden) await loadProjects();
          toast(`${trackedProjectName} finished processing.`);
        }
        clearFinishedJobSoon(job.id);
        return;
      }

      if (job.state === "failed") {
        const message = job.error || job.message || `${trackedProjectName} could not be processed.`;
        toast(message, "error");
        $("#jobPanel").hidden = false;
        updateJobPanel(job);
        if (!retryableJobKinds.has(job.kind)) {
          $("#jobMessage").textContent = `${message} Restart this operation from its original project control.`;
        }
        syncActiveJobIndicators();
        return;
      }

      if (job.state === "cancelled") {
        toast(`Processing cancelled for ${trackedProjectName}. Saved work was not changed.`);
        clearFinishedJobSoon(job.id);
      }
    } catch (error) {
      toast(error.message, "error");
    }
  };

  function clearFinishedJobSoon(jobId) {
    setTimeout(() => {
      if (state.activeJob?.id !== jobId) return;
      clearTrackedJob();
    }, 1800);
  }

  function clearTrackedJob() {
    clearTimeout(state.pollTimer);
    $("#jobPanel").hidden = true;
    state.activeJob = null;
    state.activeJobProjectId = null;
    state.activeJobProjectName = "";
    syncActiveJobIndicators();
  }

  function dismissFailedJob() {
    if (state.activeJob?.state !== "failed") return;
    clearTrackedJob();
  }

  async function retryFailedJob() {
    if (state.activeJob?.state !== "failed" || !state.activeJobProjectId) return;
    const failedJob = state.activeJob;
    const projectId = state.activeJobProjectId;
    const retryButton = $("#retryJob");
    retryButton.disabled = true;
    retryButton.textContent = "Starting…";
    try {
      const project = await api(`/api/projects/${projectId}`);
      let job;
      if (failedJob.kind === "analysis") {
        job = await api(`/api/projects/${projectId}/analyze`, { method: "POST" });
      } else if (failedJob.kind === "mp4-export") {
        job = await api(`/api/projects/${projectId}/exports/mp4`, { method: "POST" });
      } else if (failedJob.kind === "transcript-repair") {
        job = await api(`/api/projects/${projectId}/repair-transcript`, { method: "POST" });
      } else if (failedJob.kind === "speaker-reanalysis") {
        job = await api(`/api/projects/${projectId}/reanalyze-speakers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ expected_speaker_count: project.expected_speaker_count ?? null }),
        });
      } else {
        toast("This operation needs its original inputs and must be restarted from the project.", "error");
        return;
      }
      monitorJob(job, projectId, project.name);
      toast(`Retry started for ${project.name}.`);
    } catch (error) {
      toast(error.message, "error");
      updateJobPanel(failedJob);
    } finally {
      retryButton.disabled = false;
      if (state.activeJob?.state === "failed") {
        retryButton.textContent = state.activeJob.error_code === "job_interrupted" ? "Retry interrupted job" : "Retry";
      }
    }
  }

  document.addEventListener("DOMContentLoaded", installJobRecoveryActions);
})();
