from pathlib import Path

root = Path(__file__).resolve().parents[1]
styles = root / "src/accessible_caption_studio/web/styles.css"
browser_test = root / "tests/browser/test_browser_ui.py"

styles_text = styles.read_text()

anchor = ".project-job-spinner {\n"
override = ".project-card .project-job-status { display: flex; }\n"
if override in styles_text:
    raise SystemExit("project job status specificity override already present")
if anchor not in styles_text:
    raise SystemExit("project job spinner rule not found")
styles_text = styles_text.replace(anchor, override + anchor, 1)
styles.write_text(styles_text)


test_text = browser_test.read_text()
old_geometry = '''          const box = card.getBoundingClientRect();
          const statusBox = status.getBoundingClientRect();
          const actions = card.querySelector('.project-card-actions').getBoundingClientRect();
          return {
            cardHeight: Math.round(box.height),
            statusBottom: statusBox.bottom,
            actionsTop: actions.top,
          };
'''
new_geometry = '''          const box = card.getBoundingClientRect();
          const metaBox = card.querySelector('.project-open > span:not(.project-type):not(.project-job-status)').getBoundingClientRect();
          const statusBox = status.getBoundingClientRect();
          const spinnerBox = status.querySelector('.project-job-spinner').getBoundingClientRect();
          const textBox = status.querySelector('.project-job-status-text').getBoundingClientRect();
          const actions = card.querySelector('.project-card-actions').getBoundingClientRect();
          return {
            cardHeight: Math.round(box.height),
            statusDisplay: getComputedStyle(status).display,
            metaBottom: metaBox.bottom,
            statusTop: statusBox.top,
            statusBottom: statusBox.bottom,
            spinnerTop: spinnerBox.top,
            spinnerCenter: spinnerBox.top + (spinnerBox.height / 2),
            textCenter: textBox.top + (textBox.height / 2),
            actionsTop: actions.top,
          };
'''
if old_geometry not in test_text:
    raise SystemExit("active job geometry fixture not found")
test_text = test_text.replace(old_geometry, new_geometry, 1)

old_assertions = '''    assert geometry["cardHeight"] == 272
    assert geometry["actionsTop"] - geometry["statusBottom"] >= 8
'''
new_assertions = '''    assert geometry["cardHeight"] == 272
    assert geometry["statusDisplay"] == "flex"
    assert geometry["statusTop"] - geometry["metaBottom"] >= 4
    assert geometry["spinnerTop"] - geometry["metaBottom"] >= 4
    assert abs(geometry["spinnerCenter"] - geometry["textCenter"]) <= 1
    assert geometry["actionsTop"] - geometry["statusBottom"] >= 8
'''
if old_assertions not in test_text:
    raise SystemExit("active job geometry assertions not found")
test_text = test_text.replace(old_assertions, new_assertions, 1)
browser_test.write_text(test_text)
