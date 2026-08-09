from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/accessible_caption_studio/web/app.js"
CSS = ROOT / "src/accessible_caption_studio/web/styles.css"

app = APP.read_text(encoding="utf-8")
css = CSS.read_text(encoding="utf-8")

project_controls = r'''  function installProjectControls() {
    if ($("#projectBrowserControls")) return;
    const container = document.querySelector(".project-list-container");
    if (!container) return;
    const controls = document.createElement("div");
    controls.id = "projectBrowserControls";
    controls.className = "project-browser-controls";
    controls.innerHTML = `
      <div class="project-search-cluster">
        <label class="project-search-field" for="projectSearch">
          <span>Search projects</span>
          <input id="projectSearch" type="search" placeholder="Search by project name" autocomplete="off">
        </label>
        <span id="projectFilterCount" class="project-filter-count" role="status"></span>
      </div>
      <div class="project-refine-controls" role="group" aria-label="Project view options">
        <label for="projectTypeFilter"><span>Media</span>
          <select id="projectTypeFilter">
            <option value="all">All media</option>
            <option value="video">Video</option>
            <option value="audio">Audio only</option>
          </select>
        </label>
        <label for="projectSort"><span>Sort</span>
          <select id="projectSort">
            <option value="recent">Most recent</option>
            <option value="oldest">Oldest updated</option>
            <option value="name">Name A-Z</option>
            <option value="captions">Most captions</option>
          </select>
        </label>
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

'''

caption_tools = r'''  function installCaptionTools() {
    if ($("#captionProductivityTools")) return;
    const editorHeading = document.querySelector(".editor-heading");
    if (!editorHeading) return;

    const redoButton = document.createElement("button");
    redoButton.id = "redoButton";
    redoButton.className = "secondary editor-action";
    redoButton.type = "button";
    redoButton.textContent = "Redo";
    redoButton.disabled = true;
    $("#undoButton").after(redoButton);

    const titleRow = editorHeading.querySelector(".editor-title-row");
    const addButton = $("#addCueButton");
    const titleActions = document.createElement("div");
    titleActions.className = "editor-title-actions";
    const reviewButton = document.createElement("button");
    reviewButton.id = "lowConfidenceReview";
    reviewButton.className = "secondary editor-review-action";
    reviewButton.type = "button";
    reviewButton.textContent = "Review uncertain";
    titleActions.append(reviewButton);
    if (addButton) titleActions.append(addButton);
    titleRow?.append(titleActions);

    const tools = document.createElement("details");
    tools.id = "captionProductivityTools";
    tools.className = "caption-productivity-tools";
    tools.innerHTML = `
      <summary>
        <span class="caption-find-summary-copy">
          <strong>Find & replace captions</strong>
          <small>Search the whole transcript without crowding the timeline.</small>
        </span>
        <span id="captionSearchStatus" class="caption-search-status" role="status"></span>
      </summary>
      <div class="caption-find-body">
        <div class="caption-search-row">
          <label for="captionSearch"><span>Find caption text</span><input id="captionSearch" type="search" placeholder="Find text in captions" autocomplete="off"></label>
          <button id="captionFindNext" class="secondary editor-action" type="button">Find next</button>
        </div>
        <div class="caption-replace-row">
          <label for="captionReplace"><span>Replace with</span><input id="captionReplace" type="text" placeholder="Replacement text"></label>
          <button id="captionReplaceCurrent" class="secondary editor-action" type="button">Replace</button>
          <button id="captionReplaceAll" class="secondary editor-action" type="button">Replace all</button>
        </div>
      </div>`;
    editorHeading.append(tools);

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

'''

safe_area = r'''  function installSafeAreaGuide() {
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
      const extra = document.createElement("div");
      extra.className = "playback-extra-tools";

      const button = document.createElement("button");
      button.id = "safeAreaToggle";
      button.className = "text-button safe-area-toggle";
      button.type = "button";
      button.setAttribute("aria-pressed", "false");
      button.textContent = "Safe areas";
      button.addEventListener("click", () => {
        const enabled = guides.hidden;
        guides.hidden = !enabled;
        button.setAttribute("aria-pressed", String(enabled));
        button.textContent = enabled ? "Hide safe areas" : "Safe areas";
      });

      const shortcuts = document.createElement("details");
      shortcuts.className = "shortcut-disclosure";
      shortcuts.innerHTML = `
        <summary>Timing shortcuts</summary>
        <div class="timing-shortcut-grid">
          <span><span><kbd>Shift</kbd> + <kbd>←/→</kbd></span><small>Nudge 0.1s</small></span>
          <span><span><kbd>Option/Alt</kbd> + <kbd>←/→</kbd></span><small>Nudge 0.5s</small></span>
          <span><span><kbd>[</kbd> / <kbd>]</kbd></span><small>Set cue start / end</small></span>
          <span><span><kbd>P</kbd> / <kbd>N</kbd></span><small>Previous / next caption</small></span>
        </div>`;
      extra.append(button, shortcuts);
      help.append(extra);
    }
  }

'''

patterns = [
    (r"  function installProjectControls\(\) \{.*?\n  \}\n\n  function installCaptionTools", project_controls + "  function installCaptionTools"),
    (r"  function installCaptionTools\(\) \{.*?\n  \}\n\n  function installSafeAreaGuide", caption_tools + "  function installSafeAreaGuide"),
    (r"  function installSafeAreaGuide\(\) \{.*?\n  \}\n\n  function installSystemReadiness", safe_area + "  function installSystemReadiness"),
]

for pattern, replacement in patterns:
    app, count = re.subn(pattern, replacement, app, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Expected exactly one app.js replacement for {pattern!r}; got {count}")

new_css = r'''/* major-iterations: productivity tools */
.project-browser-controls {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin: 0 0 1rem;
}
.project-search-cluster {
  min-width: 0;
  flex: 1 1 560px;
  display: flex;
  align-items: flex-end;
  gap: .8rem;
}
.project-browser-controls label,
.caption-productivity-tools label {
  display: grid;
  gap: .35rem;
  color: var(--muted);
  font-size: .75rem;
  font-weight: 800;
}
.project-search-field { min-width: 0; flex: 1; }
.project-browser-controls input,
.project-browser-controls select,
.caption-productivity-tools input {
  min-width: 0;
  width: 100%;
  border: 1px solid #aeb9ce;
  border-radius: 9px;
  padding: .65rem .72rem;
  color: var(--ink);
  background: var(--control);
}
.project-search-field input { min-height: 42px; }
.project-refine-controls {
  flex: 0 0 auto;
  display: flex;
  align-items: flex-end;
  gap: .55rem;
  padding: .45rem;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--paper);
}
.project-refine-controls label { min-width: 132px; }
.project-refine-controls select { min-height: 36px; padding-block: .48rem; }
.project-filter-count {
  flex: 0 0 auto;
  min-width: max-content;
  padding-bottom: .7rem;
  color: var(--muted);
  font-size: .78rem;
  white-space: nowrap;
}
.project-filter-empty { margin-top: .75rem; }

.editor-heading { gap: .75rem; padding: 1rem; }
.editor-title-row { align-items: flex-start; }
.editor-title-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: .5rem;
}
.editor-review-action {
  min-height: 36px;
  padding: .45rem .7rem;
  border-color: color-mix(in srgb, var(--blue) 36%, var(--line));
  color: var(--blue-dark);
  background: color-mix(in srgb, var(--sky) 56%, var(--control));
  font-size: .76rem;
  font-weight: 800;
  white-space: nowrap;
}
.editor-tools {
  margin: 0;
  padding: .65rem .7rem;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: color-mix(in srgb, var(--wash) 72%, var(--paper));
}
.editor-tool-group { gap: .4rem; }
.editor-tool-group + .editor-tool-group { margin-left: auto; }

.caption-productivity-tools {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--paper);
}
.caption-productivity-tools > summary {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: .65rem .75rem;
  color: var(--ink);
  background: color-mix(in srgb, var(--wash) 64%, var(--paper));
  cursor: pointer;
  list-style: none;
}
.caption-productivity-tools > summary::-webkit-details-marker { display: none; }
.caption-productivity-tools > summary::after {
  content: "+";
  flex: 0 0 auto;
  width: 1.7rem;
  height: 1.7rem;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 7px;
  color: var(--blue-dark);
  background: var(--control);
  font-weight: 900;
}
.caption-productivity-tools[open] > summary::after { content: "−"; }
.caption-productivity-tools[open] > summary { border-bottom: 1px solid var(--line); }
.caption-find-summary-copy { min-width: 0; display: grid; gap: .12rem; }
.caption-find-summary-copy strong { font-size: .82rem; }
.caption-find-summary-copy small { color: var(--muted); font-size: .72rem; font-weight: 500; line-height: 1.35; }
.caption-search-status {
  margin-left: auto;
  color: var(--muted);
  font-size: .74rem;
  text-align: right;
  white-space: nowrap;
}
.caption-find-body { display: grid; gap: .65rem; padding: .75rem; }
.caption-search-row,
.caption-replace-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: .55rem;
  align-items: end;
}
.caption-replace-row { grid-template-columns: minmax(0, 1fr) auto auto; }
.caption-productivity-tools .editor-action { min-height: 38px; height: 38px; }

.cue-row.search-match {
  background: color-mix(in srgb, var(--sky) 72%, var(--paper));
  box-shadow: inset 4px 0 var(--blue), 0 0 0 1px color-mix(in srgb, var(--blue) 28%, transparent);
}
.safe-area-guides { position: absolute; inset: 0; z-index: 5; pointer-events: none; }
.safe-area-guides > div { position: absolute; border: 1px dashed rgba(255,255,255,.78); box-shadow: 0 0 0 1px rgba(0,0,0,.4); }
.safe-area-guides span { position: absolute; top: .2rem; left: .3rem; padding: .12rem .3rem; border-radius: 4px; color: #fff; background: rgba(0,0,0,.68); font-size: .62rem; font-weight: 800; }
.safe-area-action { inset: 5%; }
.safe-area-title { inset: 10%; }
.playback-help { align-items: center; flex-wrap: wrap; gap: .45rem .85rem; }
.playback-extra-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: .45rem;
}
.safe-area-toggle,
.shortcut-disclosure > summary {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  padding: .3rem .5rem;
  border: 1px solid var(--line);
  border-radius: 7px;
  color: var(--blue-dark);
  background: var(--control);
  font-size: .72rem;
  font-weight: 800;
  white-space: nowrap;
}
.safe-area-toggle { margin: 0; }
.safe-area-toggle[aria-pressed="true"] { border-color: var(--blue); background: var(--sky); }
.shortcut-disclosure { position: relative; }
.shortcut-disclosure > summary { cursor: pointer; list-style: none; }
.shortcut-disclosure > summary::-webkit-details-marker { display: none; }
.timing-shortcut-grid {
  position: absolute;
  z-index: 8;
  top: calc(100% + .4rem);
  right: 0;
  width: min(360px, calc(100vw - 3rem));
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .4rem;
  padding: .6rem;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--paper);
  box-shadow: var(--shadow);
}
.timing-shortcut-grid > span { display: grid; gap: .18rem; padding: .45rem; border-radius: 7px; background: var(--wash); }
.timing-shortcut-grid small { color: var(--muted); font-size: .68rem; }

.system-readiness-list { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-top: .7rem; }
.system-readiness-list > div { display: flex; justify-content: space-between; gap: .75rem; padding: .65rem .7rem; border-radius: 8px; background: var(--wash); font-size: .8rem; }
.readiness-ok { color: var(--teal); font-weight: 800; }
.readiness-warning { color: var(--warning); font-weight: 800; }

@media (max-width: 1180px) {
  .project-browser-controls { align-items: stretch; flex-direction: column; }
  .project-search-cluster { flex-basis: auto; }
  .project-refine-controls { align-self: flex-start; }
  .editor-tool-group + .editor-tool-group { margin-left: 0; }
}
@media (max-width: 760px) {
  .project-search-cluster { align-items: stretch; flex-direction: column; gap: .35rem; }
  .project-filter-count { padding: 0; }
  .project-refine-controls { width: 100%; display: grid; grid-template-columns: 1fr 1fr; }
  .project-refine-controls label { min-width: 0; }
  .editor-title-row { align-items: stretch; flex-direction: column; }
  .editor-title-actions { width: 100%; justify-content: stretch; }
  .editor-title-actions > button { flex: 1 1 0; }
  .editor-tools { align-items: stretch; }
  .editor-tool-group { flex: 1 1 100%; }
  .editor-tool-group .editor-action { flex: 1 1 auto; }
  .caption-productivity-tools > summary { align-items: flex-start; flex-wrap: wrap; gap: .45rem; }
  .caption-search-status { order: 3; width: 100%; margin-left: 0; text-align: left; }
  .caption-search-row,
  .caption-replace-row { grid-template-columns: 1fr 1fr; }
  .caption-search-row label,
  .caption-replace-row label { grid-column: 1 / -1; }
  .playback-extra-tools { width: 100%; margin-left: 0; justify-content: flex-start; }
  .timing-shortcut-grid { right: auto; left: 0; grid-template-columns: 1fr; }
  .system-readiness-list { grid-template-columns: 1fr; }
}
@media (max-width: 480px) {
  .project-refine-controls { grid-template-columns: 1fr; }
  .editor-title-actions { flex-direction: column; }
  .caption-search-row,
  .caption-replace-row { grid-template-columns: 1fr; }
  .caption-search-row label,
  .caption-replace-row label { grid-column: auto; }
  .caption-productivity-tools .editor-action { width: 100%; }
}

/* major-iterations: readability and finding fixes */'''

css_pattern = r"/\* major-iterations: productivity tools \*/.*?/\* major-iterations: readability and finding fixes \*/"
css, count = re.subn(css_pattern, new_css, css, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"Expected one productivity CSS block; got {count}")

APP.write_text(app, encoding="utf-8")
CSS.write_text(css, encoding="utf-8")
