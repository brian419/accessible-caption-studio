from pathlib import Path

root = Path(__file__).resolve().parents[1]
styles_path = root / "src/accessible_caption_studio/web/styles.css"
test_path = root / "tests/browser/test_browser_ui.py"

styles = styles_path.read_text()
marker = "/* Caption font favorite cell alignment */"
if marker not in styles:
    styles += r'''


/* Caption font favorite cell alignment */
.caption-font-option {
  grid-template-columns: minmax(0, 1fr) 50px;
  align-items: center;
}

.caption-font-option-main {
  align-self: stretch;
}

.caption-font-favorite {
  align-self: center !important;
  justify-self: center !important;
  margin: 0 !important;
}
'''
styles_path.write_text(styles)

tests = test_path.read_text()
old_fixture = '''    page.locator("body").evaluate(
        """body => {
          const fixture = document.createElement('button');
          fixture.id = 'font-favorite-style-fixture';
          fixture.className = 'caption-font-favorite';
          fixture.setAttribute('aria-label', 'Favorite font');
          fixture.setAttribute('aria-pressed', 'false');
          fixture.textContent = '☆';
          body.append(fixture);
        }"""
    )
'''
new_fixture = '''    page.locator("body").evaluate(
        """body => {
          const fixture = document.createElement('div');
          fixture.id = 'font-option-style-fixture';
          fixture.className = 'caption-font-option';
          fixture.innerHTML = `
            <button class="caption-font-option-main" type="button"><span class="caption-font-option-name">Example Font</span></button>
            <button id="font-favorite-style-fixture" class="caption-font-favorite" type="button" aria-label="Favorite font" aria-pressed="false">☆</button>`;
          fixture.style.width = '414px';
          document.body.append(fixture);
        }"""
    )
'''
if old_fixture not in tests:
    raise SystemExit("favorite fixture block not found")
tests = tests.replace(old_fixture, new_fixture, 1)

needle = '''    assert card_surface["mask"] == font_surface["mask"]
    assert "data:image/svg+xml;base64" in card_surface["mask"]

    page.get_by_label("Project view").select_option("compact")
'''
replacement = '''    assert card_surface["mask"] == font_surface["mask"]
    assert "data:image/svg+xml;base64" in card_surface["mask"]

    font_geometry = page.locator("#font-option-style-fixture").evaluate(
        """row => {
          const button = row.querySelector('.caption-font-favorite');
          const rowRect = row.getBoundingClientRect();
          const buttonRect = button.getBoundingClientRect();
          return {
            topInset: Math.round(buttonRect.top - rowRect.top),
            bottomInset: Math.round(rowRect.bottom - buttonRect.bottom),
            rightInset: Math.round(rowRect.right - buttonRect.right),
            rowHeight: Math.round(rowRect.height),
            buttonHeight: Math.round(buttonRect.height),
          };
        }"""
    )
    assert font_geometry["rowHeight"] == 60
    assert font_geometry["buttonHeight"] == 34
    assert abs(font_geometry["topInset"] - font_geometry["bottomInset"]) <= 1
    assert font_geometry["rightInset"] == 8

    page.get_by_label("Project view").select_option("compact")
'''
if needle not in tests:
    raise SystemExit("favorite geometry insertion point not found")
tests = tests.replace(needle, replacement, 1)
test_path.write_text(tests)
