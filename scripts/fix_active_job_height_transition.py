from pathlib import Path

path = Path("src/accessible_caption_studio/web/final_batch.js")
text = path.read_text()
old = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job { height:292px; min-height:292px; }\n"
new = "      .project-grid:not(.project-grid-compact) .project-card.has-active-job { height:292px; min-height:292px; transition:transform .18s,border-color .18s,box-shadow .18s; }\n"
if old not in text:
    raise SystemExit("active job card rule not found")
path.write_text(text.replace(old, new, 1))
