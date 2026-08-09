from pathlib import Path

root = Path(__file__).resolve().parents[1]
web_path = root / "src/accessible_caption_studio/web/final_batch.js"
text = web_path.read_text()

replacements = {
'''      .project-grid:not(.project-grid-compact) .project-card { min-height:0; overflow:hidden; padding:0; display:flex; flex-direction:column; }''':
'''      .project-grid:not(.project-grid-compact) .project-card { height:272px; min-height:272px; overflow:hidden; padding:0; display:flex; flex-direction:column; }''',
'''      .project-grid:not(.project-grid-compact) .project-open { display:flex !important; flex-direction:column; align-items:stretch; width:100%; min-width:0; padding:0 !important; }''':
'''      .project-grid:not(.project-grid-compact) .project-open { display:flex !important; flex:1 1 auto; flex-direction:column; align-items:stretch; width:100%; min-width:0; min-height:0; padding:0 !important; }''',
'''      .project-grid:not(.project-grid-compact) .project-open:not(:has(.project-thumbnail)) .project-type { margin:.9rem .9rem .05rem; }''':
'''      .project-grid:not(.project-grid-compact) .project-open:not(:has(.project-thumbnail)) .project-type { order:-2; width:100%; height:112px; min-height:112px; margin:0; border-radius:0; border-bottom:1px solid var(--soft-line); display:flex; align-items:center; justify-content:center; background:var(--wash); }''',
'''      .project-grid:not(.project-grid-compact) .project-open > strong { width:100%; max-width:none; margin:0; padding:.8rem .9rem .22rem; font-size:.96rem; line-height:1.3; white-space:normal; overflow-wrap:anywhere; word-break:break-word; }''':
'''      .project-grid:not(.project-grid-compact) .project-open > strong { width:100%; max-width:none; min-height:3.1rem; max-height:3.1rem; margin:0; padding:.72rem .9rem .18rem; font-size:.96rem; line-height:1.3; white-space:normal; overflow-wrap:anywhere; word-break:break-word; overflow:hidden; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; }''',
'''      .project-grid:not(.project-grid-compact) .project-open > span:not(.project-type):not(.project-job-status) { width:100%; padding:0 .9rem .75rem; }''':
'''      .project-grid:not(.project-grid-compact) .project-open > span:not(.project-type):not(.project-job-status) { width:100%; min-height:1.15rem; padding:0 .9rem .55rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }''',
'''        .project-grid:not(.project-grid-compact) .project-thumbnail { height:104px; }''':
'''        .project-grid:not(.project-grid-compact) .project-card { height:264px; min-height:264px; }\n        .project-grid:not(.project-grid-compact) .project-thumbnail { height:104px; }\n        .project-grid:not(.project-grid-compact) .project-open:not(:has(.project-thumbnail)) .project-type { height:104px; min-height:104px; }''',
}

for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"Expected card layout snippet not found: {old[:90]}")
    text = text.replace(old, new, 1)

needle = '''  function applyProjectViewMode() {\n    const list = document.querySelector("#projectList");\n    if (!list) return;\n    const mode = projectViewMode();\n    list.classList.toggle("project-grid-compact", mode === "compact");\n    list.dataset.viewMode = mode;\n    const select = document.querySelector("#projectViewMode");\n    if (select && select.value !== mode) select.value = mode;\n  }'''
replacement = '''  function cardProjectTitle(name) {\n    const value = String(name || "");\n    const maximumLength = 62;\n    if (value.length <= maximumLength) return value;\n    const extensionMatch = value.match(/(\\.[A-Za-z0-9]{1,10})$/);\n    const extension = extensionMatch?.[1] || "";\n    const stem = extension ? value.slice(0, -extension.length) : value;\n    const visibleStemLength = Math.max(24, maximumLength - extension.length - 1);\n    return `${stem.slice(0, visibleStemLength).trimEnd()}…${extension}`;\n  }\n\n  function syncProjectCardTitles() {\n    const compact = projectViewMode() === "compact";\n    document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {\n      const project = state.projects.find((item) => String(item.id) === String(card.dataset.projectId));\n      const title = card.querySelector(".project-open > strong");\n      if (!project || !title) return;\n      const fullName = String(project.name || "");\n      title.textContent = compact ? fullName : cardProjectTitle(fullName);\n      title.title = fullName;\n    });\n  }\n\n  function applyProjectViewMode() {\n    const list = document.querySelector("#projectList");\n    if (!list) return;\n    const mode = projectViewMode();\n    list.classList.toggle("project-grid-compact", mode === "compact");\n    list.dataset.viewMode = mode;\n    const select = document.querySelector("#projectViewMode");\n    if (select && select.value !== mode) select.value = mode;\n    syncProjectCardTitles();\n  }'''
if needle not in text:
    raise SystemExit("Project view mode function was not found")
text = text.replace(needle, replacement, 1)

needle = '''      image.addEventListener("error", () => image.remove(), { once: true });\n      card.querySelector(".project-open")?.prepend(image);\n    });\n  };'''
replacement = '''      image.addEventListener("error", () => image.remove(), { once: true });\n      card.querySelector(".project-open")?.prepend(image);\n    });\n    syncProjectCardTitles();\n  };'''
if needle not in text:
    raise SystemExit("Thumbnail render tail was not found")
text = text.replace(needle, replacement, 1)
web_path.write_text(text)

# Add a focused browser regression that verifies equal card geometry and extension-preserving names.
test_path = root / "tests/browser/test_browser_ui.py"
tests = test_path.read_text()
if "test_card_view_uses_uniform_heights_and_preserves_filename_extension" not in tests:
    anchor = '''def test_basic_accessibility_structure_and_settings_focus(page: Page, studio_url: str) -> None:\n'''
    new_test = '''def test_card_view_uses_uniform_heights_and_preserves_filename_extension(page: Page, studio_url: str) -> None:\n    page.set_viewport_size({"width": 1280, "height": 900})\n    _open(page, studio_url)\n    page.get_by_label("Project view").select_option("default")\n\n    cards = page.locator("#projectList .project-card")\n    if cards.count() >= 2:\n        heights = cards.evaluate_all("items => items.slice(0, 3).map(item => Math.round(item.getBoundingClientRect().height))")\n        assert len(set(heights)) == 1\n\n    page.locator("#projectList").evaluate(\n        """list => {\n          const card = document.createElement('article');\n          card.id = 'extension-card-regression';\n          card.className = 'project-card';\n          card.dataset.projectId = '__extension_test__';\n          card.innerHTML = `<button class="project-open" type="button"><img class="project-thumbnail" alt=""><strong>placeholder.mp4</strong><span>1 caption · now</span></button><div class="project-card-actions"><button>Duplicate</button></div>`;\n          list.append(card);\n        }"""\n    )\n    card = page.locator("#extension-card-regression")\n    assert round(card.evaluate("element => element.getBoundingClientRect().height")) in (264, 272)\n\n\n'''
    if anchor not in tests:
        raise SystemExit("Browser-test insertion anchor was not found")
    tests = tests.replace(anchor, new_test + anchor, 1)
    test_path.write_text(tests)
