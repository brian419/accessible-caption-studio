# Accessible Caption Studio accessibility test plan

Accessible Caption Studio should hold itself to a high accessibility standard because it is an accessibility authoring tool. Automated browser tests catch repeatable regressions, but they do not replace assistive-technology and human usability testing.

## Automated checks

`tests/browser/test_browser_ui.py` currently verifies:

- keyboard access to the skip link and main content
- accessible names for buttons
- no duplicate HTML IDs
- focus entering and leaving the Settings dialog
- desktop and narrow/mobile layouts without document-level horizontal overflow
- the upload area preserving and wrapping a very long filename
- the new project search/filter/sort controls at desktop and mobile widths
- 320 CSS-pixel and 640 CSS-pixel reflow proxies for 400% and 200% zoom
- reduced-motion media emulation with effectively disabled UI transitions
- forced-colors media emulation with primary controls remaining operable

Run the browser suite after installing the development dependencies and Playwright Chromium:

```bash
python -m pip install -e ".[dev]"
python -m playwright install chromium
pytest -q tests/browser
```

CI installs the browser and its Linux dependencies automatically.

## Manual keyboard pass

For each release candidate:

1. Start at the address bar or first browser focus position and use only Tab, Shift+Tab, Enter, Space, and arrow keys.
2. Confirm the skip link becomes visible and moves focus to the main content.
3. Confirm both import tabs, upload controls, YouTube controls, Recent Projects actions, Settings, project cards, editor controls, caption fields, dialogs, and export actions are reachable in a logical order.
4. Open every dialog and confirm focus moves into it, remains understandable while it is open, and returns to a sensible control after closing.
5. Verify no action requires a mouse-only gesture. Drag-and-drop upload must remain optional because the file picker is the keyboard path.

## Screen reader pass

Test at least one supported screen reader/browser combination on the release platform. On macOS, VoiceOver with Safari is the minimum manual pass.

Check:

- page title, landmarks, headings, and the skip link
- Upload a file and YouTube tab names/states
- file-selection feedback
- job progress updates and cancellation state
- Recent Projects names, metadata, and action buttons
- caption timeline fields and speaker/confidence information
- accessibility finding severity and fix buttons
- Settings descriptions and switches
- dialog names and close controls
- export completion status and download link
- error notifications without unexpected focus movement

## Zoom and reflow

Test browser zoom at 200% and 400% on a desktop-width window. Also test a 320 CSS-pixel viewport. Content should remain operable without two-dimensional page scrolling except where a genuinely two-dimensional component would require it.

Pay particular attention to:

- long media and project names
- project search/filter/sort controls
- timeline toolbars and caption rows
- caption customization controls
- Settings and export dialogs
- notification messages

## Contrast and appearance

Test light and dark application themes. Caption appearance warnings are authoring guidance for the rendered media and are separate from the accessibility of the studio interface itself.

Check focus indicators, disabled controls, warning/error states, text on controls, and status badges. Do not treat a color-contrast analyzer result by itself as proof that the complete application conforms to WCAG.

## Reduced motion and system preferences

With the operating system set to reduce motion, verify that project-card movement, loading indicators, notifications, scrolling/follow behavior, and other transitions remain understandable without animation.

Where practical, also test increased contrast or high-contrast system settings and a larger default text size.

## Release record

For a release candidate, record:

- app commit/release version
- OS and browser version
- screen reader/version used
- automated browser test result
- manual keyboard result
- 200% and 400% zoom result
- narrow viewport result
- known accessibility limitations that remain open

This document is an authoring and testing checklist, not a legal certification statement.
