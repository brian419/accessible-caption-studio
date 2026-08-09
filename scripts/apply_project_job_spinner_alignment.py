from pathlib import Path

root = Path(__file__).resolve().parents[1]
final_batch = root / "src/accessible_caption_studio/web/final_batch.js"

text = final_batch.read_text()
old_actions = "      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.7rem; }\n"
new_actions = "      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.45rem; }\n"
if old_actions not in text:
    raise SystemExit("Cards-view footer spacing rule not found")
text = text.replace(old_actions, new_actions, 1)
final_batch.write_text(text)
