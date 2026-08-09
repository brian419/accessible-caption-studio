from pathlib import Path

root = Path(__file__).resolve().parents[1]
styles = root / "src/accessible_caption_studio/web/styles.css"
app = root / "src/accessible_caption_studio/web/app.js"
browser_test = root / "tests/browser/test_browser_ui.py"

styles_text = styles.read_text()
old_save_status = ".save-status { color: var(--teal); font-size: .84rem; }\n"
new_save_status = '''.save-status { color: var(--teal); font-size: .84rem; }
.workspace-actions > #saveStatus,
.workspace-actions > #analyzeButton,
.workspace-actions > #validateButton,
.workspace-actions > #backupProjectButton {
  height: 38px;
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  font-size: .84rem;
  font-weight: 750;
  line-height: 1;
  white-space: nowrap;
  box-shadow: none;
}
.workspace-actions > #saveStatus {
  width: 88px;
  min-width: 88px;
  padding: 0 .75rem;
  border: 1px solid #aeb9ce;
  background: var(--control);
  color: var(--teal);
}
.workspace-actions > #analyzeButton,
.workspace-actions > #validateButton,
.workspace-actions > #backupProjectButton {
  padding: 0 .8rem;
}
.workspace-actions > #backupProjectButton {
  width: 116px;
  min-width: 116px;
}
'''
if old_save_status not in styles_text:
    raise SystemExit("workspace save status rule not found")
styles_text = styles_text.replace(old_save_status, new_save_status, 1)
styles.write_text(styles_text)

app_text = app.read_text()
old_backup_class = '      backup.className = "text-button workspace-utility-action";\n'
new_backup_class = '      backup.className = "secondary workspace-utility-action";\n'
if old_backup_class not in app_text:
    raise SystemExit("backup button class assignment not found")
app_text = app_text.replace(old_backup_class, new_backup_class, 1)

old_loading_label = '''      button.setAttribute("aria-busy", "true");
      button.textContent = "Preparing backup…";
'''
new_loading_label = '''      button.setAttribute("aria-busy", "true");
      button.setAttribute("aria-label", "Preparing project backup");
      button.textContent = "Preparing…";
'''
if old_loading_label not in app_text:
    raise SystemExit("backup loading label block not found")
app_text = app_text.replace(old_loading_label, new_loading_label, 1)

old_loading_cleanup = '''        button.classList.remove("is-loading");
        button.removeAttribute("aria-busy");
        button.textContent = "Backup";
'''
new_loading_cleanup = '''        button.classList.remove("is-loading");
        button.removeAttribute("aria-busy");
        button.removeAttribute("aria-label");
        button.textContent = "Backup";
'''
if old_loading_cleanup not in app_text:
    raise SystemExit("backup loading cleanup block not found")
app_text = app_text.replace(old_loading_cleanup, new_loading_cleanup, 1)
app.write_text(app_text)


test_text = browser_test.read_text()
old_test = '''def test_backup_button_shows_preparing_state_until_archive_is_ready(page: Page, studio_url: str) -> None:
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
'''
new_test = '''def test_backup_button_shows_preparing_state_until_archive_is_ready(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)
    page.locator("#homeView").evaluate("element => { element.hidden = true; }")
    page.locator("#workspaceView").evaluate("element => { element.hidden = false; }")
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
        }"""
    )

    toolbar_styles = page.locator(
        '#saveStatus, #analyzeButton, #validateButton, #backupProjectButton'
    ).evaluate_all(
        """elements => elements.map(element => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return {
            height: Math.round(rect.height),
            background: style.backgroundColor,
            border: style.borderColor,
            radius: style.borderRadius,
            fontSize: style.fontSize,
            fontWeight: style.fontWeight,
          };
        })"""
    )
    assert {item["height"] for item in toolbar_styles} == {38}
    assert len({item["background"] for item in toolbar_styles}) == 1
    assert len({item["border"] for item in toolbar_styles}) == 1
    assert len({item["radius"] for item in toolbar_styles}) == 1
    assert len({item["fontSize"] for item in toolbar_styles}) == 1
    assert len({item["fontWeight"] for item in toolbar_styles}) == 1

    button = page.locator('#backupProjectButton')
    idle_geometry = button.evaluate(
        "element => ({ width: Math.round(element.getBoundingClientRect().width), height: Math.round(element.getBoundingClientRect().height) })"
    )
    expect(button).to_have_text('Backup')
    button.evaluate("element => element.click()")

    expect(button).to_have_text('Preparing…')
    expect(button).to_be_disabled()
    expect(button).to_have_attribute('aria-busy', 'true')
    expect(button).to_have_attribute('aria-label', 'Preparing project backup')
    assert button.evaluate("element => element.classList.contains('is-loading')")
    loading_geometry = button.evaluate(
        "element => ({ width: Math.round(element.getBoundingClientRect().width), height: Math.round(element.getBoundingClientRect().height) })"
    )
    assert loading_geometry == idle_geometry
    assert button.evaluate("element => element.scrollWidth <= element.clientWidth + 1")

    page.evaluate('window.__resolveBackup()')
    page.wait_for_function('window.__backupDownloadName !== null')
    assert page.evaluate('window.__backupDownloadName') == 'Backup fixture - backup.acstudio.zip'
    expect(button).to_have_text('Backup')
    expect(button).to_be_enabled()
    assert button.evaluate("element => element.getAttribute('aria-busy')") is None
    assert button.evaluate("element => element.getAttribute('aria-label')") is None
    assert not button.evaluate("element => element.classList.contains('is-loading')")
    finished_geometry = button.evaluate(
        "element => ({ width: Math.round(element.getBoundingClientRect().width), height: Math.round(element.getBoundingClientRect().height) })"
    )
    assert finished_geometry == idle_geometry
'''
if old_test not in test_text:
    raise SystemExit("backup browser regression not found")
test_text = test_text.replace(old_test, new_test, 1)
browser_test.write_text(test_text)
