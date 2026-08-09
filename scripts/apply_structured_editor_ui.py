from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/accessible_caption_studio/web/app.js"
CSS = ROOT / "src/accessible_caption_studio/web/styles.css"


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected one {label} replacement, found {count}")
    return updated


app = APP.read_text()

project_controls = r'''  function installProjectControls() {
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

'''
app = replace_once(
    app,
    r"  function installProjectControls\(\) \{.*?\n  \}\n\n(?=  function installCaptionTools\(\))",
    project_controls,
    "project controls",
)

caption_tools = r'''  function installCaptionTools() {
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
    commandBar.setAttribute("role", "toolbar");
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

'''
app = replace_once(
    app,
    r"  function installCaptionTools\(\) \{.*?\n  \}\n\n(?=  function installSafeAreaGuide\(\))",
    caption_tools,
    "caption tools",
)

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

'''
app = replace_once(
    app,
    r"  function installSafeAreaGuide\(\) \{.*?\n  \}\n\n(?=  function installSystemReadiness\(\))",
    safe_area,
    "safe area tools",
)

APP.write_text(app)

css = CSS.read_text()
css += r'''

/* major-iterations: structured editor UI */
.project-browser-controls {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) auto;
  align-items: center;
  gap: .7rem;
  margin: -.1rem 0 .9rem;
  padding: 0;
  border: 0;
  background: transparent;
}
.project-search-field { min-width: 0; }
.project-search-field input,
.project-compact-select select {
  width: 100%;
  min-width: 0;
  min-height: 38px;
  border: 1px solid color-mix(in srgb, var(--line) 88%, #7f8ca6);
  border-radius: 9px;
  color: var(--ink);
  background: var(--paper);
  box-shadow: 0 1px 2px rgba(20, 35, 70, .04);
}
.project-search-field input {
  padding: .58rem .75rem .58rem 2.15rem;
  background-image: linear-gradient(45deg, transparent 46%, var(--muted) 47%, var(--muted) 53%, transparent 54%), linear-gradient(-45deg, transparent 46%, var(--muted) 47%, var(--muted) 53%, transparent 54%);
  background-size: 7px 7px, 7px 7px;
  background-position: .86rem 1.02rem, 1.14rem 1.02rem;
  background-repeat: no-repeat;
}
.project-browser-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: .45rem;
}
.project-compact-select { min-width: 124px; }
.project-compact-select select { padding: .5rem 1.8rem .5rem .62rem; }
.project-filter-count {
  min-width: max-content;
  padding: 0 .1rem 0 .35rem;
  color: var(--muted);
  font-size: .74rem;
  white-space: nowrap;
}
.project-filter-empty { margin-top: .7rem; }

.editor-heading {
  gap: .65rem;
  padding: .95rem 1rem .75rem;
}
.editor-title-row { align-items: center; }
.editor-title-row > div:first-child { min-width: 0; }
.editor-command-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  min-width: 0;
  padding-top: .55rem;
  border-top: 1px solid var(--soft-line);
}
.editor-command-primary,
.editor-command-secondary {
  display: flex;
  align-items: center;
  gap: .25rem;
  min-width: 0;
}
.editor-command-primary { flex: 1 1 auto; flex-wrap: wrap; }
.editor-command-secondary { flex: 0 0 auto; }
.editor-command-bar .editor-command-button,
.editor-more-trigger {
  min-height: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: .35rem .55rem;
  border: 0;
  border-radius: 7px;
  color: var(--muted);
  background: transparent;
  box-shadow: none;
  font-size: .74rem;
  font-weight: 760;
  line-height: 1;
  white-space: nowrap;
}
.editor-command-bar .editor-command-button:hover,
.editor-more-trigger:hover { color: var(--ink); background: var(--wash); }
.editor-command-bar .editor-command-button[aria-pressed="true"],
.editor-command-bar .follow-playback[aria-pressed="true"] {
  color: var(--blue-dark);
  background: var(--sky);
}
.editor-command-bar .editor-review-action {
  color: var(--blue-dark);
  background: color-mix(in srgb, var(--sky) 62%, transparent);
}
.editor-command-bar .editor-review-action:disabled {
  color: var(--muted);
  background: transparent;
}
.editor-command-bar #addCueButton {
  min-height: 34px;
  height: 34px;
  margin-left: .2rem;
  padding: .42rem .7rem;
  box-shadow: none;
}
.editor-more-menu { position: relative; }
.editor-more-trigger { cursor: pointer; list-style: none; }
.editor-more-trigger::-webkit-details-marker { display: none; }
.editor-more-trigger::after { content: "⌄"; margin-left: .35rem; color: var(--muted); font-size: .7rem; }
.editor-more-menu[open] .editor-more-trigger { color: var(--ink); background: var(--wash); }
.editor-more-popover {
  position: absolute;
  z-index: 20;
  top: calc(100% + .4rem);
  right: 0;
  width: 210px;
  display: grid;
  gap: .18rem;
  padding: .35rem;
  border: 1px solid color-mix(in srgb, var(--line) 86%, #7f8ca6);
  border-radius: 10px;
  background: var(--paper);
  box-shadow: 0 12px 30px rgba(20, 35, 70, .16), 0 2px 8px rgba(20, 35, 70, .08);
  transform-origin: top right;
  transition: opacity 150ms cubic-bezier(.23,1,.32,1), transform 150ms cubic-bezier(.23,1,.32,1);
}
.editor-more-menu[open] .editor-more-popover {
  @starting-style { opacity: 0; transform: scale(.97) translateY(-3px); }
}
.editor-more-popover .editor-more-action {
  width: 100%;
  min-height: 36px;
  height: auto;
  justify-content: flex-start;
  padding: .55rem .6rem;
  border: 0;
  border-radius: 7px;
  color: var(--ink);
  background: transparent;
  box-shadow: none;
  text-align: left;
  font-size: .75rem;
}
.editor-more-popover .editor-more-action:hover { background: var(--wash); }

.caption-productivity-tools.caption-find-panel {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: .5rem;
  overflow: visible;
  padding-top: .05rem;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.caption-productivity-tools.caption-find-panel[hidden] { display: none; }
.caption-find-search,
.caption-find-replace {
  min-width: 0;
  display: grid;
  align-items: center;
  gap: .4rem;
}
.caption-find-search { grid-template-columns: minmax(0, 1fr) auto auto; }
.caption-find-replace { grid-template-columns: minmax(0, 1fr) auto auto; }
.caption-find-panel label { min-width: 0; }
.caption-find-panel input {
  width: 100%;
  min-width: 0;
  min-height: 36px;
  padding: .5rem .62rem;
  border: 1px solid color-mix(in srgb, var(--line) 88%, #7f8ca6);
  border-radius: 8px;
  color: var(--ink);
  background: var(--control);
}
.caption-find-panel .editor-action {
  min-height: 34px;
  height: 34px;
  padding: .4rem .55rem;
  box-shadow: none;
  font-size: .72rem;
}
.caption-search-status {
  margin: 0;
  min-width: max-content;
  color: var(--muted);
  font-size: .7rem;
  white-space: nowrap;
}

.cue-row.search-match {
  background: color-mix(in srgb, var(--sky) 68%, var(--paper));
  box-shadow: inset 3px 0 var(--blue);
}

.playback-help {
  align-items: center;
  gap: .45rem .8rem;
  flex-wrap: wrap;
}
.preview-utility-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: .15rem;
}
.preview-utility-tools .safe-area-toggle,
.preview-utility-tools .shortcut-disclosure > summary {
  min-height: 28px;
  padding: .28rem .42rem;
  border: 0;
  border-radius: 6px;
  color: var(--muted);
  background: transparent;
  font-size: .7rem;
  font-weight: 760;
  white-space: nowrap;
}
.preview-utility-tools .safe-area-toggle:hover,
.preview-utility-tools .shortcut-disclosure > summary:hover { color: var(--ink); background: var(--wash); }
.preview-utility-tools .safe-area-toggle[aria-pressed="true"] { color: var(--blue-dark); background: var(--sky); }
.shortcut-disclosure { position: relative; }
.shortcut-disclosure > summary { cursor: pointer; list-style: none; }
.shortcut-disclosure > summary::-webkit-details-marker { display: none; }
.timing-shortcut-grid {
  top: calc(100% + .35rem);
  right: 0;
  width: min(330px, calc(100vw - 2rem));
  grid-template-columns: 1fr 1fr;
  gap: .2rem;
  padding: .35rem;
  border-radius: 10px;
  box-shadow: 0 12px 30px rgba(20, 35, 70, .16), 0 2px 8px rgba(20, 35, 70, .08);
  transform-origin: top right;
  transition: opacity 150ms cubic-bezier(.23,1,.32,1), transform 150ms cubic-bezier(.23,1,.32,1);
}
.shortcut-disclosure[open] .timing-shortcut-grid {
  @starting-style { opacity: 0; transform: scale(.97) translateY(-3px); }
}
.timing-shortcut-grid > span { padding: .42rem; background: transparent; }
.timing-shortcut-grid > span:hover { background: var(--wash); }

@media (max-width: 900px) {
  .project-browser-controls { grid-template-columns: 1fr; align-items: stretch; }
  .project-browser-actions { justify-content: flex-start; }
  .project-filter-count { margin-left: auto; }
  .caption-productivity-tools.caption-find-panel { grid-template-columns: 1fr; }
}

@media (max-width: 700px) {
  .editor-command-bar { align-items: stretch; flex-direction: column; }
  .editor-command-primary,
  .editor-command-secondary { width: 100%; }
  .editor-command-secondary { justify-content: space-between; }
  .editor-command-bar #addCueButton { margin-left: auto; }
  .editor-more-popover { left: 0; right: auto; transform-origin: top left; }
}

@media (max-width: 560px) {
  .project-browser-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .project-compact-select { min-width: 0; }
  .project-filter-count { grid-column: 1 / -1; margin: 0; padding: .1rem 0 0; }
  .editor-command-primary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .editor-command-bar .editor-command-button { width: 100%; }
  .caption-find-search,
  .caption-find-replace { grid-template-columns: minmax(0, 1fr) auto; }
  .caption-find-search .caption-search-status { grid-column: 1 / -1; grid-row: 2; }
  #captionReplaceAll { grid-column: 1 / -1; width: 100%; }
  .preview-utility-tools { width: 100%; margin-left: 0; justify-content: flex-end; }
  .timing-shortcut-grid { grid-template-columns: 1fr; }
}

@media (hover: hover) and (pointer: fine) {
  .editor-command-bar button,
  .editor-more-trigger,
  .preview-utility-tools button,
  .preview-utility-tools summary {
    transition: background-color 140ms ease, color 140ms ease;
  }
}
'''
CSS.write_text(css)
