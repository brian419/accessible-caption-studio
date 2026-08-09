from pathlib import Path

root = Path(__file__).resolve().parents[1]
js_path = root / "src/accessible_caption_studio/web/final_batch.js"
test_path = root / "tests/browser/test_browser_ui.py"

text = js_path.read_text()
old_global = '''      .caption-track-status { display:inline-flex; align-items:center; align-self:end; justify-self:start; min-height:34px; padding:.35rem .65rem; border-radius:999px; background:var(--paper); border:1px solid var(--soft-line); color:var(--muted); font-size:.7rem; font-weight:800; white-space:nowrap; }\n      .caption-track-status.needs-update { color:#8a4b08; border-color:#e7c089; background:#fff7e8; }'''
new_global = '''      .caption-track-status { display:inline-flex; align-items:center; align-self:end; justify-self:start; min-height:0; padding:0; border:0; border-radius:0; background:transparent; color:var(--muted); font-size:.7rem; font-weight:750; line-height:1.35; white-space:normal; }\n      .caption-track-status.needs-update { color:var(--muted); border-color:transparent; background:transparent; }'''
old_dialog = '''      .caption-localization-dialog .caption-track-status { display:inline-flex; align-items:center; justify-self:start; min-height:34px; padding:.35rem .65rem; border-radius:999px; background:var(--paper); border:1px solid var(--soft-line); color:var(--muted); font-size:.7rem; font-weight:800; white-space:nowrap; }\n      .caption-localization-dialog .caption-track-status.needs-update { color:#8a4b08; border-color:#e7c089; background:#fff7e8; }'''
new_dialog = '''      .caption-localization-dialog .caption-track-status { display:inline-flex; align-items:center; justify-self:start; min-height:0; padding:0; border:0; border-radius:0; background:transparent; color:var(--muted); font-size:.7rem; font-weight:750; line-height:1.35; white-space:normal; }\n      .caption-localization-dialog .caption-track-status.needs-update { color:var(--muted); border-color:transparent; background:transparent; }'''
for old, new in ((old_global, new_global), (old_dialog, new_dialog)):
    if old not in text:
        raise SystemExit("Expected localization status CSS block not found")
    text = text.replace(old, new, 1)
js_path.write_text(text)

test = test_path.read_text()
needle = '''    expect(dialog.get_by_role("heading", name="Languages & translations")).to_be_visible()\n'''
addition = '''    expect(dialog.get_by_role("heading", name="Languages & translations")).to_be_visible()\n    status_style = dialog.locator("#captionTrackStatus").evaluate(\n        """element => {\n          const style = getComputedStyle(element);\n          return {\n            background: style.backgroundColor,\n            borderTopWidth: style.borderTopWidth,\n            borderRadius: style.borderRadius,\n            paddingLeft: style.paddingLeft,\n            paddingRight: style.paddingRight,\n          };\n        }"""\n    )\n    assert status_style["background"] == "rgba(0, 0, 0, 0)"\n    assert status_style["borderTopWidth"] == "0px"\n    assert status_style["borderRadius"] == "0px"\n    assert status_style["paddingLeft"] == "0px"\n    assert status_style["paddingRight"] == "0px"\n'''
if needle not in test:
    raise SystemExit("Expected localization modal browser assertion anchor not found")
test = test.replace(needle, addition, 1)
test_path.write_text(test)
