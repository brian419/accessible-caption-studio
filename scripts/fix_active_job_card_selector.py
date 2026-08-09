from pathlib import Path

path = Path("src/accessible_caption_studio/web/styles.css")
text = path.read_text()
marker = "/* Active project job card spacing selector correction */"
if marker not in text:
    text += """

/* Active project job card spacing selector correction */
.project-card.has-active-job {
  height: 292px !important;
  min-height: 292px !important;
}

.project-grid-compact .project-card.has-active-job {
  height: auto !important;
  min-height: 0 !important;
}

@media (max-width: 560px) {
  .project-card.has-active-job {
    height: 284px !important;
    min-height: 284px !important;
  }

  .project-grid-compact .project-card.has-active-job {
    height: auto !important;
    min-height: 0 !important;
  }
}
"""
    path.write_text(text)
