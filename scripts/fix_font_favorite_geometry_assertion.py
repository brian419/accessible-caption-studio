from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests/browser/test_browser_ui.py"
text = path.read_text()
old = '    assert font_geometry["rightInset"] == 8\n'
new = '    # Includes the font row\'s 1px outer border plus 8px inner spacing.\n    assert font_geometry["rightInset"] == 9\n'
if old not in text:
    raise SystemExit("geometry assertion not found")
path.write_text(text.replace(old, new, 1))
