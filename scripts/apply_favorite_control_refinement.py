from pathlib import Path

root = Path(__file__).resolve().parents[1]
styles_path = root / "src/accessible_caption_studio/web/styles.css"
test_path = root / "tests/browser/test_browser_ui.py"

styles = styles_path.read_text()
marker = "/* Shared favorite control refinement */"
if marker not in styles:
    styles += r'''


/* Shared favorite control refinement */
.project-favorite,
.caption-font-favorite {
  width: 34px !important;
  height: 34px !important;
  min-width: 34px !important;
  min-height: 34px !important;
  padding: 0 !important;
  display: inline-grid !important;
  place-items: center !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
  color: var(--muted) !important;
  background: var(--control) !important;
  box-shadow: 0 1px 3px rgba(20, 35, 70, .08) !important;
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
  line-height: 0 !important;
}

.project-favorite::before,
.caption-font-favorite::before {
  width: 18px !important;
  height: 18px !important;
  margin: 0 !important;
  transform: translateY(.5px);
  transform-origin: center;
}

.project-favorite[aria-pressed="true"],
.caption-font-favorite[aria-pressed="true"],
.caption-font-favorite.is-favorite {
  color: #a66b00 !important;
  border-color: color-mix(in srgb, #a66b00 36%, var(--line)) !important;
  background: var(--finding) !important;
}

.project-favorite:focus-visible,
.caption-font-favorite:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--blue) 44%, transparent) !important;
  outline-offset: 2px;
}

@media (hover: hover) and (pointer: fine) {
  .project-favorite,
  .caption-font-favorite {
    transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease, box-shadow 140ms ease;
  }

  .project-favorite:hover,
  .caption-font-favorite:hover {
    color: var(--ink) !important;
    border-color: color-mix(in srgb, var(--blue) 26%, var(--line)) !important;
    background: var(--subtle) !important;
    box-shadow: 0 2px 6px rgba(20, 35, 70, .11) !important;
  }

  .project-favorite[aria-pressed="true"]:hover,
  .caption-font-favorite[aria-pressed="true"]:hover,
  .caption-font-favorite.is-favorite:hover {
    color: #a66b00 !important;
    border-color: color-mix(in srgb, #a66b00 46%, var(--line)) !important;
    background: var(--finding) !important;
  }

  .project-favorite:hover::before,
  .caption-font-favorite:hover::before {
    transform: translateY(.5px) scale(1.06);
  }

  .project-favorite:active::before,
  .caption-font-favorite:active::before {
    transform: translateY(.5px) scale(.92);
  }
}
'''
styles_path.write_text(styles)

tests = test_path.read_text()
start = tests.index("def test_favorite_controls_share_the_same_lucide_icon")
end = tests.index("def test_basic_accessibility_structure_and_settings_focus", start)
new_test = '''def test_favorite_controls_share_one_centered_surface(page: Page, studio_url: str) -> None:\n    projects = [\n        {\n            "id": "favorite-style-project",\n            "name": "favorite-style-project.mp4",\n            "cues": [],\n            "media": {"has_video": False},\n            "updated_at": "2026-08-09T08:00:00Z",\n            "is_favorite": False,\n        }\n    ]\n    page.route(\n        "**/api/projects",\n        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(projects)),\n    )\n    _open(page, studio_url)\n    page.locator("body").evaluate(\n        """body => {\n          const fixture = document.createElement('button');\n          fixture.id = 'font-favorite-style-fixture';\n          fixture.className = 'caption-font-favorite';\n          fixture.setAttribute('aria-label', 'Favorite font');\n          fixture.setAttribute('aria-pressed', 'false');\n          fixture.textContent = '☆';\n          body.append(fixture);\n        }"""\n    )\n\n    project = page.locator('[data-project-id="favorite-style-project"] .project-favorite')\n    font = page.locator("#font-favorite-style-fixture")\n\n    def favorite_surface(locator):\n        return locator.evaluate(\n            """element => {\n              const style = getComputedStyle(element);\n              const icon = getComputedStyle(element, '::before');\n              const rect = element.getBoundingClientRect();\n              return {\n                background: style.backgroundColor,\n                border: style.borderColor,\n                width: Math.round(rect.width),\n                height: Math.round(rect.height),\n                display: style.display,\n                alignItems: style.alignItems,\n                justifyItems: style.justifyItems,\n                iconWidth: icon.width,\n                iconHeight: icon.height,\n                iconTransform: icon.transform,\n                mask: icon.maskImage || icon.webkitMaskImage,\n              };\n            }"""\n        )\n\n    card_surface = favorite_surface(project)\n    font_surface = favorite_surface(font)\n    assert card_surface["background"] == font_surface["background"]\n    assert card_surface["border"] == font_surface["border"]\n    assert card_surface["width"] == font_surface["width"] == 34\n    assert card_surface["height"] == font_surface["height"] == 34\n    assert card_surface["iconWidth"] == font_surface["iconWidth"] == "18px"\n    assert card_surface["iconHeight"] == font_surface["iconHeight"] == "18px"\n    assert card_surface["iconTransform"] == font_surface["iconTransform"]\n    assert card_surface["mask"] == font_surface["mask"]\n    assert "data:image/svg+xml;base64" in card_surface["mask"]\n\n    page.get_by_label("Project view").select_option("compact")\n    compact_surface = favorite_surface(project)\n    assert compact_surface["background"] == card_surface["background"]\n    assert compact_surface["border"] == card_surface["border"]\n    assert compact_surface["width"] == card_surface["width"]\n    assert compact_surface["height"] == card_surface["height"]\n    assert compact_surface["iconTransform"] == card_surface["iconTransform"]\n\n    project.evaluate("element => element.setAttribute('aria-pressed', 'true')")\n    font.evaluate("element => element.setAttribute('aria-pressed', 'true')")\n    active_project = favorite_surface(project)\n    active_font = favorite_surface(font)\n    assert active_project["background"] == active_font["background"]\n    assert active_project["border"] == active_font["border"]\n    assert active_project["mask"] == active_font["mask"]\n    assert active_project["mask"] != card_surface["mask"]\n\n\n'''
tests = tests[:start] + new_test + tests[end:]
test_path.write_text(tests)
