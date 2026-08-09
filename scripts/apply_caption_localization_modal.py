from pathlib import Path

FINAL_BATCH = Path("src/accessible_caption_studio/web/final_batch.js")
BROWSER_TEST = Path("tests/browser/test_browser_ui.py")


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[:start_index] + replacement + text[end_index:]


source = FINAL_BATCH.read_text()

modal_styles = r'''
      /* Caption localization is intentionally modal so it never consumes timeline height. */
      .caption-localization-dialog { width:min(650px,calc(100vw - 2rem)); max-height:calc(100vh - 2rem); }
      .caption-localization-card { display:grid; gap:1rem; }
      .caption-localization-copy { margin:-.35rem 0 0; color:var(--muted); font-size:.78rem; line-height:1.5; }
      .caption-localization-body { display:grid; gap:.9rem; }
      .caption-localization-section { display:grid; gap:.7rem; padding:.95rem 1rem; border:1px solid var(--soft-line); border-radius:12px; background:var(--wash); }
      .caption-localization-section[hidden] { display:none !important; }
      .caption-localization-section-heading { display:grid; gap:.16rem; }
      .caption-localization-section-heading h3 { margin:0; color:var(--ink); font-size:.88rem; }
      .caption-localization-section-heading p { margin:0; color:var(--muted); font-size:.72rem; line-height:1.4; }
      .caption-localization-dialog .caption-track-current { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.65rem; align-items:end; }
      .caption-localization-dialog .caption-track-field { display:grid; gap:.38rem; min-width:0; color:var(--muted); font-size:.72rem; font-weight:800; }
      .caption-localization-dialog .caption-track-field select,
      .caption-localization-dialog .caption-track-add select { width:100%; min-width:0; min-height:40px; border:1px solid #aeb9ce; border-radius:9px; padding:.48rem .65rem; color:var(--ink); background:var(--control); }
      .caption-localization-dialog .caption-track-status { display:inline-flex; align-items:center; justify-self:start; min-height:34px; padding:.35rem .65rem; border-radius:999px; background:var(--paper); border:1px solid var(--soft-line); color:var(--muted); font-size:.7rem; font-weight:800; white-space:nowrap; }
      .caption-localization-dialog .caption-track-status.needs-update { color:#8a4b08; border-color:#e7c089; background:#fff7e8; }
      .caption-localization-dialog .caption-track-add { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.55rem; align-items:end; }
      .caption-localization-dialog .caption-track-actions { display:flex; flex-wrap:wrap; gap:.45rem; align-items:center; }
      .caption-localization-dialog .caption-track-actions button { min-height:36px; }
      @media (max-width:560px) {
        .caption-localization-dialog { width:calc(100vw - 1rem); max-height:calc(100vh - 1rem); }
        .caption-localization-dialog .caption-track-current,
        .caption-localization-dialog .caption-track-add { grid-template-columns:1fr; }
        .caption-localization-dialog .caption-track-add button { width:100%; }
        .caption-localization-dialog .caption-track-actions { display:grid; grid-template-columns:1fr; }
        .caption-localization-dialog .caption-track-actions button { width:100%; }
      }
'''
anchor = "      @media (prefers-reduced-motion: reduce) {"
if modal_styles.strip() not in source:
    source = source.replace(anchor, modal_styles + "\n" + anchor, 1)

start = "  function installCaptionTrackContext() {"
end = "  async function switchCaptionTrack(trackId) {"
replacement = r'''  function installCaptionLocalizationDialog() {
    if (document.querySelector("#captionLocalizationDialog")) return;
    const dialog = document.createElement("dialog");
    dialog.id = "captionLocalizationDialog";
    dialog.className = "caption-localization-dialog";
    dialog.setAttribute("aria-labelledby", "captionLocalizationTitle");
    dialog.innerHTML = `
      <div class="dialog-card caption-localization-card">
        <div class="dialog-heading">
          <div><p class="eyebrow">Caption localization</p><h2 id="captionLocalizationTitle">Languages & translations</h2></div>
          <button id="closeCaptionLocalization" class="icon-button" type="button" aria-label="Close caption localization">×</button>
        </div>
        <p class="caption-localization-copy">Switch the language shown in the timeline, add translated caption tracks, and manage translation review without taking space away from the caption editor.</p>
        <div id="captionLocalizationBody" class="caption-localization-body"></div>
        <div class="button-row dialog-actions"><span class="dialog-action-spacer"></span><button id="doneCaptionLocalization" class="primary" type="button">Done</button></div>
      </div>`;
    document.body.append(dialog);
    dialog.querySelector("#closeCaptionLocalization").addEventListener("click", () => dialog.close());
    dialog.querySelector("#doneCaptionLocalization").addEventListener("click", () => dialog.close());
  }

  function installCaptionLocalizationAction() {
    const more = document.querySelector(".editor-more-popover");
    if (!more || document.querySelector("#captionLocalizationButton")) return;
    const button = document.createElement("button");
    button.id = "captionLocalizationButton";
    button.className = "secondary editor-action editor-more-action";
    button.type = "button";
    button.textContent = "Caption localization";
    button.addEventListener("click", () => {
      if (!state.project) return;
      renderCaptionLocalizationDialog();
      document.querySelector("#captionLocalizationDialog")?.showModal();
    });
    more.append(button);
  }

  function syncCaptionTrackSourceToolAvailability() {
    const active = activeCaptionTrack();
    const translated = active?.kind === "translation";
    ["#improveTranscriptButton", "#redetectSpeakersButton"].forEach((selector) => {
      const button = document.querySelector(selector);
      if (!button) return;
      button.disabled = translated;
      button.title = translated ? "Switch to the Original caption track to use this source-analysis tool." : "";
    });
    document.querySelectorAll(".cue-actions button").forEach((button) => {
      if (/overlapping voices/i.test(button.textContent || "")) {
        button.disabled = translated;
        button.title = translated ? "Switch to the Original caption track to analyze overlapping voices." : "";
      }
    });
    updateExportTrackContext();
  }

  function renderCaptionLocalizationDialog() {
    document.querySelector("#captionTrackBar")?.remove();
    const project = state.project;
    const body = document.querySelector("#captionLocalizationBody");
    if (!project || !body) return;
    const tracks = project.caption_tracks || [];
    const active = activeCaptionTrack(project);
    const existingTargets = new Set(tracks.filter((track) => track.kind === "translation").map((track) => track.language));
    const sourceLanguage = tracks.find((track) => track.kind === "original")?.language || project.detected_language || project.spoken_language || "en";
    const availableTargets = languages.filter(([code]) => code !== "auto" && code !== sourceLanguage && !existingTargets.has(code));
    const translated = active?.kind === "translation";
    body.innerHTML = `
      <section class="caption-localization-section" aria-labelledby="captionLocalizationCurrentTitle">
        <div class="caption-localization-section-heading">
          <h3 id="captionLocalizationCurrentTitle">Current caption track</h3>
          <p>Choose which language appears in the caption timeline, preview, validation, and exports.</p>
        </div>
        <div class="caption-track-current">
          <label class="caption-track-field" for="captionTrackSelect">Caption track
            <select id="captionTrackSelect" aria-label="Caption track"></select>
          </label>
          <span id="captionTrackStatus" class="caption-track-status"></span>
        </div>
      </section>
      <section class="caption-localization-section" aria-labelledby="captionLocalizationAddTitle">
        <div class="caption-localization-section-heading">
          <h3 id="captionLocalizationAddTitle">Add translation</h3>
          <p>Create another language from the Original caption track. The source captions stay unchanged.</p>
        </div>
        <div class="caption-track-add">
          <select id="captionTranslationLanguage" aria-label="Translated caption language">
            <option value="">Choose language…</option>
            ${optionMarkup(availableTargets)}
          </select>
          <button id="createCaptionTranslation" class="secondary editor-action" type="button">Create translation</button>
        </div>
      </section>
      <section id="captionTranslationActions" class="caption-localization-section" aria-labelledby="captionLocalizationActionsTitle" ${translated ? "" : "hidden"}>
        <div class="caption-localization-section-heading">
          <h3 id="captionLocalizationActionsTitle">Translation actions</h3>
          <p>Review, refresh, or remove the currently selected translated caption track.</p>
        </div>
        <div class="caption-track-actions" role="group" aria-label="Active translation actions">
          <button id="captionTrackReview" class="secondary editor-action" type="button"></button>
          <button id="regenerateCaptionTranslation" class="secondary editor-action" type="button">Regenerate</button>
          <button id="deleteCaptionTranslation" class="secondary editor-action" type="button">Delete translation</button>
        </div>
      </section>`;

    const select = body.querySelector("#captionTrackSelect");
    tracks.forEach((track) => {
      const option = document.createElement("option");
      option.value = track.id;
      option.textContent = captionTrackOptionLabel(track);
      select.append(option);
    });
    select.value = active?.id || "";
    const status = body.querySelector("#captionTrackStatus");
    status.textContent = captionTrackStatusLabel(active);
    status.classList.toggle("needs-update", active?.review_state === "needs_update");

    const createButton = body.querySelector("#createCaptionTranslation");
    const targetSelect = body.querySelector("#captionTranslationLanguage");
    const sourceCues = tracks.find((track) => track.kind === "original")?.cues || project.cues || [];
    createButton.disabled = !availableTargets.length || !sourceCues.length;
    targetSelect.disabled = !availableTargets.length;
    select.addEventListener("change", () => switchCaptionTrack(select.value));
    createButton.addEventListener("click", () => createCaptionTranslation(false));

    if (translated) {
      const review = body.querySelector("#captionTrackReview");
      const regenerate = body.querySelector("#regenerateCaptionTranslation");
      const remove = body.querySelector("#deleteCaptionTranslation");
      review.textContent = active.review_state === "reviewed" ? "Mark needs review" : "Mark reviewed";
      regenerate.hidden = active.review_state !== "needs_update";
      review.addEventListener("click", toggleCaptionTrackReview);
      regenerate.addEventListener("click", () => createCaptionTranslation(true));
      remove.addEventListener("click", deleteCaptionTranslation);
    }
    syncCaptionTrackSourceToolAvailability();
  }

'''
source = replace_between(source, start, end, replacement)

source = source.replace(
    '      renderProject();\n      toast(`Now editing ${captionTrackOptionLabel(activeCaptionTrack())}.`);',
    '      renderProject();\n      document.querySelector("#captionLocalizationDialog")?.close();\n      toast(`Now editing ${captionTrackOptionLabel(activeCaptionTrack())}.`);',
    1,
)
source = source.replace(
    '      monitorJob(job, state.project.id, state.project.name);\n      toast(`${replaceExisting ? "Regenerating" : "Creating"} ${languageLabel(target)} captions locally.`);',
    '      monitorJob(job, state.project.id, state.project.name);\n      document.querySelector("#captionLocalizationDialog")?.close();\n      toast(`${replaceExisting ? "Regenerating" : "Creating"} ${languageLabel(target)} captions locally.`);',
    1,
)
source = source.replace(
    '  renderProject = function renderProjectWithLocalization() {\n    previousRenderProjectLocalization();\n    renderCaptionTrackContext();\n  };',
    '  renderProject = function renderProjectWithLocalization() {\n    previousRenderProjectLocalization();\n    document.querySelector("#captionTrackBar")?.remove();\n    syncCaptionTrackSourceToolAvailability();\n    if (document.querySelector("#captionLocalizationDialog")?.open) renderCaptionLocalizationDialog();\n  };',
    1,
)
source = source.replace(
    '    installProjectPreferenceAction();\n    installExportOptions();',
    '    installProjectPreferenceAction();\n    installCaptionLocalizationDialog();\n    installCaptionLocalizationAction();\n    installExportOptions();',
    1,
)

if "heading.after(bar);" in source:
    raise SystemExit("persistent localization bar insertion still exists")
if "installCaptionTrackContext" in source or "renderCaptionTrackContext" in source:
    raise SystemExit("legacy localization bar functions still exist")
if "installCaptionLocalizationDialog" not in source or "installCaptionLocalizationAction" not in source:
    raise SystemExit("modal localization functions were not installed")

FINAL_BATCH.write_text(source)


tests = BROWSER_TEST.read_text()
test_start = "def test_caption_localization_toolbar_sits_below_editor_tools_and_reflows(page: Page, studio_url: str) -> None:"
start_index = tests.index(test_start)
replacement_test = r'''def test_caption_localization_is_modal_and_preserves_timeline_height(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)

    source = page.evaluate("() => fetch('/final-batch.js').then((response) => response.text())")
    assert 'heading.after(bar);' not in source
    assert 'installCaptionLocalizationDialog' in source
    assert 'installCaptionLocalizationAction' in source

    page.locator("#homeView").evaluate("element => { element.hidden = true; }")
    page.locator("#workspaceView").evaluate("element => { element.hidden = false; }")
    before = page.locator(".column-labels").evaluate("element => Math.round(element.getBoundingClientRect().top)")
    assert page.locator("#captionTrackBar").count() == 0

    page.evaluate(
        """() => {
          state.project = {
            id: 'modal-layout-fixture',
            name: 'Localization layout fixture',
            active_caption_track_id: 'track-original',
            caption_tracks: [
              { id: 'track-original', kind: 'original', language: 'en', review_state: 'reviewed', cues: [{ id: 'cue-1', start: 0, end: 1, text: 'Hello' }] },
              { id: 'track-ko', kind: 'translation', language: 'ko', review_state: 'needs_update', cues: [{ id: 'cue-1-ko', start: 0, end: 1, text: '안녕하세요' }] },
            ],
            cues: [{ id: 'cue-1', start: 0, end: 1, text: 'Hello' }],
          };
          document.querySelector('#captionLocalizationButton').click();
        }"""
    )

    dialog = page.locator("#captionLocalizationDialog")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("heading", name="Languages & translations")).to_be_visible()
    expect(dialog.get_by_label("Caption track")).to_have_value("track-original")
    expect(dialog.get_by_label("Translated caption language")).to_be_visible()
    assert page.locator("#captionTrackBar").count() == 0
    after = page.locator(".column-labels").evaluate("element => Math.round(element.getBoundingClientRect().top)")
    assert abs(after - before) <= 1

    page.set_viewport_size({"width": 390, "height": 844})
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
    assert dialog.locator("#captionLocalizationBody").evaluate("element => element.scrollWidth <= element.clientWidth + 1")
'''
tests = tests[:start_index] + replacement_test + "\n"
BROWSER_TEST.write_text(tests)
