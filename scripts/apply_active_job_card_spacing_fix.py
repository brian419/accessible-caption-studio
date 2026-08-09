from pathlib import Path

styles_path = Path("src/accessible_caption_studio/web/styles.css")
tests_path = Path("tests/browser/test_browser_ui.py")

styles_marker = "/* Active project job card spacing fix */"
styles = styles_path.read_text()
if styles_marker not in styles:
    styles += """

/* Active project job card spacing fix */
.project-grid:not(.project-grid-compact) .project-card.has-active-job {
  height: 292px !important;
  min-height: 292px !important;
}

.project-grid:not(.project-grid-compact) .project-card.has-active-job .project-job-status {
  margin: .1rem .9rem .85rem !important;
  padding-bottom: 0 !important;
}

.project-grid:not(.project-grid-compact) .project-card.has-active-job .project-card-actions {
  margin-top: auto !important;
}

@media (max-width: 560px) {
  .project-grid:not(.project-grid-compact) .project-card.has-active-job {
    height: 284px !important;
    min-height: 284px !important;
  }
}
"""
    styles_path.write_text(styles)


test_name = "def test_active_job_card_reserves_space_above_actions"
tests = tests_path.read_text()
if test_name not in tests:
    tests += r'''


def test_active_job_card_reserves_space_above_actions(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)
    page.get_by_label("Project view").select_option("default")
    _inject_project_card(page, "active-job-spacing-regression")

    card = page.locator("#active-job-spacing-regression")
    card.evaluate(
        """card => {
          card.classList.add('has-active-job');
          const status = document.createElement('span');
          status.className = 'project-job-status';
          status.innerHTML = `
            <span class="project-job-spinner" aria-hidden="true"></span>
            <span class="project-job-status-text">Transcribing speech and singing · 25%</span>`;
          card.querySelector('.project-open').append(status);
        }"""
    )

    geometry = card.evaluate(
        """card => {
          const box = card.getBoundingClientRect();
          const status = card.querySelector('.project-job-status').getBoundingClientRect();
          const actions = card.querySelector('.project-card-actions').getBoundingClientRect();
          return {
            cardHeight: Math.round(box.height),
            statusBottom: status.bottom,
            actionsTop: actions.top,
          };
        }"""
    )
    assert geometry["cardHeight"] == 292
    assert geometry["actionsTop"] - geometry["statusBottom"] >= 8
'''
    tests_path.write_text(tests)
