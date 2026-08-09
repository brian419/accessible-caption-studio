from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL_BATCH = ROOT / "src/accessible_caption_studio/web/final_batch.js"
BROWSER_TEST = ROOT / "tests/browser/test_browser_ui.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find {label}")
    return text.replace(old, new, 1)


source = FINAL_BATCH.read_text(encoding="utf-8")

css_start = source.index("      .caption-track-bar {")
css_end = source.index("      @media (max-width:560px) {", css_start)
new_css = """      .caption-track-bar { display:grid; gap:.65rem; margin:.05rem 0 .85rem; padding:.72rem 0 .8rem; border-top:1px solid var(--soft-line); border-bottom:1px solid var(--soft-line); background:transparent; }
      .caption-track-heading { display:flex; align-items:center; justify-content:space-between; gap:.75rem; min-width:0; }
      .caption-track-heading > div { min-width:0; display:flex; flex-wrap:wrap; align-items:baseline; gap:.4rem .65rem; }
      .caption-track-eyebrow { color:var(--blue); font-size:.67rem; font-weight:900; letter-spacing:.09em; text-transform:uppercase; }
      .caption-track-description { color:var(--muted); font-size:.72rem; line-height:1.4; }
      .caption-track-controls { min-width:0; display:grid; grid-template-columns:minmax(230px,.9fr) minmax(270px,1.1fr); gap:.75rem; align-items:end; }
      .caption-track-current { min-width:0; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:.5rem; }
      .caption-track-create { min-width:0; display:grid; gap:.28rem; }
      .caption-track-field { display:grid; gap:.28rem; min-width:0; font-size:.72rem; font-weight:800; color:var(--muted); }
      .caption-track-control-label { color:var(--muted); font-size:.72rem; font-weight:800; }
      .caption-track-field select, .caption-track-add select { width:100%; min-width:0; min-height:38px; border:1px solid #aeb9ce; border-radius:9px; padding:.45rem .6rem; color:var(--ink); background:var(--control); }
      .caption-track-status { display:inline-flex; align-items:center; align-self:end; min-height:30px; padding:.3rem .55rem; border-radius:999px; background:var(--paper); border:1px solid var(--soft-line); color:var(--muted); font-size:.7rem; font-weight:800; white-space:nowrap; }
      .caption-track-status.needs-update { color:#8a4b08; border-color:#e7c089; background:#fff7e8; }
      .caption-track-add { min-width:0; display:grid; grid-template-columns:minmax(170px,1fr) auto; gap:.4rem; align-items:end; }
      .caption-track-actions { display:flex; flex-wrap:wrap; align-items:center; gap:.4rem; min-width:0; }
      .caption-track-actions[hidden] { display:none !important; }
      .caption-track-actions-label { margin-right:.1rem; color:var(--muted); font-size:.68rem; font-weight:850; }
      .caption-track-context { margin:.55rem 0 0; padding:.55rem .7rem; border-radius:8px; background:var(--wash); color:var(--muted); font-size:.75rem; }
      @media (max-width:760px) {
        .caption-track-controls { grid-template-columns:1fr; align-items:stretch; }
        .caption-track-current { grid-template-columns:minmax(0,1fr) auto; }
        .caption-track-actions { align-items:flex-start; }
      }
      @media (max-width:480px) {
        .caption-track-current { grid-template-columns:1fr; align-items:stretch; }
        .caption-track-status { justify-self:start; }
        .caption-track-add { grid-template-columns:1fr; }
        .caption-track-add button { width:100%; }
        .caption-track-actions { align-items:stretch; }
        .caption-track-actions-label { flex-basis:100%; }
      }
"""
source = source[:css_start] + new_css + source[css_end:]

old_install = """  function installCaptionTrackContext() {
    const panel = document.querySelector(\".editor-panel\");
    if (!panel) return null;
    let bar = document.querySelector(\"#captionTrackBar\");
    if (!bar) {
      bar = document.createElement(\"div\");
      bar.id = \"captionTrackBar\";
      bar.className = \"caption-track-bar\";
      panel.prepend(bar);
    }
    return bar;
  }
"""
new_install = """  function installCaptionTrackContext() {
    const panel = document.querySelector(\".editor-panel\");
    const heading = panel?.querySelector(\".editor-heading\");
    if (!panel || !heading) return null;
    let bar = document.querySelector(\"#captionTrackBar\");
    if (!bar) {
      bar = document.createElement(\"div\");
      bar.id = \"captionTrackBar\";
      bar.className = \"caption-track-bar\";
    }
    heading.after(bar);
    return bar;
  }
"""
source = replace_once(source, old_install, new_install, "caption track placement function")

function_start = source.index("  function renderCaptionTrackContext() {")
html_start = source.index("    bar.innerHTML = `", function_start)
html_end_marker = "      </div>`;\n    const select = bar.querySelector(\"#captionTrackSelect\");"
html_end = source.index(html_end_marker, html_start)
html_end += len("      </div>`;\n")
new_html = """    bar.innerHTML = `
      <div class=\"caption-track-heading\">
        <div>
          <span class=\"caption-track-eyebrow\">Caption localization</span>
          <span class=\"caption-track-description\">Switch languages and manage translated caption tracks.</span>
        </div>
      </div>
      <div class=\"caption-track-controls\">
        <div class=\"caption-track-current\">
          <label class=\"caption-track-field\" for=\"captionTrackSelect\">Caption track
            <select id=\"captionTrackSelect\" aria-label=\"Caption track\"></select>
          </label>
          <span id=\"captionTrackStatus\" class=\"caption-track-status\"></span>
        </div>
        <div class=\"caption-track-create\">
          <span id=\"captionTranslationLabel\" class=\"caption-track-control-label\">Add translation</span>
          <div class=\"caption-track-add\">
            <select id=\"captionTranslationLanguage\" aria-labelledby=\"captionTranslationLabel\">
              <option value=\"\">Choose language…</option>
              ${optionMarkup(availableTargets)}
            </select>
            <button id=\"createCaptionTranslation\" class=\"secondary editor-action\" type=\"button\">Create translation</button>
          </div>
        </div>
      </div>
      <div class=\"caption-track-actions\" role=\"group\" aria-label=\"Active translation actions\">
        <span class=\"caption-track-actions-label\">Translation actions</span>
        <button id=\"captionTrackReview\" class=\"secondary editor-action\" type=\"button\"></button>
        <button id=\"regenerateCaptionTranslation\" class=\"secondary editor-action\" type=\"button\">Regenerate</button>
        <button id=\"deleteCaptionTranslation\" class=\"secondary editor-action\" type=\"button\">Delete translation</button>
      </div>`;
"""
source = source[:html_start] + new_html + source[html_end:]

old_translated = """    const translated = active?.kind === \"translation\";
    review.hidden = !translated;
    regenerate.hidden = !translated;
    remove.hidden = !translated;
"""
new_translated = """    const translated = active?.kind === \"translation\";
    bar.querySelector(\".caption-track-actions\").hidden = !translated;
    review.hidden = !translated;
    regenerate.hidden = !translated;
    remove.hidden = !translated;
"""
source = replace_once(source, old_translated, new_translated, "translation action visibility")
FINAL_BATCH.write_text(source, encoding="utf-8")

browser = BROWSER_TEST.read_text(encoding="utf-8")
test_name = "test_caption_localization_toolbar_sits_below_editor_tools_and_reflows"
if test_name not in browser:
    browser += r'''


def test_caption_localization_toolbar_sits_below_editor_tools_and_reflows(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)

    source = page.evaluate("() => fetch('/final_batch.js').then((response) => response.text())")
    assert 'heading.after(bar);' in source

    page.locator("#homeView").evaluate("element => { element.hidden = true; }")
    page.locator("#workspaceView").evaluate("element => { element.hidden = false; }")
    page.locator(".editor-panel").evaluate(
        """panel => {
          const heading = panel.querySelector('.editor-heading');
          const bar = document.createElement('div');
          bar.id = 'captionTrackBarFixture';
          bar.className = 'caption-track-bar';
          bar.innerHTML = `
            <div class="caption-track-heading">
              <div>
                <span class="caption-track-eyebrow">Caption localization</span>
                <span class="caption-track-description">Switch languages and manage translated caption tracks.</span>
              </div>
            </div>
            <div class="caption-track-controls">
              <div class="caption-track-current">
                <label class="caption-track-field">Caption track
                  <select><option>Korean · Translation · needs update</option></select>
                </label>
                <span class="caption-track-status needs-update">Source changed · review again</span>
              </div>
              <div class="caption-track-create">
                <span class="caption-track-control-label">Add translation</span>
                <div class="caption-track-add">
                  <select><option>Choose language…</option></select>
                  <button class="secondary editor-action" type="button">Create translation</button>
                </div>
              </div>
            </div>
            <div class="caption-track-actions">
              <span class="caption-track-actions-label">Translation actions</span>
              <button class="secondary editor-action" type="button">Mark reviewed</button>
              <button class="secondary editor-action" type="button">Regenerate</button>
              <button class="secondary editor-action" type="button">Delete translation</button>
            </div>`;
          heading.after(bar);
        }"""
    )

    bar = page.locator("#captionTrackBarFixture")
    expect(bar).to_be_visible()
    desktop = bar.evaluate(
        """bar => {
          const heading = document.querySelector('.editor-heading').getBoundingClientRect();
          const box = bar.getBoundingClientRect();
          const current = bar.querySelector('.caption-track-current').getBoundingClientRect();
          const create = bar.querySelector('.caption-track-create').getBoundingClientRect();
          return {
            top: Math.round(box.top),
            headingBottom: Math.round(heading.bottom),
            overflow: Math.round(bar.scrollWidth - bar.clientWidth),
            currentTop: Math.round(current.top),
            createTop: Math.round(create.top),
          };
        }"""
    )
    assert desktop["top"] >= desktop["headingBottom"] - 1
    assert desktop["overflow"] <= 1
    assert abs(desktop["currentTop"] - desktop["createTop"]) <= 2

    page.set_viewport_size({"width": 390, "height": 844})
    mobile = bar.evaluate(
        """bar => {
          const current = bar.querySelector('.caption-track-current').getBoundingClientRect();
          const create = bar.querySelector('.caption-track-create').getBoundingClientRect();
          return {
            overflow: Math.round(bar.scrollWidth - bar.clientWidth),
            currentBottom: Math.round(current.bottom),
            createTop: Math.round(create.top),
          };
        }"""
    )
    assert mobile["overflow"] <= 1
    assert mobile["createTop"] >= mobile["currentBottom"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
'''
    BROWSER_TEST.write_text(browser, encoding="utf-8")
