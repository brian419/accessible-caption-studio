from pathlib import Path

root = Path(__file__).resolve().parents[1]
final_batch = root / "src/accessible_caption_studio/web/final_batch.js"

text = final_batch.read_text()

old_card = "      .project-grid:not(.project-grid-compact) .project-card { height:272px; min-height:272px; overflow:hidden; padding:0; display:flex; flex-direction:column; }\n"
new_card = "      .project-grid:not(.project-grid-compact) .project-card { position:relative; height:272px; min-height:272px; overflow:hidden; padding:0; display:flex; flex-direction:column; }\n"
if old_card not in text:
    raise SystemExit("Cards-view project card rule not found")
text = text.replace(old_card, new_card)

old_meta = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-open > span:not(.project-type):not(.project-job-status) { padding-bottom:0; }\n"
if old_meta not in text:
    raise SystemExit("active-job metadata override not found")
text = text.replace(old_meta, "")

old_status = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { margin:.05rem .9rem 0; padding-bottom:0; }\n"
new_status = (
    "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { position:absolute; left:.9rem; right:.9rem; bottom:4.35rem; z-index:1; width:auto; margin:0; padding:0; }\n"
    "      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status-text { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }\n"
)
if old_status not in text:
    raise SystemExit("active-job status override not found")
text = text.replace(old_status, new_status)

old_actions = "      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.4rem; }\n"
new_actions = "      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.7rem; }\n"
if old_actions not in text:
    raise SystemExit("Cards-view action spacing rule not found")
text = text.replace(old_actions, new_actions)

final_batch.write_text(text)
