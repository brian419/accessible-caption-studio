from pathlib import Path

APP = Path('src/accessible_caption_studio/web/app.js')
STYLES = Path('src/accessible_caption_studio/web/styles.css')
TESTS = Path('tests/browser/test_browser_ui.py')

app = APP.read_text()
old_backup = '''  function downloadProjectBackup() {\n    if (!state.project) return;\n    const link = document.createElement("a");\n    link.href = `/api/projects/${state.project.id}/backup`;\n    link.download = "";\n    document.body.append(link);\n    link.click();\n    link.remove();\n  }\n'''
new_backup = '''  function backupDownloadFilename(disposition, projectName) {\n    const value = String(disposition || "");\n    const encoded = value.match(/filename\\*=UTF-8''([^;]+)/i);\n    if (encoded?.[1]) {\n      try { return decodeURIComponent(encoded[1].replace(/^"|"$/g, "")); } catch (_) { /* Use the plain filename or fallback below. */ }\n    }\n    const plain = value.match(/filename="?([^";]+)"?/i);\n    if (plain?.[1]) return plain[1].trim();\n    const safeProjectName = String(projectName || "Accessible Caption Studio project")\n      .replace(/[\\\\/:*?"<>|]+/g, "-")\n      .trim() || "Accessible Caption Studio project";\n    return `${safeProjectName} - backup.acstudio.zip`;\n  }\n\n  async function downloadProjectBackup() {\n    if (!state.project) return;\n    const button = $("#backupProjectButton");\n    if (button?.disabled) return;\n    if (button) {\n      button.disabled = true;\n      button.classList.add("is-loading");\n      button.setAttribute("aria-busy", "true");\n      button.textContent = "Preparing backup…";\n    }\n    try {\n      const response = await fetch(`/api/projects/${state.project.id}/backup`);\n      if (!response.ok) {\n        let message = "The project backup could not be prepared.";\n        try {\n          const payload = await response.json();\n          message = payload?.detail?.message || payload?.detail || message;\n        } catch (_) { /* Keep the friendly fallback. */ }\n        throw new Error(String(message));\n      }\n      const blob = await response.blob();\n      const objectUrl = URL.createObjectURL(blob);\n      const link = document.createElement("a");\n      link.href = objectUrl;\n      link.download = backupDownloadFilename(response.headers.get("content-disposition"), state.project.name);\n      document.body.append(link);\n      link.click();\n      link.remove();\n      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);\n      toast("Backup ready. Download starting.");\n    } catch (error) {\n      toast(error?.message || "The project backup could not be prepared.", "error");\n    } finally {\n      if (button) {\n        button.disabled = false;\n        button.classList.remove("is-loading");\n        button.removeAttribute("aria-busy");\n        button.textContent = "Backup";\n      }\n    }\n  }\n'''
if old_backup not in app:
    raise SystemExit('backup function marker not found')
app = app.replace(old_backup, new_backup, 1)
APP.write_text(app)

styles = STYLES.read_text()
old_text_button = '.text-button { padding-inline: .25rem; }\n'
new_text_button = '''.text-button { padding-inline: .25rem; }\n#backupProjectButton.is-loading { display: inline-flex; align-items: center; gap: .42rem; }\n#backupProjectButton.is-loading::before {\n  content: "";\n  width: 13px;\n  height: 13px;\n  flex: 0 0 13px;\n  border: 2px solid color-mix(in srgb, var(--blue) 22%, transparent);\n  border-top-color: var(--blue);\n  border-radius: 50%;\n  animation: backup-button-spin .8s linear infinite;\n}\n@keyframes backup-button-spin { to { transform: rotate(360deg); } }\n'''
if old_text_button not in styles:
    raise SystemExit('text button style marker not found')
styles = styles.replace(old_text_button, new_text_button, 1)
old_job = '''  width: fit-content;\n  margin-top: .72rem;\n  color: var(--blue-dark) !important;\n'''
new_job = '''  width: fit-content;\n  margin-top: .72rem;\n  padding-bottom: .3rem;\n  color: var(--blue-dark) !important;\n'''
if old_job not in styles:
    raise SystemExit('job status style marker not found')
styles = styles.replace(old_job, new_job, 1)
STYLES.write_text(styles)

tests = TESTS.read_text()
marker = 'def test_backup_button_shows_preparing_state_until_archive_is_ready'
if marker not in tests:
    tests += r'''


def test_backup_button_shows_preparing_state_until_archive_is_ready(page: Page, studio_url: str) -> None:
    _open(page, studio_url)
    page.evaluate(
        """() => {
          state.project = { id: 'backup-loading-fixture', name: 'Backup fixture' };
          const button = document.querySelector('#backupProjectButton');
          button.disabled = false;
          window.__backupDownloadName = null;
          window.__resolveBackup = null;
          window.fetch = () => new Promise((resolve) => {
            window.__resolveBackup = () => resolve(new Response(
              new Blob(['backup-bytes'], { type: 'application/zip' }),
              {
                status: 200,
                headers: { 'Content-Disposition': 'attachment; filename="Backup fixture - backup.acstudio.zip"' },
              },
            ));
          });
          URL.createObjectURL = () => 'blob:backup-fixture';
          URL.revokeObjectURL = () => {};
          HTMLAnchorElement.prototype.click = function clickBackupFixture() {
            window.__backupDownloadName = this.download;
          };
          button.click();
        }"""
    )

    button = page.locator('#backupProjectButton')
    expect(button).to_have_text('Preparing backup…')
    expect(button).to_be_disabled()
    expect(button).to_have_attribute('aria-busy', 'true')
    assert button.evaluate("element => element.classList.contains('is-loading')")

    page.evaluate('window.__resolveBackup()')
    page.wait_for_function('window.__backupDownloadName !== null')
    assert page.evaluate('window.__backupDownloadName') == 'Backup fixture - backup.acstudio.zip'
    expect(button).to_have_text('Backup')
    expect(button).to_be_enabled()
    assert button.evaluate("element => element.getAttribute('aria-busy')") is None
    assert not button.evaluate("element => element.classList.contains('is-loading')")


def test_dynamic_project_job_status_has_space_below_note(page: Page, studio_url: str) -> None:
    _open(page, studio_url)
    page.locator('body').evaluate(
        """body => {
          const status = document.createElement('span');
          status.id = 'dynamic-job-status-spacing-fixture';
          status.className = 'project-job-status';
          status.innerHTML = '<span class="project-job-spinner"></span><span class="project-job-status-text">Translating captions · 47%</span>';
          body.append(status);
        }"""
    )
    status = page.locator('#dynamic-job-status-spacing-fixture')
    expect(status).to_be_visible()
    assert status.evaluate("element => parseFloat(getComputedStyle(element).paddingBottom)") >= 4
'''
    TESTS.write_text(tests)
