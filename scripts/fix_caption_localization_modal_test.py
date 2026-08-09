from pathlib import Path

path = Path("tests/browser/test_browser_ui.py")
text = path.read_text()
old = 'expect(dialog.get_by_label("Caption track")).to_have_value("track-original")'
new = 'expect(dialog.get_by_label("Caption track", exact=True)).to_have_value("track-original")'
if old not in text:
    raise SystemExit("expected localization modal assertion not found")
path.write_text(text.replace(old, new, 1))
