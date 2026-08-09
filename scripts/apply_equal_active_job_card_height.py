from pathlib import Path

root = Path(__file__).resolve().parents[1]
final_batch = root / "src/accessible_caption_studio/web/final_batch.js"

text = final_batch.read_text()

old_meta = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-open > span:not(.project-type):not(.project-job-status) { padding-bottom:.2rem; }\n"
new_meta = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-open > span:not(.project-type):not(.project-job-status) { padding-bottom:0; }\n"
if old_meta not in text:
    raise SystemExit("active-job metadata spacing rule not found")
text = text.replace(old_meta, new_meta)

old_status = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { margin:.05rem .9rem .35rem; padding-bottom:0; }\n"
new_status = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { margin:.05rem .9rem 0; padding-bottom:0; }\n"
if old_status not in text:
    raise SystemExit("active-job status spacing rule not found")
text = text.replace(old_status, new_status)

old_actions = "      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.7rem; }\n"
new_actions = "      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.4rem; }\n"
if old_actions not in text:
    raise SystemExit("card action spacing rule not found")
text = text.replace(old_actions, new_actions)

final_batch.write_text(text)
