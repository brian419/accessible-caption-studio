from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src/accessible_caption_studio/web/app.js"
STYLES = ROOT / "src/accessible_caption_studio/web/styles.css"
WEBAPP = ROOT / "src/accessible_caption_studio/webapp.py"

JS_MARKER = "// major-iterations: productivity tools"
CSS_MARKER = "/* major-iterations: productivity tools */"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch anchor was not found in {path}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: Path, marker: str, addition: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    path.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n", encoding="utf-8")


PRODUCTIVITY_JS = r'''
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
    controls.innerHTML = `
      <label class="project-search-field" for="projectSearch">
        <span>Search projects</span>
        <input id="projectSearch" type="search" placeholder="Search by project name" autocomplete="off">
      </label>
      <label for="projectTypeFilter">Type
        <select id="projectTypeFilter">
          <option value="all">All media</option>
          <option value="video">Video</option>
          <option value="audio">Audio only</option>
        </select>
      </label>
      <label for="projectSort">Sort
        <select id="projectSort">
          <option value="recent">Most recent</option>
          <option value="oldest">Oldest updated</option>
          <option value="name">Name A–Z</option>
          <option value="captions">Most captions</option>
        </select>
      </label>
      <span id="projectFilterCount" class="project-filter-count" role="status"></span>`;
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
    if ($("#captionProductivityTools")) return;
    const editorHeading = document.querySelector(".editor-heading");
    if (!editorHeading) return;
    const tools = document.createElement("div");
    tools.id = "captionProductivityTools";
    tools.className = "caption-productivity-tools";
    tools.innerHTML = `
      <div class="caption-search-row">
        <label for="captionSearch"><span>Find caption text</span><input id="captionSearch" type="search" placeholder="Find text" autocomplete="off"></label>
        <button id="captionFindNext" class="secondary editor-action" type="button">Find next</button>
        <button id="lowConfidenceReview" class="secondary editor-action" type="button">Review uncertain</button>
      </div>
      <div class="caption-replace-row">
        <label for="captionReplace"><span>Replace with</span><input id="captionReplace" type="text" placeholder="Replacement text"></label>
        <button id="captionReplaceCurrent" class="secondary editor-action" type="button">Replace</button>
        <button id="captionReplaceAll" class="secondary editor-action" type="button">Replace all</button>
        <span id="captionSearchStatus" class="caption-search-status" role="status"></span>
      </div>`;
    editorHeading.append(tools);

    const redoButton = document.createElement("button");
    redoButton.id = "redoButton";
    redoButton.className = "secondary editor-action";
    redoButton.type = "button";
    redoButton.textContent = "Redo";
    redoButton.disabled = true;
    $("#undoButton").after(redoButton);

    $("#captionSearch").addEventListener("input", () => {
      productivity.captionSearchIndex = -1;
      productivity.captionSearchCueId = null;
      updateCaptionProductivityStatus();
    });
    $("#captionSearch").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        findNextCaption();
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
    if (help) {
      const button = document.createElement("button");
      button.id = "safeAreaToggle";
      button.className = "text-button safe-area-toggle";
      button.type = "button";
      button.setAttribute("aria-pressed", "false");
      button.textContent = "Show safe areas";
      button.addEventListener("click", () => {
        const enabled = guides.hidden;
        guides.hidden = !enabled;
        button.setAttribute("aria-pressed", String(enabled));
        button.textContent = enabled ? "Hide safe areas" : "Show safe areas";
      });
      help.append(button);
      const shortcut = document.createElement("span");
      shortcut.className = "precision-shortcuts";
      shortcut.innerHTML = `<kbd>Shift</kbd>+<kbd>←/→</kbd> 0.1s · <kbd>Option/Alt</kbd>+<kbd>←/→</kbd> 0.5s · <kbd>[</kbd>/<kbd>]</kbd> set cue edges · <kbd>P</kbd>/<kbd>N</kbd> previous/next`;
      help.append(shortcut);
    }
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
'''

PRODUCTIVITY_CSS = r'''
/* major-iterations: productivity tools */
.project-browser-controls {
  display: grid;
  grid-template-columns: minmax(220px, 1.5fr) minmax(130px, .6fr) minmax(150px, .7fr) auto;
  gap: .7rem;
  align-items: end;
  margin: 0 0 .85rem;
  padding: .85rem;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--paper);
}
.project-browser-controls label,
.caption-productivity-tools label { display: grid; gap: .3rem; color: var(--muted); font-size: .76rem; font-weight: 800; }
.project-browser-controls input,
.project-browser-controls select,
.caption-productivity-tools input {
  min-width: 0;
  width: 100%;
  border: 1px solid #aeb9ce;
  border-radius: 8px;
  padding: .58rem .65rem;
  color: var(--ink);
  background: var(--control);
}
.project-filter-count { align-self: center; color: var(--muted); font-size: .78rem; white-space: nowrap; }
.project-filter-empty { margin-top: .75rem; }
.caption-productivity-tools { display: grid; gap: .55rem; padding-top: .7rem; border-top: 1px solid var(--soft-line); }
.caption-search-row,
.caption-replace-row { display: grid; grid-template-columns: minmax(170px, 1fr) auto auto; gap: .5rem; align-items: end; }
.caption-replace-row { grid-template-columns: minmax(170px, 1fr) auto auto minmax(100px, auto); }
.caption-search-status { align-self: center; color: var(--muted); font-size: .75rem; text-align: right; }
.cue-row.search-match { background: color-mix(in srgb, var(--sky) 72%, var(--paper)); box-shadow: inset 4px 0 var(--blue), 0 0 0 1px color-mix(in srgb, var(--blue) 28%, transparent); }
.safe-area-guides { position: absolute; inset: 0; z-index: 5; pointer-events: none; }
.safe-area-guides > div { position: absolute; border: 1px dashed rgba(255,255,255,.78); box-shadow: 0 0 0 1px rgba(0,0,0,.4); }
.safe-area-guides span { position: absolute; top: .2rem; left: .3rem; padding: .12rem .3rem; border-radius: 4px; color: #fff; background: rgba(0,0,0,.68); font-size: .62rem; font-weight: 800; }
.safe-area-action { inset: 5%; }
.safe-area-title { inset: 10%; }
.safe-area-toggle { margin-left: auto; font-size: .76rem; }
.precision-shortcuts { flex-basis: 100%; line-height: 1.6; }
.system-readiness-list { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-top: .7rem; }
.system-readiness-list > div { display: flex; justify-content: space-between; gap: .75rem; padding: .65rem .7rem; border-radius: 8px; background: var(--wash); font-size: .8rem; }
.readiness-ok { color: var(--teal); font-weight: 800; }
.readiness-warning { color: var(--warning); font-weight: 800; }
@media (max-width: 760px) {
  .project-browser-controls { grid-template-columns: 1fr 1fr; }
  .project-search-field, .project-filter-count { grid-column: 1 / -1; }
  .caption-search-row, .caption-replace-row { grid-template-columns: 1fr 1fr; }
  .caption-search-row label, .caption-replace-row label, .caption-search-status { grid-column: 1 / -1; }
  .caption-search-status { text-align: left; }
  .system-readiness-list { grid-template-columns: 1fr; }
}
'''


def main() -> None:
    append_once(APP_JS, JS_MARKER, PRODUCTIVITY_JS)
    append_once(STYLES, CSS_MARKER, PRODUCTIVITY_CSS)

    webapp_text = WEBAPP.read_text(encoding="utf-8")
    if "import sys\n" not in webapp_text:
        replace_once(WEBAPP, "import subprocess\n", "import subprocess\nimport sys\n")

    webapp_text = WEBAPP.read_text(encoding="utf-8")
    if '"ffprobe": shutil.which("ffprobe") is not None' not in webapp_text:
        replace_once(
            WEBAPP,
            '            "ffmpeg": shutil.which("ffmpeg") is not None,\n            "speaker_engine": "local-ecapa",',
            '            "ffmpeg": shutil.which("ffmpeg") is not None,\n'
            '            "ffprobe": shutil.which("ffprobe") is not None,\n'
            '            "python_version": sys.version.split()[0],\n'
            '            "free_disk_bytes": shutil.disk_usage(root).free,\n'
            '            "model_cache_bytes": store.summary().models_bytes,\n'
            '            "recovered_jobs": len(jobs.recovered_job_ids),\n'
            '            "speaker_engine": "local-ecapa",',
        )


if __name__ == "__main__":
    main()
