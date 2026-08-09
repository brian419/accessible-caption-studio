from pathlib import Path

root = Path(__file__).resolve().parents[1]
styles_path = root / "src/accessible_caption_studio/web/styles.css"
styles = styles_path.read_text()

marker = "/* Shared Icônes / Lucide favorite icon */"
if marker not in styles:
    styles += r'''

/* Shared Icônes / Lucide favorite icon */
:root {
  --favorite-star-outline: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xMS41MjUgMi4yOTVhLjUzLjUzIDAgMCAxIC45NSAwbDIuMzEgNC42NzlhMi4xMjMgMi4xMjMgMCAwIDAgMS41OTUgMS4xNmw1LjE2Ni43NTZhLjUzLjUzIDAgMCAxIC4yOTQuOTA0bC0zLjczNiAzLjYzOGEyLjEyMyAyLjEyMyAwIDAgMC0uNjExIDEuODc4bC44ODIgNS4xNGEuNTMuNTMgMCAwIDEtLjc3MS41NmwtNC42MTgtMi40MjhhMi4xMjIgMi4xMjIgMCAwIDAtMS45NzMgMEw2LjM5NiAyMS4wMWEuNTMuNTMgMCAwIDEtLjc3LS41NmwuODgxLTUuMTM5YTIuMTIyIDIuMTIyIDAgMCAwLS42MTEtMS44NzlMMi4xNiA5Ljc5NWEuNTMuNTMgMCAwIDEgLjI5NC0uOTA2bDUuMTY1LS43NTVhMi4xMjIgMi4xMjIgMCAwIDAgMS41OTctMS4xNnoiLz48L3N2Zz4=");
  --favorite-star-filled: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iYmxhY2siIHN0cm9rZT0iYmxhY2siIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMTEuNTI1IDIuMjk1YS41My41MyAwIDAgMSAuOTUgMGwyLjMxIDQuNjc5YTIuMTIzIDIuMTIzIDAgMCAwIDEuNTk1IDEuMTZsNS4xNjYuNzU2YS41My41MyAwIDAgMSAuMjk0LjkwNGwtMy43MzYgMy42MzhhMi4xMjMgMi4xMjMgMCAwIDAtLjYxMSAxLjg3OGwuODgyIDUuMTRhLjUzLjUzIDAgMCAxLS43NzEuNTZsLTQuNjE4LTIuNDI4YTIuMTIyIDIuMTIyIDAgMCAwLTEuOTczIDBMNi4zOTYgMjEuMDFhLjUzLjUzIDAgMCAxLS43Ny0uNTZsLjg4MS01LjEzOWEyLjEyMiAyLjEyMiAwIDAgMC0uNjExLTEuODc5TDIuMTYgOS43OTVhLjUzLjUzIDAgMCAxIC4yOTQtLjkwNmw1LjE2NS0uNzU1YTIuMTIyIDIuMTIyIDAgMCAwIDEuNTk3LTEuMTZ6Ii8+PC9zdmc+");
}

.project-favorite,
.caption-font-favorite {
  font-size: 0 !important;
}

.project-favorite::before,
.caption-font-favorite::before {
  content: "";
  display: block;
  width: 18px;
  height: 18px;
  background: currentColor;
  -webkit-mask: var(--favorite-star-outline) center / contain no-repeat;
  mask: var(--favorite-star-outline) center / contain no-repeat;
}

.project-favorite[aria-pressed="true"]::before,
.caption-font-favorite[aria-pressed="true"]::before,
.caption-font-favorite.is-favorite::before {
  -webkit-mask-image: var(--favorite-star-filled);
  mask-image: var(--favorite-star-filled);
}

.project-favorite {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
}

.caption-font-favorite {
  display: grid;
  place-items: center;
}

@media (hover: hover) and (pointer: fine) {
  .project-favorite::before,
  .caption-font-favorite::before {
    transition: transform 140ms cubic-bezier(.23, 1, .32, 1);
  }

  .project-favorite:hover::before,
  .caption-font-favorite:hover::before {
    transform: scale(1.08);
  }

  .project-favorite:active::before,
  .caption-font-favorite:active::before {
    transform: scale(.92);
  }
}
'''
styles_path.write_text(styles)

# Add a browser regression proving both favorite systems use the same icon masks.
test_path = root / "tests/browser/test_browser_ui.py"
tests = test_path.read_text()
if "test_favorite_controls_share_the_same_lucide_icon" not in tests:
    anchor = "def test_basic_accessibility_structure_and_settings_focus(page: Page, studio_url: str) -> None:\n"
    test = '''def test_favorite_controls_share_the_same_lucide_icon(page: Page, studio_url: str) -> None:\n    _open(page, studio_url)\n    page.locator("body").evaluate(\n        """body => {\n          const fixture = document.createElement('div');\n          fixture.id = 'favorite-icon-fixture';\n          fixture.innerHTML = `\n            <button class="project-favorite" aria-label="Favorite project" aria-pressed="false">☆</button>\n            <button class="caption-font-favorite" aria-label="Favorite font" aria-pressed="false">☆</button>`;\n          body.append(fixture);\n        }"""\n    )\n\n    project = page.locator("#favorite-icon-fixture .project-favorite")\n    font = page.locator("#favorite-icon-fixture .caption-font-favorite")\n    inactive = page.evaluate(\n        """() => {\n          const project = document.querySelector('#favorite-icon-fixture .project-favorite');\n          const font = document.querySelector('#favorite-icon-fixture .caption-font-favorite');\n          const projectIcon = getComputedStyle(project, '::before');\n          const fontIcon = getComputedStyle(font, '::before');\n          return {\n            projectMask: projectIcon.maskImage || projectIcon.webkitMaskImage,\n            fontMask: fontIcon.maskImage || fontIcon.webkitMaskImage,\n            projectFontSize: getComputedStyle(project).fontSize,\n            fontFontSize: getComputedStyle(font).fontSize,\n          };\n        }"""\n    )\n    assert inactive["projectMask"] == inactive["fontMask"]\n    assert "data:image/svg+xml;base64" in inactive["projectMask"]\n    assert inactive["projectFontSize"] == "0px"\n    assert inactive["fontFontSize"] == "0px"\n\n    project.evaluate("element => element.setAttribute('aria-pressed', 'true')")\n    font.evaluate("element => element.setAttribute('aria-pressed', 'true')")\n    active = page.evaluate(\n        """() => {\n          const project = getComputedStyle(document.querySelector('#favorite-icon-fixture .project-favorite'), '::before');\n          const font = getComputedStyle(document.querySelector('#favorite-icon-fixture .caption-font-favorite'), '::before');\n          return {\n            projectMask: project.maskImage || project.webkitMaskImage,\n            fontMask: font.maskImage || font.webkitMaskImage,\n          };\n        }"""\n    )\n    assert active["projectMask"] == active["fontMask"]\n    assert active["projectMask"] != inactive["projectMask"]\n\n\n'''
    if anchor not in tests:
        raise SystemExit("Browser test insertion point was not found")
    tests = tests.replace(anchor, test + anchor, 1)
    test_path.write_text(tests)
