from pathlib import Path

root = Path(__file__).resolve().parents[1]
final_batch = root / "src/accessible_caption_studio/web/final_batch.js"
browser_test = root / "tests/browser/test_browser_ui.py"

text = final_batch.read_text()

old = '  const sdhStorageKey = "accessible-caption-sdh-mode";\n'
new = old + '  const projectViewStorageKey = "accessible-caption-project-view";\n'
if old not in text or projectViewStorageKey if False else False:
    pass
text = text.replace(old, new, 1)

old_styles = '''      .project-thumbnail { width:72px; height:46px; object-fit:cover; border-radius:8px; border:1px solid var(--line); background:var(--wash); grid-row:1 / span 3; }
      .project-card .project-open:has(.project-thumbnail) { display:grid; grid-template-columns:72px auto minmax(0,1fr); column-gap:.7rem; align-items:center; }
      .project-card .project-open:has(.project-thumbnail) .project-type { grid-column:2; }
      .project-card .project-open:has(.project-thumbnail) strong, .project-card .project-open:has(.project-thumbnail) > span:not(.project-type):not(.project-job-status) { grid-column:3; }
'''
new_styles = '''      .project-thumbnail { width:88px; height:56px; object-fit:cover; border-radius:8px; border:1px solid var(--line); background:var(--wash); grid-column:1; grid-row:1 / span 2; margin-top:.08rem; }
      .project-card .project-open:has(.project-thumbnail) { display:grid; grid-template-columns:88px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.85rem; row-gap:.08rem; align-items:start; }
      .project-card .project-open:has(.project-thumbnail) .project-type { display:none !important; }
      .project-card .project-open:has(.project-thumbnail) strong { grid-column:2; grid-row:1; min-width:0; margin:.05rem 0 .22rem; line-height:1.25; }
      .project-card .project-open:has(.project-thumbnail) > span:not(.project-type):not(.project-job-status) { grid-column:2; grid-row:2; min-width:0; }
      .project-view-select { min-width:132px; }
      .project-grid.project-grid-compact { grid-template-columns:1fr; gap:.55rem; }
      .project-grid-compact .project-card { min-height:0; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:.75rem; padding:.72rem .8rem; }
      .project-grid-compact .project-card:hover { transform:none; }
      .project-grid-compact .project-open { min-width:0; display:grid; grid-template-columns:40px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.7rem; row-gap:.08rem; align-items:center; }
      .project-grid-compact .project-open .project-type { grid-column:1; grid-row:1 / span 2; }
      .project-grid-compact .project-open strong { grid-column:2; grid-row:1; min-width:0; margin:0 0 .16rem; font-size:.92rem; line-height:1.25; }
      .project-grid-compact .project-open > span:not(.project-type):not(.project-job-status) { grid-column:2; grid-row:2; min-width:0; }
      .project-grid-compact .project-open:has(.project-thumbnail) { grid-template-columns:64px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.7rem; }
      .project-grid-compact .project-open:has(.project-thumbnail) .project-thumbnail { width:64px; height:40px; grid-column:1; grid-row:1 / span 2; margin:0; }
      .project-grid-compact .project-card-actions { align-self:center; display:flex; gap:.35rem; margin:0; padding:0; border-top:0; }
      .project-grid-compact .project-action { min-height:30px; padding:.3rem .5rem; }
'''
if old_styles not in text:
    raise SystemExit("thumbnail style block not found")
text = text.replace(old_styles, new_styles, 1)

old_mobile = '''        .project-card .project-open:has(.project-thumbnail) { grid-template-columns:58px auto minmax(0,1fr); }
        .project-thumbnail { width:58px; height:42px; }
'''
new_mobile = '''        .project-card .project-open:has(.project-thumbnail) { grid-template-columns:64px minmax(0,1fr); }
        .project-thumbnail { width:64px; height:42px; }
        .project-view-select { grid-column:1 / -1; min-width:0; }
        .project-grid-compact .project-card { grid-template-columns:1fr; align-items:stretch; }
        .project-grid-compact .project-card-actions { padding-top:.55rem; border-top:1px solid var(--soft-line); }
'''
if old_mobile not in text:
    raise SystemExit("mobile thumbnail style block not found")
text = text.replace(old_mobile, new_mobile, 1)

anchor = '''  const previousRenderProjectsFinal = renderProjects;
'''
view_functions = '''  function projectViewMode() {
    const value = readPreference(projectViewStorageKey, "default");
    return value === "compact" ? "compact" : "default";
  }

  function applyProjectViewMode() {
    const list = document.querySelector("#projectList");
    if (!list) return;
    const mode = projectViewMode();
    list.classList.toggle("project-grid-compact", mode === "compact");
    list.dataset.viewMode = mode;
    const select = document.querySelector("#projectViewMode");
    if (select && select.value !== mode) select.value = mode;
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
        <option value="default">Default cards</option>
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

'''
if anchor not in text:
    raise SystemExit("renderProjects anchor not found")
text = text.replace(anchor, view_functions + anchor, 1)

old_render = '''  renderProjects = function renderProjectsWithThumbnails() {
    previousRenderProjectsFinal();
    document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {
'''
new_render = '''  renderProjects = function renderProjectsWithThumbnails() {
    previousRenderProjectsFinal();
    installProjectViewControl();
    applyProjectViewMode();
    document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {
'''
if old_render not in text:
    raise SystemExit("renderProjects wrapper not found")
text = text.replace(old_render, new_render, 1)

final_batch.write_text(text)

browser = browser_test.read_text()
old_expect = '''    expect(page.get_by_label("Sort")).to_be_visible()\n    expect(page.get_by_role("button", name="Restore backup")).to_be_visible()\n'''
new_expect = '''    expect(page.get_by_label("Sort")).to_be_visible()\n    expect(page.get_by_label("Project view")).to_be_visible()\n    expect(page.get_by_role("button", name="Restore backup")).to_be_visible()\n'''
if old_expect not in browser:
    raise SystemExit("desktop browser test anchor not found")
browser = browser.replace(old_expect, new_expect, 1)

append_test = '''\n\ndef test_project_view_mode_persists_between_visits(page: Page, studio_url: str) -> None:\n    _open(page, studio_url)\n\n    view = page.get_by_label("Project view")\n    expect(view).to_have_value("default")\n    view.select_option("compact")\n    expect(page.locator("#projectList")).to_have_class(re.compile(r"\\bproject-grid-compact\\b"))\n\n    page.reload(wait_until="networkidle")\n    expect(page.locator("#projectBrowserControls")).to_be_attached()\n    expect(page.get_by_label("Project view")).to_have_value("compact")\n    expect(page.locator("#projectList")).to_have_class(re.compile(r"\\bproject-grid-compact\\b"))\n\n    page.get_by_label("Project view").select_option("default")\n    expect(page.locator("#projectList")).not_to_have_class(re.compile(r"\\bproject-grid-compact\\b"))\n'''
if "test_project_view_mode_persists_between_visits" not in browser:
    browser += append_test
browser_test.write_text(browser)
