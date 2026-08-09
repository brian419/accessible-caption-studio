from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "src/accessible_caption_studio/webapp.py"
EXPORTS = ROOT / "src/accessible_caption_studio/exports.py"
APP = ROOT / "src/accessible_caption_studio/web/app.js"
CSS = ROOT / "src/accessible_caption_studio/web/styles.css"
BROWSER_TEST = ROOT / "tests/browser/test_browser_ui.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} target, found {count}")
    return text.replace(old, new, 1)


webapp = WEBAPP.read_text(encoding="utf-8")
webapp = replace_once(
    webapp,
    "from fastapi.responses import FileResponse, HTMLResponse, Response\n",
    "from fastapi.responses import FileResponse, HTMLResponse, Response\nfrom starlette.background import BackgroundTask\n",
    "BackgroundTask import",
)
webapp = replace_once(
    webapp,
    "from .visual import analyze_active_speakers\n",
    "from .visual import analyze_active_speakers\nfrom .waveform import build_waveform_envelope\n",
    "waveform import",
)
webapp = replace_once(
    webapp,
    '''class OverlapRequest(BaseModel):\n    start: float = Field(ge=0)\n    end: float = Field(gt=0)\n''',
    '''class FavoriteRequest(BaseModel):\n    favorite: bool\n\n\nclass OverlapRequest(BaseModel):\n    start: float = Field(ge=0)\n    end: float = Field(gt=0)\n''',
    "favorite request model",
)

restore_route = '''    @app.post("/api/projects/restore", status_code=201)\n    async def restore_project_backup(\n        backup: Annotated[UploadFile, File()],\n    ) -> Project:\n        filename = safe_filename(backup.filename or "project.acstudio.zip", "project.acstudio.zip")\n        upload_path = store.temp_dir / f"restore-upload-{uuid4().hex}-{filename}"\n        try:\n            await _save_upload(backup, upload_path)\n            return store.restore_archive(upload_path)\n        except ValueError as exc:\n            raise HTTPException(status_code=400, detail=str(exc)) from exc\n        finally:\n            upload_path.unlink(missing_ok=True)\n\n'''
webapp = replace_once(
    webapp,
    '''    @app.post("/api/projects/upload", status_code=202)\n''',
    restore_route + '''    @app.post("/api/projects/upload", status_code=202)\n''',
    "restore route",
)

project_routes = '''    @app.post("/api/projects/{project_id}/favorite")\n    def favorite_project(project_id: str, request: FavoriteRequest) -> Project:\n        project = _get_project(store, project_id)\n        project.is_favorite = request.favorite\n        return store.save(project, touch=False)\n\n    @app.get("/api/projects/{project_id}/backup")\n    def backup_project(project_id: str) -> FileResponse:\n        project = _get_project(store, project_id)\n        archive_path = store.create_archive(project_id)\n        filename = f"{safe_filename(project.name, 'Accessible Caption Studio project')} - backup.acstudio.zip"\n        return FileResponse(\n            archive_path,\n            media_type="application/zip",\n            filename=filename,\n            background=BackgroundTask(archive_path.unlink, missing_ok=True),\n        )\n\n    @app.get("/api/projects/{project_id}/revisions")\n    def project_revisions(project_id: str) -> list[dict[str, object]]:\n        _get_project(store, project_id)\n        return store.list_revisions(project_id)\n\n    @app.post("/api/projects/{project_id}/revisions/{revision_id}/restore")\n    def restore_project_revision(project_id: str, revision_id: str) -> Project:\n        _get_project(store, project_id)\n        try:\n            return store.restore_revision(project_id, revision_id)\n        except KeyError as exc:\n            raise HTTPException(status_code=404, detail="Restore point not found") from exc\n        except ValueError as exc:\n            raise HTTPException(status_code=400, detail=str(exc)) from exc\n\n    @app.get("/api/projects/{project_id}/waveform")\n    def project_waveform(project_id: str) -> dict[str, Any]:\n        project = _get_project(store, project_id)\n        if not project.media:\n            raise HTTPException(status_code=400, detail="Project media is not ready yet")\n        project_dir = store.project_dir(project_id)\n        audio_path = project_dir / "analysis.wav"\n        if not audio_path.is_file():\n            source = project_dir / project.media.stored_name\n            extract_audio(source, audio_path)\n        try:\n            return build_waveform_envelope(audio_path, project_dir / "waveform.json")\n        except (OSError, ValueError) as exc:\n            raise HTTPException(status_code=400, detail="The waveform could not be prepared for this project") from exc\n\n'''
webapp = replace_once(
    webapp,
    '''    @app.get("/api/projects/{project_id}")\n    def get_project(project_id: str) -> Project:\n        return _get_project(store, project_id)\n\n''',
    project_routes
    + '''    @app.get("/api/projects/{project_id}")\n    def get_project(project_id: str) -> Project:\n        return _get_project(store, project_id)\n\n''',
    "project utility routes",
)

old_update = '''    @app.patch("/api/projects/{project_id}")\n    def update_project(project_id: str, request: ProjectUpdate) -> Project:\n        project = _get_project(store, project_id)\n        if request.name is not None:\n            project.name = request.name\n        if request.cues is not None:\n            project.cues = request.cues\n            project.findings = validate_cues(\n                project.cues, project.media.duration if project.media else None\n            )\n        if request.speaker_names is not None:\n            project.speaker_names = request.speaker_names\n        if request.transcription_quality is not None:\n            project.transcription_quality = request.transcription_quality\n        if request.caption_style is not None:\n            project.caption_style = request.caption_style\n        return store.save(project)\n'''
new_update = '''    @app.patch("/api/projects/{project_id}")\n    def update_project(project_id: str, request: ProjectUpdate) -> Project:\n        project = _get_project(store, project_id)\n        changed = (\n            (request.name is not None and request.name != project.name)\n            or (request.cues is not None and request.cues != project.cues)\n            or (request.speaker_names is not None and request.speaker_names != project.speaker_names)\n            or (\n                request.transcription_quality is not None\n                and request.transcription_quality != project.transcription_quality\n            )\n            or (request.caption_style is not None and request.caption_style != project.caption_style)\n        )\n        if changed:\n            store.create_revision(project)\n        if request.name is not None:\n            project.name = request.name\n        if request.cues is not None:\n            project.cues = request.cues\n            project.findings = validate_cues(\n                project.cues, project.media.duration if project.media else None\n            )\n        if request.speaker_names is not None:\n            project.speaker_names = request.speaker_names\n        if request.transcription_quality is not None:\n            project.transcription_quality = request.transcription_quality\n        if request.caption_style is not None:\n            project.caption_style = request.caption_style\n        return store.save(project)\n'''
webapp = replace_once(webapp, old_update, new_update, "revision-aware project update")
WEBAPP.write_text(webapp, encoding="utf-8")

exports = EXPORTS.read_text(encoding="utf-8")
old_render_items = '''def _render_items(project: Project) -> list[tuple[float, float, str]]:\n    """Match the browser preview by joining intentionally grouped overlapping cues."""\n    ordered = sorted(project.cues, key=lambda cue: (cue.start, cue.end, cue.id))\n    grouped: dict[str, list[CaptionCue]] = {}\n    for cue in ordered:\n        if cue.overlap_group_id:\n            grouped.setdefault(cue.overlap_group_id, []).append(cue)\n\n    rendered: list[tuple[float, float, str]] = []\n    seen_groups: set[str] = set()\n    for cue in ordered:\n        group_id = cue.overlap_group_id\n        if group_id:\n            if group_id in seen_groups:\n                continue\n            seen_groups.add(group_id)\n            members = grouped[group_id]\n            rendered.append(\n                (\n                    min(member.start for member in members),\n                    max(member.end for member in members),\n                    "\\n".join(_caption_text(project, member) for member in members),\n                )\n            )\n        else:\n            rendered.append((cue.start, cue.end, _caption_text(project, cue)))\n    return rendered\n'''
new_render_items = '''def _style_for_cue(project: Project, cue: CaptionCue) -> CaptionStyle:\n    style = project.caption_style.model_copy(deep=True)\n    if cue.position_override is not None:\n        style.position = cue.position_override\n    if cue.alignment_override is not None:\n        style.alignment = cue.alignment_override\n    if cue.vertical_margin_percent_override is not None:\n        style.vertical_margin_percent = cue.vertical_margin_percent_override\n    return style\n\n\ndef _render_items(project: Project) -> list[tuple[float, float, str, CaptionStyle]]:\n    """Match the browser preview by joining intentionally grouped overlapping cues."""\n    ordered = sorted(project.cues, key=lambda cue: (cue.start, cue.end, cue.id))\n    grouped: dict[str, list[CaptionCue]] = {}\n    for cue in ordered:\n        if cue.overlap_group_id:\n            grouped.setdefault(cue.overlap_group_id, []).append(cue)\n\n    rendered: list[tuple[float, float, str, CaptionStyle]] = []\n    seen_groups: set[str] = set()\n    for cue in ordered:\n        group_id = cue.overlap_group_id\n        if group_id:\n            if group_id in seen_groups:\n                continue\n            seen_groups.add(group_id)\n            members = grouped[group_id]\n            rendered.append(\n                (\n                    min(member.start for member in members),\n                    max(member.end for member in members),\n                    "\\n".join(_caption_text(project, member) for member in members),\n                    _style_for_cue(project, members[0]),\n                )\n            )\n        else:\n            rendered.append((cue.start, cue.end, _caption_text(project, cue), _style_for_cue(project, cue)))\n    return rendered\n'''
exports = replace_once(exports, old_render_items, new_render_items, "per-cue render items")
exports = replace_once(
    exports,
    '''    entries: list[tuple[Path, float, float, int, int]] = []\n    for item_index, (start, end, text) in enumerate(items):\n        lines = _wrap_export_text(text, project.caption_style, video_width, video_height)\n        for line_index, line in enumerate(lines):\n            text_path = temporary_dir / f"caption-{item_index:05d}-{line_index:02d}.txt"\n            text_path.write_text(line, encoding="utf-8")\n            entries.append((text_path, start, end, line_index, len(lines)))\n\n    current = "[normalized]"\n    filters: list[str] = [f"[0:v]{normalization}[normalized]"]\n    for index, (text_path, start, end, line_index, total_lines) in enumerate(entries):\n        output = "[captioned]" if index == len(entries) - 1 else f"[caption{index}]"\n        drawtext = _drawtext_filter(\n            project.caption_style,\n            text_path,\n            start,\n            end,\n            video_height,\n            line_index,\n            total_lines,\n        )\n''',
    '''    entries: list[tuple[Path, float, float, int, int, CaptionStyle]] = []\n    for item_index, (start, end, text, item_style) in enumerate(items):\n        lines = _wrap_export_text(text, item_style, video_width, video_height)\n        for line_index, line in enumerate(lines):\n            text_path = temporary_dir / f"caption-{item_index:05d}-{line_index:02d}.txt"\n            text_path.write_text(line, encoding="utf-8")\n            entries.append((text_path, start, end, line_index, len(lines), item_style))\n\n    current = "[normalized]"\n    filters: list[str] = [f"[0:v]{normalization}[normalized]"]\n    for index, (text_path, start, end, line_index, total_lines, item_style) in enumerate(entries):\n        output = "[captioned]" if index == len(entries) - 1 else f"[caption{index}]"\n        drawtext = _drawtext_filter(\n            item_style,\n            text_path,\n            start,\n            end,\n            video_height,\n            line_index,\n            total_lines,\n        )\n''',
    "per-cue export styles",
)
EXPORTS.write_text(exports, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
app += r'''

// major-iterations Batch 2: favorites, backups, history, waveform timing, per-cue placement
(() => {
  const batch2 = {
    waveform: null,
    waveformProjectId: null,
    waveformCueId: null,
    waveformDrag: null,
    placementCueId: null,
  };

  const previousRenderProjectsBatch2 = renderProjects;
  renderProjects = function renderProjectsWithFavorites() {
    previousRenderProjectsBatch2();
    document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {
      const project = state.projects.find((item) => item.id === card.dataset.projectId);
      if (!project || card.querySelector(".project-favorite")) return;
      card.classList.toggle("is-favorite", Boolean(project.is_favorite));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "project-favorite";
      button.setAttribute("aria-pressed", String(Boolean(project.is_favorite)));
      button.setAttribute(
        "aria-label",
        `${project.is_favorite ? "Remove" : "Add"} ${project.name} ${project.is_favorite ? "from" : "to"} favorites`,
      );
      button.title = project.is_favorite ? "Remove from favorites" : "Add to favorites";
      button.textContent = project.is_favorite ? "★" : "☆";
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const desired = !Boolean(project.is_favorite);
        button.disabled = true;
        try {
          const saved = await api(`/api/projects/${project.id}/favorite`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ favorite: desired }),
          });
          const index = state.projects.findIndex((item) => item.id === project.id);
          if (index >= 0) state.projects[index] = saved;
          renderProjects();
        } catch (error) {
          toast(error.message, "error");
          button.disabled = false;
        }
      });
      card.append(button);
    });
  };

  const previousRenderCuesBatch2 = renderCues;
  renderCues = function renderCuesWithPlacementAndWaveformSelection() {
    previousRenderCuesBatch2();
    state.project?.cues.forEach((cue) => {
      const row = document.querySelector(`#cue-${CSS.escape(cue.id)}`);
      if (!row) return;
      const actions = row.querySelector(".cue-actions");
      if (actions && !actions.querySelector(".cue-placement-button")) {
        const button = actionButton("Position", () => openCuePlacement(cue.id));
        button.classList.add("cue-placement-button");
        const customized = Boolean(
          cue.position_override || cue.alignment_override || cue.vertical_margin_percent_override != null
        );
        button.classList.toggle("is-customized", customized);
        button.textContent = customized ? "Position •" : "Position";
        actions.append(button);
      }
      row.addEventListener("focusin", () => selectWaveformCue(cue.id));
      row.addEventListener("click", () => selectWaveformCue(cue.id));
    });
    drawWaveform();
  };

  const previousRenderProjectBatch2 = renderProject;
  renderProject = function renderProjectWithBatch2() {
    const incomingId = state.project?.id || null;
    if (batch2.waveformProjectId !== incomingId) {
      batch2.waveform = null;
      batch2.waveformProjectId = incomingId;
      batch2.waveformCueId = null;
    }
    previousRenderProjectBatch2();
    updateBatch2Controls();
  };

  const previousSyncPlaybackBatch2 = syncPlayback;
  syncPlayback = function syncPlaybackWithCuePlacement(...args) {
    previousSyncPlaybackBatch2(...args);
    const cue = activePlacementCue();
    applyCuePlacement(cue);
    if (!batch2.waveformCueId && cue) batch2.waveformCueId = cue.id;
    drawWaveform();
  };

  function activePlacementCue() {
    if (!state.project?.cues?.length) return null;
    const time = activePlayer()?.currentTime ?? 0;
    return state.project.cues.find((cue) => time >= Number(cue.start) && time <= Number(cue.end)) || null;
  }

  function applyCuePlacement(cue) {
    if (!state.project) return;
    const base = normalizeCaptionStyle(state.project.caption_style);
    const position = cue?.position_override || base.position;
    const alignment = cue?.alignment_override || base.alignment;
    const verticalMarginPercent = cue?.vertical_margin_percent_override ?? base.vertical_margin_percent;
    const overlay = $("#captionOverlay");
    const stage = $("#mediaStage");
    const stageBox = stage.getBoundingClientRect();
    const videoBox = mediaPlayer.hidden ? stageBox : mediaPlayer.getBoundingClientRect();
    const videoHeight = Math.max(videoBox.height, 1);
    const videoWidth = Math.max(videoBox.width, 1);
    const videoTop = Math.max(0, videoBox.top - stageBox.top);
    const videoLeft = Math.max(0, videoBox.left - stageBox.left);
    const horizontalMargin = videoWidth * 0.06;
    const verticalMargin = videoHeight * verticalMarginPercent / 100;
    const transforms = [];

    overlay.style.textAlign = alignment;
    overlay.style.alignItems = ({ left: "flex-start", center: "center", right: "flex-end" })[alignment];
    overlay.style.top = "auto";
    overlay.style.bottom = "auto";
    overlay.style.left = "auto";
    overlay.style.right = "auto";
    if (alignment === "left") overlay.style.left = `${videoLeft + horizontalMargin}px`;
    else if (alignment === "right") {
      overlay.style.right = `${Math.max(0, stageBox.width - videoLeft - videoWidth + horizontalMargin)}px`;
    } else {
      overlay.style.left = `${videoLeft + videoWidth / 2}px`;
      transforms.push("translateX(-50%)");
    }
    if (position === "top") overlay.style.top = `${videoTop + verticalMargin}px`;
    else if (position === "middle") {
      overlay.style.top = `${videoTop + videoHeight / 2}px`;
      transforms.push("translateY(-50%)");
    } else {
      overlay.style.bottom = `${Math.max(0, stageBox.height - videoTop - videoHeight + verticalMargin)}px`;
    }
    overlay.style.transform = transforms.length ? transforms.join(" ") : "none";
  }

  function installBatch2ProjectControls() {
    if ($("#restoreProjectBackup")) return;
    const recentActions = document.querySelector(".recent-actions");
    if (recentActions) {
      const restore = document.createElement("button");
      restore.id = "restoreProjectBackup";
      restore.className = "text-button";
      restore.type = "button";
      restore.textContent = "Restore backup";
      const input = document.createElement("input");
      input.id = "restoreProjectBackupInput";
      input.type = "file";
      input.accept = ".zip,.acstudio.zip,application/zip";
      input.hidden = true;
      restore.addEventListener("click", () => input.click());
      input.addEventListener("change", restoreProjectBackup);
      recentActions.insertBefore(restore, $("#refreshProjects"));
      recentActions.append(input);
    }

    const workspaceActions = document.querySelector(".workspace-actions");
    if (workspaceActions && !$("#backupProjectButton")) {
      const backup = document.createElement("button");
      backup.id = "backupProjectButton";
      backup.className = "text-button workspace-utility-action";
      backup.type = "button";
      backup.textContent = "Backup";
      backup.addEventListener("click", downloadProjectBackup);
      workspaceActions.insertBefore(backup, $("#exportButton"));
    }
  }

  async function restoreProjectBackup(event) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    const button = $("#restoreProjectBackup");
    button.disabled = true;
    button.textContent = "Restoring…";
    try {
      const form = new FormData();
      form.append("backup", file, file.name);
      const restored = await api("/api/projects/restore", { method: "POST", body: form });
      await loadProjects();
      toast(`Restored “${restored.name}”.`);
      await openProject(restored.id);
    } catch (error) {
      toast(error.message, "error");
    } finally {
      input.value = "";
      button.disabled = false;
      button.textContent = "Restore backup";
    }
  }

  function downloadProjectBackup() {
    if (!state.project) return;
    const link = document.createElement("a");
    link.href = `/api/projects/${state.project.id}/backup`;
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
  }

  function installBatch2EditorTools() {
    const primary = document.querySelector(".editor-command-primary");
    if (primary && !$("#waveformToggle")) {
      const button = document.createElement("button");
      button.id = "waveformToggle";
      button.className = "secondary editor-action editor-command-button";
      button.type = "button";
      button.textContent = "Waveform";
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-controls", "waveformTimingPanel");
      button.addEventListener("click", toggleWaveformPanel);
      primary.append(button);
    }

    const more = document.querySelector(".editor-more-popover");
    if (more && !$("#revisionHistoryButton")) {
      const history = document.createElement("button");
      history.id = "revisionHistoryButton";
      history.className = "secondary editor-action editor-more-action";
      history.type = "button";
      history.textContent = "Version history";
      history.addEventListener("click", openRevisionHistory);
      more.append(history);
    }

    const heading = document.querySelector(".editor-heading");
    if (heading && !$("#waveformTimingPanel")) {
      const panel = document.createElement("section");
      panel.id = "waveformTimingPanel";
      panel.className = "waveform-timing-panel";
      panel.hidden = true;
      panel.setAttribute("aria-labelledby", "waveformTimingTitle");
      panel.innerHTML = `
        <div class="waveform-heading">
          <div><strong id="waveformTimingTitle">Waveform timing</strong><span id="waveformStatus">Select a caption to adjust its timing.</span></div>
          <span class="waveform-help">Drag the start/end handles. Exact In/Out fields remain available in each caption row.</span>
        </div>
        <div class="waveform-canvas-wrap">
          <canvas id="waveformCanvas" tabindex="0" role="img" aria-label="Audio waveform timing editor"></canvas>
        </div>`;
      heading.append(panel);
      const canvas = panel.querySelector("#waveformCanvas");
      canvas.addEventListener("pointerdown", waveformPointerDown);
      canvas.addEventListener("pointermove", waveformPointerMove);
      canvas.addEventListener("pointerup", waveformPointerUp);
      canvas.addEventListener("pointercancel", waveformPointerUp);
      if (window.ResizeObserver) new ResizeObserver(drawWaveform).observe(panel.querySelector(".waveform-canvas-wrap"));
    }
  }

  async function toggleWaveformPanel() {
    const panel = $("#waveformTimingPanel");
    const button = $("#waveformToggle");
    const opening = panel.hidden;
    panel.hidden = !opening;
    button.setAttribute("aria-expanded", String(opening));
    button.setAttribute("aria-pressed", String(opening));
    if (!opening) return;
    if (!batch2.waveform || batch2.waveformProjectId !== state.project?.id) {
      $("#waveformStatus").textContent = "Preparing waveform…";
      try {
        batch2.waveform = await api(`/api/projects/${state.project.id}/waveform`);
        batch2.waveformProjectId = state.project.id;
      } catch (error) {
        $("#waveformStatus").textContent = error.message;
        return;
      }
    }
    if (!batch2.waveformCueId) {
      batch2.waveformCueId = activePlacementCue()?.id || state.project?.cues?.[0]?.id || null;
    }
    drawWaveform();
  }

  function selectWaveformCue(cueId) {
    if (!state.project?.cues.some((cue) => cue.id === cueId)) return;
    batch2.waveformCueId = cueId;
    drawWaveform();
  }

  function selectedWaveformCue() {
    return state.project?.cues.find((cue) => cue.id === batch2.waveformCueId) || null;
  }

  function waveformWindow(cue) {
    const duration = Math.max(Number(state.project?.media?.duration || batch2.waveform?.duration || 0), 0.001);
    if (!cue) return { start: 0, end: Math.min(duration, 12) };
    const cueDuration = Math.max(0.05, Number(cue.end) - Number(cue.start));
    const windowLength = Math.min(duration, Math.max(10, cueDuration + 8));
    let start = Math.max(0, ((Number(cue.start) + Number(cue.end)) / 2) - windowLength / 2);
    let end = Math.min(duration, start + windowLength);
    start = Math.max(0, end - windowLength);
    return { start, end };
  }

  function waveformGeometry() {
    const canvas = $("#waveformCanvas");
    const cue = selectedWaveformCue();
    if (!canvas || !cue || !batch2.waveform?.samples?.length) return null;
    const rect = canvas.getBoundingClientRect();
    const windowRange = waveformWindow(cue);
    const span = Math.max(0.001, windowRange.end - windowRange.start);
    const xForTime = (time) => ((Number(time) - windowRange.start) / span) * rect.width;
    const timeForX = (x) => windowRange.start + (Math.max(0, Math.min(rect.width, x)) / Math.max(rect.width, 1)) * span;
    return { canvas, cue, rect, windowRange, span, xForTime, timeForX };
  }

  function drawWaveform() {
    const panel = $("#waveformTimingPanel");
    const canvas = $("#waveformCanvas");
    if (!panel || panel.hidden || !canvas) return;
    const cue = selectedWaveformCue();
    const status = $("#waveformStatus");
    if (!batch2.waveform?.samples?.length) {
      if (status && status.textContent !== "Preparing waveform…") status.textContent = "Open Waveform to prepare the audio view.";
      return;
    }
    if (!cue) {
      status.textContent = "Select a caption to adjust its timing.";
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);

    const computed = getComputedStyle(document.documentElement);
    const ink = computed.getPropertyValue("--ink").trim() || "#172033";
    const muted = computed.getPropertyValue("--muted").trim() || "#69758f";
    const blue = computed.getPropertyValue("--blue").trim() || "#2563eb";
    const sky = computed.getPropertyValue("--sky").trim() || "#eaf2ff";
    const range = waveformWindow(cue);
    const duration = Math.max(Number(batch2.waveform.duration || state.project.media?.duration || 0), 0.001);
    const samples = batch2.waveform.samples;
    const startIndex = Math.max(0, Math.floor((range.start / duration) * samples.length));
    const endIndex = Math.min(samples.length, Math.ceil((range.end / duration) * samples.length));
    const visible = samples.slice(startIndex, Math.max(startIndex + 1, endIndex));
    const center = height / 2;

    context.strokeStyle = muted;
    context.globalAlpha = 0.72;
    context.lineWidth = 1;
    context.beginPath();
    visible.forEach((amplitude, index) => {
      const x = visible.length <= 1 ? 0 : (index / (visible.length - 1)) * width;
      const half = Math.max(1, Number(amplitude) * (height * 0.4));
      context.moveTo(x, center - half);
      context.lineTo(x, center + half);
    });
    context.stroke();
    context.globalAlpha = 1;

    const span = Math.max(0.001, range.end - range.start);
    const xForTime = (time) => ((Number(time) - range.start) / span) * width;
    const startX = xForTime(cue.start);
    const endX = xForTime(cue.end);
    context.fillStyle = sky;
    context.globalAlpha = 0.55;
    context.fillRect(startX, 0, Math.max(2, endX - startX), height);
    context.globalAlpha = 1;

    context.strokeStyle = blue;
    context.lineWidth = 2;
    [startX, endX].forEach((x) => {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
      context.fillStyle = blue;
      context.fillRect(x - 4, 0, 8, 12);
    });

    const playhead = activePlayer()?.currentTime ?? 0;
    if (playhead >= range.start && playhead <= range.end) {
      context.strokeStyle = ink;
      context.lineWidth = 1;
      context.beginPath();
      const playheadX = xForTime(playhead);
      context.moveTo(playheadX, 0);
      context.lineTo(playheadX, height);
      context.stroke();
    }
    status.textContent = `${Number(cue.start).toFixed(3)}s – ${Number(cue.end).toFixed(3)}s · ${range.start.toFixed(1)}–${range.end.toFixed(1)}s window`;
  }

  function waveformPointerDown(event) {
    const geometry = waveformGeometry();
    if (!geometry) return;
    const x = event.clientX - geometry.rect.left;
    const startX = geometry.xForTime(geometry.cue.start);
    const endX = geometry.xForTime(geometry.cue.end);
    const startDistance = Math.abs(x - startX);
    const endDistance = Math.abs(x - endX);
    if (Math.min(startDistance, endDistance) <= 14) {
      remember();
      batch2.waveformDrag = startDistance <= endDistance ? "start" : "end";
      geometry.canvas.setPointerCapture(event.pointerId);
      event.preventDefault();
      return;
    }
    const time = geometry.timeForX(x);
    const player = activePlayer();
    if (player?.src) player.currentTime = time;
    drawWaveform();
  }

  function waveformPointerMove(event) {
    if (!batch2.waveformDrag) return;
    const geometry = waveformGeometry();
    if (!geometry) return;
    const time = geometry.timeForX(event.clientX - geometry.rect.left);
    if (batch2.waveformDrag === "start") {
      geometry.cue.start = Math.max(0, Math.min(time, Number(geometry.cue.end) - 0.05));
    } else {
      const duration = Number(state.project?.media?.duration || Infinity);
      geometry.cue.end = Math.min(duration, Math.max(time, Number(geometry.cue.start) + 0.05));
    }
    geometry.cue.source = "manual";
    drawWaveform();
  }

  function waveformPointerUp(event) {
    if (!batch2.waveformDrag) return;
    const canvas = $("#waveformCanvas");
    if (canvas?.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    batch2.waveformDrag = null;
    renderCues();
    scheduleSave();
  }

  function installPlacementDialog() {
    if ($("#cuePlacementDialog")) return;
    const dialog = document.createElement("dialog");
    dialog.id = "cuePlacementDialog";
    dialog.className = "cue-placement-dialog";
    dialog.setAttribute("aria-labelledby", "cuePlacementTitle");
    dialog.innerHTML = `
      <form id="cuePlacementForm" class="dialog-card cue-placement-card">
        <div class="dialog-heading"><div><p class="eyebrow">Selected caption</p><h2 id="cuePlacementTitle">Caption position</h2></div><button id="closeCuePlacement" class="icon-button" type="button" aria-label="Close caption position">×</button></div>
        <p class="field-note">Override placement only for this caption. Choosing Project default keeps the global caption appearance setting.</p>
        <label for="cuePositionOverride"><strong>Vertical position</strong><select id="cuePositionOverride"><option value="">Project default</option><option value="top">Top</option><option value="middle">Middle</option><option value="bottom">Bottom</option></select></label>
        <label for="cueAlignmentOverride"><strong>Horizontal alignment</strong><select id="cueAlignmentOverride"><option value="">Project default</option><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label>
        <label for="cueMarginOverride"><strong>Edge distance</strong><span class="field-note">Leave blank to use the project default.</span><input id="cueMarginOverride" type="number" min="2" max="25" step="1" placeholder="Project default"></label>
        <div class="button-row dialog-actions"><button id="resetCuePlacement" class="text-button" type="button">Use project default</button><span class="dialog-action-spacer"></span><button id="cancelCuePlacement" class="secondary" type="button">Cancel</button><button class="primary" type="submit">Apply position</button></div>
      </form>`;
    document.body.append(dialog);
    $("#closeCuePlacement").addEventListener("click", () => dialog.close());
    $("#cancelCuePlacement").addEventListener("click", () => dialog.close());
    $("#resetCuePlacement").addEventListener("click", () => {
      $("#cuePositionOverride").value = "";
      $("#cueAlignmentOverride").value = "";
      $("#cueMarginOverride").value = "";
    });
    $("#cuePlacementForm").addEventListener("submit", saveCuePlacement);
  }

  function openCuePlacement(cueId) {
    const cue = state.project?.cues.find((item) => item.id === cueId);
    if (!cue) return;
    batch2.placementCueId = cueId;
    $("#cuePositionOverride").value = cue.position_override || "";
    $("#cueAlignmentOverride").value = cue.alignment_override || "";
    $("#cueMarginOverride").value = cue.vertical_margin_percent_override ?? "";
    $("#cuePlacementDialog").showModal();
  }

  function saveCuePlacement(event) {
    event.preventDefault();
    const cue = state.project?.cues.find((item) => item.id === batch2.placementCueId);
    if (!cue) return;
    const marginRaw = $("#cueMarginOverride").value.trim();
    const margin = marginRaw === "" ? null : Number(marginRaw);
    if (margin != null && (!Number.isFinite(margin) || margin < 2 || margin > 25)) {
      toast("Edge distance must be between 2% and 25%.", "error");
      return;
    }
    remember();
    cue.position_override = $("#cuePositionOverride").value || null;
    cue.alignment_override = $("#cueAlignmentOverride").value || null;
    cue.vertical_margin_percent_override = margin;
    $("#cuePlacementDialog").close();
    renderCues();
    syncPlayback();
    scheduleSave();
  }

  function installRevisionDialog() {
    if ($("#revisionHistoryDialog")) return;
    const dialog = document.createElement("dialog");
    dialog.id = "revisionHistoryDialog";
    dialog.className = "revision-history-dialog";
    dialog.setAttribute("aria-labelledby", "revisionHistoryTitle");
    dialog.innerHTML = `
      <div class="dialog-card revision-history-card">
        <div class="dialog-heading"><div><p class="eyebrow">Automatic restore points</p><h2 id="revisionHistoryTitle">Version history</h2></div><button id="closeRevisionHistory" class="icon-button" type="button" aria-label="Close version history">×</button></div>
        <p class="field-note">Accessible Caption Studio saves restore points as project edits are committed. Restoring creates a safety checkpoint first.</p>
        <div id="revisionHistoryList" class="revision-history-list" role="list"></div>
      </div>`;
    document.body.append(dialog);
    $("#closeRevisionHistory").addEventListener("click", () => dialog.close());
  }

  async function openRevisionHistory() {
    if (!state.project) return;
    const list = $("#revisionHistoryList");
    list.textContent = "Loading restore points…";
    $("#revisionHistoryDialog").showModal();
    try {
      const revisions = await api(`/api/projects/${state.project.id}/revisions`);
      renderRevisionHistory(revisions);
    } catch (error) {
      list.textContent = error.message;
    }
  }

  function renderRevisionHistory(revisions) {
    const list = $("#revisionHistoryList");
    list.replaceChildren();
    if (!revisions.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state revision-empty";
      empty.textContent = "No restore points yet. Your first saved edit will create one automatically.";
      list.append(empty);
      return;
    }
    revisions.forEach((revision) => {
      const row = document.createElement("article");
      row.className = "revision-row";
      row.setAttribute("role", "listitem");
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = new Date(revision.created_at).toLocaleString();
      const meta = document.createElement("span");
      meta.textContent = `${revision.cue_count} captions · ${revision.reason}`;
      copy.append(title, meta);
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "secondary";
      restore.textContent = "Restore";
      restore.addEventListener("click", () => restoreRevision(revision.id, restore));
      row.append(copy, restore);
      list.append(row);
    });
  }

  async function restoreRevision(revisionId, button) {
    button.disabled = true;
    button.textContent = "Restoring…";
    try {
      state.project = await api(`/api/projects/${state.project.id}/revisions/${encodeURIComponent(revisionId)}/restore`, { method: "POST" });
      $("#revisionHistoryDialog").close();
      renderProject();
      toast("Earlier project version restored.");
    } catch (error) {
      toast(error.message, "error");
      button.disabled = false;
      button.textContent = "Restore";
    }
  }

  function updateBatch2Controls() {
    const backup = $("#backupProjectButton");
    if (backup) backup.disabled = !state.project;
  }

  document.addEventListener("DOMContentLoaded", () => {
    installBatch2ProjectControls();
    installBatch2EditorTools();
    installPlacementDialog();
    installRevisionDialog();
    renderProjects();
  });
})();
'''
APP.write_text(app, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")
css += r'''

/* major-iterations Batch 2: contextual project workflow tools */
.project-card { position: relative; }
.project-card.is-favorite { order: -1; }
.project-favorite {
  position: absolute;
  top: .72rem;
  right: .72rem;
  z-index: 2;
  width: 2rem;
  height: 2rem;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 8px;
  color: var(--muted);
  background: color-mix(in srgb, var(--paper) 88%, transparent);
  font-size: 1.05rem;
  line-height: 1;
  box-shadow: none;
}
.project-favorite[aria-pressed="true"] { color: #a66b00; background: color-mix(in srgb, #fff4c2 66%, var(--paper)); }
.project-favorite:focus-visible { outline: 3px solid color-mix(in srgb, var(--blue) 44%, transparent); outline-offset: 2px; }
.project-card .project-open { padding-right: 2.35rem !important; }
.workspace-utility-action { min-height: 34px; padding-inline: .5rem; }

.waveform-timing-panel {
  display: grid;
  gap: .5rem;
  padding: .6rem .65rem .7rem;
  border-top: 1px solid var(--soft-line);
}
.waveform-timing-panel[hidden] { display: none; }
.waveform-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: .75rem;
}
.waveform-heading > div { display: flex; align-items: baseline; gap: .55rem; min-width: 0; }
.waveform-heading strong { font-size: .78rem; }
.waveform-heading span { color: var(--muted); font-size: .7rem; }
.waveform-help { text-align: right; }
.waveform-canvas-wrap {
  position: relative;
  min-width: 0;
  height: 92px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--line) 88%, #7f8ca6);
  border-radius: 9px;
  background: color-mix(in srgb, var(--wash) 58%, var(--paper));
}
#waveformCanvas { display: block; width: 100%; height: 100%; touch-action: none; cursor: crosshair; }
#waveformCanvas:focus-visible { outline: 3px solid color-mix(in srgb, var(--blue) 38%, transparent); outline-offset: -3px; }
.cue-placement-button.is-customized { color: var(--blue-dark); background: var(--sky); }

.cue-placement-dialog { width: min(500px, calc(100vw - 2rem)); }
.cue-placement-card { display: grid; gap: .85rem; }
.cue-placement-card > label { display: grid; gap: .35rem; }
.cue-placement-card select,
.cue-placement-card input { width: 100%; }
.dialog-action-spacer { flex: 1; }

.revision-history-dialog { width: min(620px, calc(100vw - 2rem)); }
.revision-history-card { display: grid; gap: .85rem; max-height: min(760px, calc(100vh - 2rem)); }
.revision-history-list { display: grid; gap: .35rem; overflow-y: auto; min-height: 100px; }
.revision-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: .75rem;
  padding: .7rem .75rem;
  border-radius: 9px;
  background: var(--wash);
}
.revision-row > div { min-width: 0; display: grid; gap: .16rem; }
.revision-row strong { font-size: .78rem; }
.revision-row span { color: var(--muted); font-size: .7rem; overflow-wrap: anywhere; }
.revision-row .secondary { min-height: 34px; padding: .4rem .6rem; }
.revision-empty { margin: 0; }

@media (hover: hover) and (pointer: fine) {
  .project-favorite { transition: transform 140ms cubic-bezier(.23,1,.32,1), background-color 140ms ease, color 140ms ease; }
  .project-favorite:hover { color: #a66b00; background: color-mix(in srgb, #fff4c2 48%, var(--paper)); }
  .project-favorite:active { transform: scale(.96); }
}

@media (max-width: 700px) {
  .waveform-heading { align-items: flex-start; flex-direction: column; gap: .25rem; }
  .waveform-heading > div { align-items: flex-start; flex-direction: column; gap: .12rem; }
  .waveform-help { text-align: left; }
}

@media (max-width: 520px) {
  .revision-row { grid-template-columns: 1fr; }
  .revision-row .secondary { width: 100%; }
  .recent-actions { flex-wrap: wrap; gap: .35rem; }
}
'''
CSS.write_text(css, encoding="utf-8")

browser_test = BROWSER_TEST.read_text(encoding="utf-8")
browser_test = replace_once(
    browser_test,
    '''    expect(page.get_by_label("Sort")).to_be_visible()\n    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")\n''',
    '''    expect(page.get_by_label("Sort")).to_be_visible()\n    expect(page.get_by_role("button", name="Restore backup")).to_be_visible()\n    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")\n''',
    "desktop restore control test",
)
BROWSER_TEST.write_text(browser_test, encoding="utf-8")
