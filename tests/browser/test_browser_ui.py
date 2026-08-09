from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _open(page: Page, studio_url: str) -> None:
    page.goto(studio_url, wait_until="networkidle")
    expect(page).to_have_title(re.compile("Accessible Caption Studio"))
    expect(page.locator("#projectBrowserControls")).to_be_attached()


def test_home_desktop_controls_and_no_horizontal_overflow(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)

    expect(page.get_by_role("heading", name="Turn a video into captions people can actually use.")).to_be_visible()
    expect(page.get_by_label("Search projects")).to_be_visible()
    expect(page.locator("#projectTypeFilter")).to_be_visible()
    expect(page.get_by_label("Sort")).to_be_visible()
    expect(page.get_by_label("Project view")).to_be_visible()
    expect(page.get_by_role("button", name="Restore backup")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_home_mobile_reflows_without_page_overflow(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _open(page, studio_url)

    expect(page.get_by_role("button", name="Create captions")).to_be_visible()
    expect(page.get_by_label("Search projects")).to_be_visible()
    expect(page.get_by_label("Project view")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    controls_width = page.locator("#projectBrowserControls").evaluate("element => element.getBoundingClientRect().width")
    assert controls_width <= 390


def test_long_upload_filename_wraps_without_losing_full_name(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 760, "height": 800})
    _open(page, studio_url)
    filename = ("very-long-tiktok-captioned-video-name-" * 7) + ".mp4"

    page.locator("#mediaInput").set_input_files(
        {"name": filename, "mimeType": "video/mp4", "buffer": b"not-submitted"}
    )

    chosen_name = page.locator("#dropZone strong")
    expect(chosen_name).to_have_text(filename)
    assert page.locator("#dropZone").evaluate("element => element.scrollWidth <= element.clientWidth + 1")


def test_thumbnail_project_card_keeps_a_readable_text_column(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)

    page.locator("#projectList").evaluate(
        """list => {
          const card = document.createElement('article');
          card.id = 'thumbnail-layout-regression-card';
          card.className = 'project-card';
          card.innerHTML = `
            <button class="project-open" type="button">
              <img class="project-thumbnail" alt="" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">
              <span class="project-type">▶</span>
              <strong>v24044gl0000d8bpaa7og65o2to74ma0-captioned-v24044gl0000d8bpaa7og65o2to74ma0</strong>
              <span>23 captions · 2 hours ago</span>
            </button>
            <div class="project-card-actions"><button class="project-action" type="button">Duplicate</button></div>`;
          list.append(card);
        }"""
    )

    card = page.locator("#thumbnail-layout-regression-card")
    type_icon = card.locator(".project-type")
    title = card.locator("strong")
    expect(type_icon).to_be_hidden()
    assert title.evaluate("element => element.getBoundingClientRect().width") >= 120
    assert card.evaluate("element => element.scrollWidth <= element.clientWidth + 1")


def test_basic_accessibility_structure_and_settings_focus(page: Page, studio_url: str) -> None:
    _open(page, studio_url)

    duplicate_ids = page.evaluate(
        """() => {
          const ids = [...document.querySelectorAll('[id]')].map((element) => element.id);
          return ids.filter((id, index) => ids.indexOf(id) !== index);
        }"""
    )
    assert duplicate_ids == []

    unnamed_buttons = page.locator("button").evaluate_all(
        """buttons => buttons.filter((button) => {
          const text = button.textContent.trim();
          const aria = button.getAttribute('aria-label');
          const labelledBy = button.getAttribute('aria-labelledby');
          return !text && !aria && !labelledBy;
        }).map((button) => button.id || button.outerHTML)"""
    )
    assert unnamed_buttons == []

    page.get_by_role("button", name="Settings").click()
    settings = page.locator("#settingsDialog")
    expect(settings).to_be_visible()
    assert page.evaluate("document.activeElement?.closest('#settingsDialog') !== null")
    page.keyboard.press("Escape")
    expect(settings).to_be_hidden()


def test_keyboard_skip_link_reaches_main_content(page: Page, studio_url: str) -> None:
    _open(page, studio_url)
    page.keyboard.press("Tab")
    skip_link = page.get_by_role("link", name="Skip to main content")
    expect(skip_link).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#main")).to_be_focused()


def test_project_view_mode_persists_between_visits(page: Page, studio_url: str) -> None:
    _open(page, studio_url)

    view = page.get_by_label("Project view")
    expect(view).to_have_value("default")
    view.select_option("compact")
    expect(page.locator("#projectList")).to_have_class(re.compile(r"\bproject-grid-compact\b"))

    page.reload(wait_until="networkidle")
    expect(page.locator("#projectBrowserControls")).to_be_attached()
    expect(page.get_by_label("Project view")).to_have_value("compact")
    expect(page.locator("#projectList")).to_have_class(re.compile(r"\bproject-grid-compact\b"))

    page.get_by_label("Project view").select_option("default")
    expect(page.locator("#projectList")).not_to_have_class(re.compile(r"\bproject-grid-compact\b"))
