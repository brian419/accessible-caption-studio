from pathlib import Path

final_path = Path("src/accessible_caption_studio/web/final_batch.js")
styles_path = Path("src/accessible_caption_studio/web/styles.css")

final = final_path.read_text()
old_card = "      .project-grid:not(.project-grid-compact) .project-card { height:272px; min-height:272px; overflow:hidden; padding:0; display:flex; flex-direction:column; }\n"
new_card = old_card + "      .project-grid:not(.project-grid-compact) .project-card.has-active-job { height:292px; min-height:292px; }\n"
if new_card not in final:
    if old_card not in final:
        raise SystemExit("desktop project card rule not found")
    final = final.replace(old_card, new_card, 1)

old_status = "      .project-grid:not(.project-grid-compact) .project-job-status { margin:.05rem .9rem .75rem; }\n"
new_status = "      .project-grid:not(.project-grid-compact) .project-job-status { margin:.05rem .9rem .75rem; }\n      .project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status { margin:.12rem .9rem .9rem; padding-bottom:0; }\n"
if new_status not in final:
    if old_status not in final:
        raise SystemExit("project status rule not found")
    final = final.replace(old_status, new_status, 1)

old_mobile = "        .project-grid:not(.project-grid-compact) .project-card { height:264px; min-height:264px; }\n"
new_mobile = old_mobile + "        .project-grid:not(.project-grid-compact) .project-card.has-active-job { height:284px; min-height:284px; }\n"
if new_mobile not in final:
    if old_mobile not in final:
        raise SystemExit("mobile project card rule not found")
    final = final.replace(old_mobile, new_mobile, 1)

final_path.write_text(final)

styles = styles_path.read_text()
start = styles.find("\n/* Active project job card spacing fix */")
if start != -1:
    end_marker = "\n/* Active project job card spacing selector correction */"
    second = styles.find(end_marker, start)
    if second != -1:
        end = styles.find("\n}", second)
        if end == -1:
            raise SystemExit("selector correction end not found")
        end += 3
        styles = styles[:start] + styles[end:]
    else:
        raise SystemExit("selector correction marker not found")
styles_path.write_text(styles)
