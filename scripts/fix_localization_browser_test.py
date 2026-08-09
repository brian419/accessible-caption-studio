from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "tests" / "browser" / "test_browser_ui.py"

content = TEST.read_text(encoding="utf-8")
old = '''def test_localization_controls_distinguish_spoken_and_caption_languages(page: Page, studio_url: str) -> None:\n    _open(page, studio_url)\n    spoken = page.locator("#defaultTranscriptionLanguage")\n    target = page.locator("#defaultTargetCaptionLanguage")\n    expect(spoken).to_be_visible()\n    expect(target).to_be_visible()\n    spoken.select_option("es")\n    target.select_option("fr")\n'''
new = '''def test_localization_controls_distinguish_spoken_and_caption_languages(page: Page, studio_url: str) -> None:\n    _open(page, studio_url)\n    page.locator("#captioningOptions > summary").click()\n    spoken = page.locator("#defaultTranscriptionLanguage")\n    target = page.locator("#defaultTargetCaptionLanguage")\n    expect(spoken).to_be_visible()\n    expect(target).to_be_visible()\n    spoken.select_option("es")\n    target.select_option("fr")\n'''
if content.count(old) != 1:
    raise RuntimeError(f"Expected localization browser test anchor once, found {content.count(old)}")
TEST.write_text(content.replace(old, new, 1), encoding="utf-8")

for temporary in (
    ROOT / "scripts" / "fix_localization_browser_test.py",
    ROOT / ".github" / "workflows" / "fix-localization-browser-test.yml",
    ROOT / ".github" / "fix-localization-browser-test-trigger.txt",
):
    temporary.unlink(missing_ok=True)

print("Updated localization browser test to open captioning options")
