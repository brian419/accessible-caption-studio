from pathlib import Path

path = Path("tests/browser/test_browser_ui.py")
text = path.read_text()
old = '''    card = page.locator("#active-job-spacing-regression")
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
'''
new = '''    card = page.locator("#active-job-spacing-regression")
    geometry = card.evaluate(
        """card => {
          card.classList.add('has-active-job');
          const status = document.createElement('span');
          status.className = 'project-job-status';
          status.innerHTML = `
            <span class="project-job-spinner" aria-hidden="true"></span>
            <span class="project-job-status-text">Transcribing speech and singing · 25%</span>`;
          card.querySelector('.project-open').append(status);

          const box = card.getBoundingClientRect();
          const statusBox = status.getBoundingClientRect();
          const actions = card.querySelector('.project-card-actions').getBoundingClientRect();
          return {
            cardHeight: Math.round(box.height),
            statusBottom: statusBox.bottom,
            actionsTop: actions.top,
          };
        }"""
    )
'''
if old not in text:
    raise SystemExit("active job spacing test block not found")
path.write_text(text.replace(old, new, 1))
