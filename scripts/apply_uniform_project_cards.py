from pathlib import Path

root = Path(__file__).resolve().parents[1]
test_path = root / "tests/browser/test_browser_ui.py"
tests = test_path.read_text()

if "import json\n" not in tests:
    tests = tests.replace("import re\n", "import json\nimport re\n", 1)

start = tests.index("def test_card_view_uses_uniform_heights_and_preserves_filename_extension")
end = tests.index("def test_basic_accessibility_structure_and_settings_focus", start)

new_test = '''def test_card_view_uses_uniform_heights_and_preserves_filename_extension(page: Page, studio_url: str) -> None:\n    page.set_viewport_size({"width": 1280, "height": 900})\n    long_name = "portrait-recording-" + ("very-long-segment-" * 6) + ".mp4"\n    projects = [\n        {\n            "id": "uniform-long",\n            "name": long_name,\n            "cues": [],\n            "media": {"has_video": False},\n            "updated_at": "2026-08-09T07:00:00Z",\n            "is_favorite": False,\n        },\n        {\n            "id": "uniform-short",\n            "name": "short-project.mov",\n            "cues": [],\n            "media": {"has_video": False},\n            "updated_at": "2026-08-09T06:00:00Z",\n            "is_favorite": False,\n        },\n    ]\n    page.route(\n        "**/api/projects",\n        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(projects)),\n    )\n    _open(page, studio_url)\n    page.get_by_label("Project view").select_option("default")\n\n    cards = page.locator("#projectList .project-card")\n    expect(cards).to_have_count(2)\n    heights = cards.evaluate_all("items => items.map(item => Math.round(item.getBoundingClientRect().height))")\n    assert len(set(heights)) == 1\n    assert heights[0] == 272\n\n    long_title = page.locator('[data-project-id="uniform-long"] .project-open > strong')\n    displayed = long_title.inner_text()\n    assert displayed.endswith(".mp4")\n    assert displayed != long_name\n    assert len(displayed) < len(long_name)\n    expect(long_title).to_have_attribute("title", long_name)\n\n    page.get_by_label("Project view").select_option("compact")\n    expect(long_title).to_have_text(long_name)\n\n\n'''

tests = tests[:start] + new_test + tests[end:]
test_path.write_text(tests)
