(() => {
  const languageStorageKey = "accessible-caption-transcription-language";
  const sdhStorageKey = "accessible-caption-sdh-mode";
  const projectViewStorageKey = "accessible-caption-project-view";
  const languages = [
    ["auto", "Auto-detect"], ["en", "English"], ["es", "Spanish"], ["fr", "French"],
    ["de", "German"], ["it", "Italian"], ["pt", "Portuguese"], ["nl", "Dutch"],
    ["pl", "Polish"], ["ru", "Russian"], ["uk", "Ukrainian"], ["zh", "Chinese"],
    ["ja", "Japanese"], ["ko", "Korean"], ["ar", "Arabic"], ["hi", "Hindi"],
    ["tr", "Turkish"], ["vi", "Vietnamese"], ["id", "Indonesian"], ["th", "Thai"],
  ];
  const sdhModes = [
    ["off", "Off", "Do not add automatic non-speech sound captions."],
    ["conservative", "Conservative", "Add only higher-confidence meaningful sounds."],
    ["full", "Full SDH", "Use the complete accessibility-focused sound-caption workflow."],
  ];
  let modelPollTimer = null;

  function readPreference(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
  }
  function writePreference(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* Session choice still works. */ }
  }
  function defaultPreferences() {
    const language = readPreference(languageStorageKey, "en");
    const sdhMode = readPreference(sdhStorageKey, "full");
    return {
      transcription_language: languages.some(([code]) => code === language) ? language : "en",
      sdh_mode: sdhModes.some(([code]) => code === sdhMode) ? sdhMode : "full",
    };
  }
  function languageLabel(code) {
    return languages.find(([value]) => value === code)?.[1] || code;
  }
  function sdhLabel(code) {
    return sdhModes.find(([value]) => value === code)?.[1] || code;
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = function fetchWithCaptioningPreferences(input, init = {}) {
    const url = typeof input === "string" ? input : input?.url || "";
    const preferences = defaultPreferences();
    if (url.endsWith("/api/projects/upload") && init.body instanceof FormData) {
      if (!init.body.has("transcription_language")) init.body.set("transcription_language", preferences.transcription_language);
      if (!init.body.has("sdh_mode")) init.body.set("sdh_mode", preferences.sdh_mode);
    }
    if (url.endsWith("/api/projects/youtube") && typeof init.body === "string") {
      try {
        const body = JSON.parse(init.body);
        body.transcription_language ??= preferences.transcription_language;
        body.sdh_mode ??= preferences.sdh_mode;
        init = { ...init, body: JSON.stringify(body) };
      } catch (_) { /* Leave unrelated JSON untouched. */ }
    }
    return nativeFetch(input, init);
  };

  function optionMarkup(items) {
    return items.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
  }

  function installStyles() {
    if (document.querySelector("#finalRoadmapStyles")) return;
    const style = document.createElement("style");
    style.id = "finalRoadmapStyles";
    style.textContent = `
      .captioning-options { margin: .8rem 0 .15rem; border-top: 1px solid var(--soft-line); border-bottom: 1px solid var(--soft-line); }
      .captioning-options summary { display:flex; align-items:center; justify-content:space-between; gap:.75rem; padding:.65rem .1rem; cursor:pointer; color:var(--ink); font-size:.8rem; font-weight:800; }
      .captioning-options summary span { color:var(--muted); font-size:.72rem; font-weight:700; }
      .captioning-options-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.75rem; padding:0 .1rem .8rem; }
      .captioning-options-grid label, .project-preference-card label { display:grid; gap:.35rem; color:var(--ink); font-size:.78rem; font-weight:750; }
      .captioning-options-grid select, .project-preference-card select { width:100%; border:1px solid #aeb9ce; border-radius:9px; padding:.58rem .65rem; color:var(--ink); background:var(--control); }
      .captioning-options-note { grid-column:1/-1; margin:0; color:var(--muted); font-size:.72rem; line-height:1.45; }
      .project-view-select { min-width:118px; }
      .project-grid:not(.project-grid-compact) { grid-template-columns:repeat(auto-fill,minmax(290px,1fr)); gap:.9rem; align-items:start; }
      .project-grid:not(.project-grid-compact) .project-card { height:272px; min-height:272px; overflow:hidden; padding:0; display:flex; flex-direction:column; }
      .project-grid:not(.project-grid-compact) .project-open { display:flex !important; flex:1 1 auto; flex-direction:column; align-items:stretch; width:100%; min-width:0; min-height:0; padding:0 !important; }
      .project-grid:not(.project-grid-compact) .project-thumbnail { order:-2; width:100%; height:112px; object-fit:cover; display:block; margin:0; border:0; border-bottom:1px solid var(--soft-line); border-radius:0; background:var(--wash); }
      .project-grid:not(.project-grid-compact) .project-open:has(.project-thumbnail) .project-type { display:none !important; }
      .project-grid:not(.project-grid-compact) .project-open:not(:has(.project-thumbnail)) .project-type { order:-2; width:100%; height:112px; min-height:112px; margin:0; border-radius:0; border-bottom:1px solid var(--soft-line); display:flex; align-items:center; justify-content:center; background:var(--wash); }
      .project-grid:not(.project-grid-compact) .project-open > strong { width:100%; max-width:none; min-height:3.1rem; max-height:3.1rem; margin:0; padding:.72rem .9rem .18rem; font-size:.96rem; line-height:1.3; white-space:normal; overflow-wrap:anywhere; word-break:break-word; overflow:hidden; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
      .project-grid:not(.project-grid-compact) .project-open > span:not(.project-type):not(.project-job-status) { width:100%; min-height:1.15rem; padding:0 .9rem .55rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .project-grid:not(.project-grid-compact) .project-job-status { margin:.05rem .9rem .75rem; }
      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.7rem; }
      .project-grid:not(.project-grid-compact) .project-favorite { top:.55rem; right:.55rem; background:color-mix(in srgb,var(--paper) 86%,transparent); box-shadow:0 2px 8px rgba(20,35,70,.14); -webkit-backdrop-filter:blur(8px); backdrop-filter:blur(8px); }

      .project-grid.project-grid-compact { grid-template-columns:1fr; gap:.48rem; }
      .project-grid-compact .project-card { min-height:0; overflow:visible; display:grid; grid-template-columns:minmax(0,1fr) auto 34px; align-items:center; gap:.7rem; padding:.68rem .75rem; }
      .project-grid-compact .project-card:hover { transform:none; }
      .project-grid-compact .project-open { min-width:0; display:grid !important; grid-template-columns:44px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.72rem; row-gap:.08rem; align-items:center; padding:0 !important; }
      .project-grid-compact .project-open .project-type { grid-column:1; grid-row:1 / span 2; width:40px; height:40px; margin:0; }
      .project-grid-compact .project-thumbnail { width:72px; height:44px; object-fit:cover; border-radius:7px; border:1px solid var(--line); background:var(--wash); grid-column:1; grid-row:1 / span 2; margin:0; }
      .project-grid-compact .project-open:has(.project-thumbnail) { grid-template-columns:72px minmax(0,1fr); }
      .project-grid-compact .project-open:has(.project-thumbnail) .project-type { display:none !important; }
      .project-grid-compact .project-open > strong { grid-column:2; grid-row:1; min-width:0; max-width:none; margin:0; padding:0; font-size:.9rem; line-height:1.25; white-space:normal; overflow-wrap:anywhere; word-break:break-word; }
      .project-grid-compact .project-open > span:not(.project-type):not(.project-job-status) { grid-column:2; grid-row:2; min-width:0; padding:0; }
      .project-grid-compact .project-job-status { grid-column:2; margin:.18rem 0 0; }
      .project-grid-compact .project-card-actions { grid-column:2; align-self:center; display:flex; gap:.35rem; margin:0; padding:0; border-top:0; }
      .project-grid-compact .project-action { min-height:30px; padding:.3rem .5rem; }
      .project-grid-compact .project-favorite { position:static; grid-column:3; justify-self:end; width:32px; height:32px; }
      .model-manager-details { border-top:1px solid var(--line); padding-top:.75rem; }
      .model-manager-details > summary { cursor:pointer; font-weight:800; }
      .model-manager-copy { margin:.4rem 0 .7rem; color:var(--muted); font-size:.78rem; }
      .model-manager-list { display:grid; gap:.45rem; }
      .model-manager-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:.75rem; padding:.65rem .7rem; border-radius:9px; background:var(--wash); }
      .model-manager-row > div { min-width:0; display:grid; gap:.12rem; }
      .model-manager-row strong { font-size:.78rem; }
      .model-manager-row span { color:var(--muted); font-size:.7rem; overflow-wrap:anywhere; }
      .model-manager-row button { min-height:32px; padding:.35rem .55rem; }
      .model-manager-error { color:var(--danger) !important; }
      .project-preference-dialog { width:min(520px,calc(100vw - 2rem)); }
      .project-preference-card { display:grid; gap:.8rem; }
      .export-grid [data-export="report"] { border-color:color-mix(in srgb,var(--blue) 28%,var(--line)); }
      @media (max-width:560px) {
        .captioning-options-grid { grid-template-columns:1fr; }
        .captioning-options-note { grid-column:1; }
        .project-view-select { grid-column:1 / -1; min-width:0; }
        .project-grid:not(.project-grid-compact) .project-card { height:264px; min-height:264px; }
        .project-grid:not(.project-grid-compact) .project-thumbnail { height:104px; }
        .project-grid:not(.project-grid-compact) .project-open:not(:has(.project-thumbnail)) .project-type { height:104px; min-height:104px; }
        .project-grid-compact .project-card { grid-template-columns:minmax(0,1fr) 34px; align-items:start; }
        .project-grid-compact .project-open { grid-column:1 / -1; grid-row:1; padding-right:2.55rem !important; }
        .project-grid-compact .project-open:has(.project-thumbnail) { grid-template-columns:58px minmax(0,1fr); }
        .project-grid-compact .project-thumbnail { width:58px; height:38px; }
        .project-grid-compact .project-card-actions { grid-column:1 / -1; grid-row:2; padding-top:.55rem; border-top:1px solid var(--soft-line); }
        .project-grid-compact .project-favorite { grid-column:2; grid-row:1; z-index:2; }
        .model-manager-row { grid-template-columns:1fr; }
        .model-manager-row button { width:100%; }
      }
      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; scroll-behavior:auto !important; }
      }
      @media (forced-colors: active) {
        .project-card, .model-manager-row, .captioning-options, .waveform-canvas-wrap { border:1px solid CanvasText; }
        button, input, select, summary { forced-color-adjust:auto; }
      }
    `;
    document.head.append(style);
  }

  function installImportOptions() {
    if (document.querySelector("#captioningOptions")) return;
    const tabs = document.querySelector(".import-card .tabs");
    if (!tabs) return;
    const details = document.createElement("details");
    details.id = "captioningOptions";
    details.className = "captioning-options";
    details.innerHTML = `
      <summary>Captioning options <span id="captioningOptionsSummary"></span></summary>
      <div class="captioning-options-grid">
        <label for="defaultTranscriptionLanguage">Language<select id="defaultTranscriptionLanguage">${optionMarkup(languages)}</select></label>
        <label for="defaultSdhMode">Sound captions<select id="defaultSdhMode">${optionMarkup(sdhModes)}</select></label>
        <p class="captioning-options-note">Auto-detect and non-English choices use multilingual Whisper models. These defaults apply to new automatic analyses and stay on this computer.</p>
      </div>`;
    tabs.after(details);
    const preferences = defaultPreferences();
    details.querySelector("#defaultTranscriptionLanguage").value = preferences.transcription_language;
    details.querySelector("#defaultSdhMode").value = preferences.sdh_mode;
    const update = () => {
      const language = details.querySelector("#defaultTranscriptionLanguage").value;
      const sdh = details.querySelector("#defaultSdhMode").value;
      writePreference(languageStorageKey, language);
      writePreference(sdhStorageKey, sdh);
      details.querySelector("#captioningOptionsSummary").textContent = `${languageLabel(language)} · ${sdhLabel(sdh)}`;
    };
    details.querySelectorAll("select").forEach((select) => select.addEventListener("change", update));
    update();
  }

  function installProjectPreferenceDialog() {
    if (document.querySelector("#projectPreferenceDialog")) return;
    const dialog = document.createElement("dialog");
    dialog.id = "projectPreferenceDialog";
    dialog.className = "project-preference-dialog";
    dialog.setAttribute("aria-labelledby", "projectPreferenceTitle");
    dialog.innerHTML = `
      <form id="projectPreferenceForm" class="dialog-card project-preference-card">
        <div class="dialog-heading"><div><p class="eyebrow">Automatic analysis</p><h2 id="projectPreferenceTitle">Transcription options</h2></div><button id="closeProjectPreferences" class="icon-button" type="button" aria-label="Close transcription options">×</button></div>
        <p class="field-note">These options are saved with this project. Run analysis again after changing them to regenerate automatic captions.</p>
        <label for="projectTranscriptionLanguage">Language<select id="projectTranscriptionLanguage">${optionMarkup(languages)}</select></label>
        <label for="projectSdhMode">Sound captions<select id="projectSdhMode">${optionMarkup(sdhModes)}</select></label>
        <div class="button-row dialog-actions"><span class="dialog-action-spacer"></span><button id="cancelProjectPreferences" class="secondary" type="button">Cancel</button><button class="primary" type="submit">Save options</button></div>
      </form>`;
    document.body.append(dialog);
    dialog.querySelector("#closeProjectPreferences").addEventListener("click", () => dialog.close());
    dialog.querySelector("#cancelProjectPreferences").addEventListener("click", () => dialog.close());
    dialog.querySelector("#projectPreferenceForm").addEventListener("submit", saveProjectPreferences);
  }

  function installProjectPreferenceAction() {
    const more = document.querySelector(".editor-more-popover");
    if (!more || document.querySelector("#projectPreferenceButton")) return;
    const button = document.createElement("button");
    button.id = "projectPreferenceButton";
    button.className = "secondary editor-action editor-more-action";
    button.type = "button";
    button.textContent = "Transcription options";
    button.addEventListener("click", () => {
      if (!state.project) return;
      document.querySelector("#projectTranscriptionLanguage").value = state.project.transcription_language || "en";
      document.querySelector("#projectSdhMode").value = state.project.sdh_mode || "full";
      document.querySelector("#projectPreferenceDialog").showModal();
    });
    more.append(button);
  }

  async function saveProjectPreferences(event) {
    event.preventDefault();
    if (!state.project) return;
    const submit = event.currentTarget.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      const project = await api(`/api/projects/${state.project.id}/preferences`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcription_language: document.querySelector("#projectTranscriptionLanguage").value,
          sdh_mode: document.querySelector("#projectSdhMode").value,
        }),
      });
      state.project = project;
      document.querySelector("#projectPreferenceDialog").close();
      toast("Transcription options saved. Run analysis again to apply them to automatic captions.");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      submit.disabled = false;
    }
  }

  function installExportOptions() {
    const grid = document.querySelector("#exportDialog .export-grid");
    if (!grid) return;
    const add = (format, title, description) => {
      if (grid.querySelector(`[data-export="${format}"]`)) return;
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.export = format;
      button.innerHTML = `<strong>${title}</strong><span>${description}</span>`;
      button.addEventListener("click", () => createExport(format));
      grid.append(button);
    };
    add("ttml", "TTML captions", "Timed Text format for broadcast and enterprise workflows");
    add("report", "Accessibility report", "Saved authoring findings, statistics, and review status");
  }

  function projectViewMode() {
    const value = readPreference(projectViewStorageKey, "default");
    return value === "compact" ? "compact" : "default";
  }

  function cardProjectTitle(name) {
    const value = String(name || "");
    const maximumLength = 62;
    if (value.length <= maximumLength) return value;
    const extensionMatch = value.match(/(\.[A-Za-z0-9]{1,10})$/);
    const extension = extensionMatch?.[1] || "";
    const stem = extension ? value.slice(0, -extension.length) : value;
    const visibleStemLength = Math.max(24, maximumLength - extension.length - 1);
    return `${stem.slice(0, visibleStemLength).trimEnd()}…${extension}`;
  }

  function syncProjectCardTitles() {
    const compact = projectViewMode() === "compact";
    document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {
      const project = state.projects.find((item) => String(item.id) === String(card.dataset.projectId));
      const title = card.querySelector(".project-open > strong");
      if (!project || !title) return;
      const fullName = String(project.name || "");
      title.textContent = compact ? fullName : cardProjectTitle(fullName);
      title.title = fullName;
    });
  }

  function applyProjectViewMode() {
    const list = document.querySelector("#projectList");
    if (!list) return;
    const mode = projectViewMode();
    list.classList.toggle("project-grid-compact", mode === "compact");
    list.dataset.viewMode = mode;
    const select = document.querySelector("#projectViewMode");
    if (select && select.value !== mode) select.value = mode;
    syncProjectCardTitles();
  }

  function installProjectViewControl() {
    if (document.querySelector("#projectViewMode")) {
      applyProjectViewMode();
      return;
    }
    const actions = document.querySelector(".project-browser-actions") || document.querySelector(".project-refine-controls");
    if (!actions) return;
    const label = document.createElement("label");
    label.className = "project-compact-select project-view-select";
    label.innerHTML = `
      <span class="sr-only">Project view</span>
      <select id="projectViewMode" aria-label="Project view">
        <option value="default">Cards</option>
        <option value="compact">Compact list</option>
      </select>`;
    const count = actions.querySelector("#projectFilterCount");
    if (count) actions.insertBefore(label, count);
    else actions.append(label);
    const select = label.querySelector("select");
    select.value = projectViewMode();
    select.addEventListener("change", () => {
      writePreference(projectViewStorageKey, select.value);
      applyProjectViewMode();
    });
    applyProjectViewMode();
  }

  const previousRenderProjectsFinal = renderProjects;
  renderProjects = function renderProjectsWithThumbnails() {
    previousRenderProjectsFinal();
    installProjectViewControl();
    applyProjectViewMode();
    document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {
      const project = state.projects.find((item) => String(item.id) === String(card.dataset.projectId));
      if (!project?.media?.has_video || card.querySelector(".project-thumbnail")) return;
      const image = document.createElement("img");
      image.className = "project-thumbnail";
      image.alt = "";
      image.loading = "lazy";
      image.src = `/api/projects/${encodeURIComponent(project.id)}/thumbnail`;
      image.addEventListener("error", () => image.remove(), { once: true });
      card.querySelector(".project-open")?.prepend(image);
    });
    syncProjectCardTitles();
  };

  function installModelManager() {
    if (document.querySelector("#modelManagerSection")) return;
    const readiness = document.querySelector("#systemReadiness");
    const storageSection = [...document.querySelectorAll("#settingsDialog .dialog-card > section")].find(
      (section) => section.querySelector("h3")?.textContent?.trim() === "Storage"
    );
    const section = document.createElement("section");
    section.id = "modelManagerSection";
    section.innerHTML = `
      <details class="model-manager-details">
        <summary>Model manager</summary>
        <p class="model-manager-copy">Inspect, preload, or remove individual local models. Downloads stay in the studio model cache.</p>
        <div id="modelManagerList" class="model-manager-list" role="status"></div>
      </details>`;
    if (readiness) readiness.after(section);
    else if (storageSection) storageSection.before(section);
    else document.querySelector("#settingsDialog .dialog-card")?.append(section);
    section.querySelector("details").addEventListener("toggle", (event) => {
      if (event.currentTarget.open) loadModels();
      else clearTimeout(modelPollTimer);
    });
  }

  async function loadModels() {
    const list = document.querySelector("#modelManagerList");
    if (!list) return;
    try {
      const models = await api("/api/models");
      renderModels(models);
      clearTimeout(modelPollTimer);
      if (models.some((model) => model.status === "installing")) {
        modelPollTimer = setTimeout(loadModels, 1600);
      }
    } catch (error) {
      list.textContent = `Model status unavailable: ${error.message}`;
    }
  }

  function renderModels(models) {
    const list = document.querySelector("#modelManagerList");
    list.replaceChildren();
    models.forEach((model) => {
      const row = document.createElement("div");
      row.className = "model-manager-row";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = model.label;
      const status = document.createElement("span");
      const size = model.size_bytes ? formatBytes(model.size_bytes) : "No local files";
      status.textContent = model.status === "installing" ? `Downloading · ${size}` : model.installed ? `Installed · ${size}` : size;
      copy.append(title, status);
      if (model.error) {
        const error = document.createElement("span");
        error.className = "model-manager-error";
        error.textContent = model.error;
        copy.append(error);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = model.installed ? "danger-secondary" : "secondary";
      button.disabled = model.status === "installing";
      button.textContent = model.status === "installing" ? "Downloading…" : model.installed ? "Remove" : "Preload";
      button.addEventListener("click", () => changeModel(model, button));
      row.append(copy, button);
      list.append(row);
    });
  }

  async function changeModel(model, button) {
    button.disabled = true;
    try {
      await api(`/api/models/${encodeURIComponent(model.id)}${model.installed ? "" : "/install"}`, {
        method: model.installed ? "DELETE" : "POST",
      });
      await loadModels();
    } catch (error) {
      toast(error.message, "error");
      button.disabled = false;
    }
  }

  function installGenericRetry() {
    const current = document.querySelector("#retryJob");
    if (!current || current.dataset.genericRetry === "true") return;
    const replacement = current.cloneNode(true);
    replacement.dataset.genericRetry = "true";
    current.replaceWith(replacement);
    replacement.addEventListener("click", retryTrackedJob);

    const previousUpdateJobPanelFinal = updateJobPanel;
    updateJobPanel = function updateJobPanelWithGenericRetry(job) {
      previousUpdateJobPanelFinal(job);
      const actions = document.querySelector("#jobRecoveryActions");
      const retry = document.querySelector("#retryJob");
      if (job?.state === "failed" && actions && retry) {
        actions.hidden = false;
        retry.hidden = false;
        retry.textContent = job.error_code === "job_interrupted" ? "Retry interrupted job" : "Retry";
      }
    };
  }

  async function retryTrackedJob() {
    if (state.activeJob?.state !== "failed" || !state.activeJobProjectId) return;
    const button = document.querySelector("#retryJob");
    button.disabled = true;
    button.textContent = "Starting…";
    try {
      const job = await api(
        `/api/projects/${state.activeJobProjectId}/jobs/${state.activeJob.id}/retry`,
        { method: "POST" },
      );
      const project = await api(`/api/projects/${state.activeJobProjectId}`);
      monitorJob(job, project.id, project.name);
      toast(`Retry started for ${project.name}.`);
    } catch (error) {
      toast(error.message, "error");
      button.disabled = false;
      button.textContent = "Retry";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    installStyles();
    installImportOptions();
    installProjectPreferenceDialog();
    installProjectPreferenceAction();
    installExportOptions();
    installModelManager();
    installGenericRetry();
    renderProjects();
  });
})();
