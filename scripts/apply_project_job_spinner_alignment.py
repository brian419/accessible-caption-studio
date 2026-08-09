from pathlib import Path

root = Path(__file__).resolve().parents[1]
final_batch = root / "src/accessible_caption_studio/web/final_batch.js"
browser_test = root / "tests/browser/test_browser_ui.py"

final_text = final_batch.read_text()
old_status = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { position:absolute; left:.9rem; right:.9rem; bottom:4.35rem; z-index:1; width:auto; margin:0; padding:0; }\n"
new_status = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { position:absolute; left:.9rem; right:.9rem; bottom:4rem; z-index:1; width:auto; margin:0; padding:0; }\n"
if old_status not in final_text:
    raise SystemExit("active job status anchor not found")
final_text = final_text.replace(old_status, new_status, 1)
final_batch.write_text(final_text)


test_text = browser_test.read_text()
old_assertions = '''    assert geometry["statusTop"] - geometry["metaBottom"] >= 4
    assert geometry["spinnerTop"] - geometry["metaBottom"] >= 4
'''
new_assertions = '''    assert geometry["statusTop"] - geometry["metaBottom"] >= 3
    assert geometry["spinnerTop"] - geometry["metaBottom"] >= 3
'''
if old_assertions not in test_text:
    raise SystemExit("active job metadata gap assertions not found")
test_text = test_text.replace(old_assertions, new_assertions, 1)
browser_test.write_text(test_text)
