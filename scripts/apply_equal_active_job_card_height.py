from pathlib import Path

root = Path(__file__).resolve().parents[1]
final_batch = root / "src/accessible_caption_studio/web/final_batch.js"
browser_test = root / "tests/browser/test_browser_ui.py"

text = final_batch.read_text()

old_desktop_height = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job { height:292px; min-height:292px; transition:transform .18s,border-color .18s,box-shadow .18s; }\n"
if old_desktop_height not in text:
    raise SystemExit("desktop active-job height rule not found")
text = text.replace(old_desktop_height, "")

old_status = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { margin:.12rem .9rem .9rem; padding-bottom:0; }\n"
new_status = (
    "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-open > span:not(.project-type):not(.project-job-status) { padding-bottom:.2rem; }\n"
    "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { margin:.05rem .9rem .35rem; padding-bottom:0; }\n"
)
if old_status not in text:
    raise SystemExit("active-job status spacing rule not found")
text = text.replace(old_status, new_status)

old_mobile_height = "        .project-grid:not(.project-grid-compact) .project-card.has-active-job { height:284px; min-height:284px; }\n"
if old_mobile_height not in text:
    raise SystemExit("mobile active-job height rule not found")
text = text.replace(old_mobile_height, "")

final_batch.write_text(text)

test_text = browser_test.read_text()
old_assert = '    assert geometry["cardHeight"] == 292\n    assert geometry["actionsTop"] - geometry["statusBottom"] >= 8\n'
new_assert = '    assert geometry["cardHeight"] == 272\n    assert geometry["actionsTop"] - geometry["statusBottom"] >= 8\n'
if old_assert not in test_text:
    raise SystemExit("active-job browser assertion not found")
test_text = test_text.replace(old_assert, new_assert)
browser_test.write_text(test_text)
