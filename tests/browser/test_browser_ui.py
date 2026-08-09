from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _open(page: Page, studio_url: str) -> None:
    page.goto(studio_url, wait_until="networkidle")
    expect(page).to_have_title(re.compile("Accessible Caption Studio"))
    expect(page.locator("#projectBrowserControls")).to_be_attached()


def _inject_project_card(page: Page, card_id: str) -> None:
    page.locator("#projectList").evaluate(
        """(list, cardId) => {
          const card = document.createElement('article');
          card.id = cardId;
          card.className = 'project-card';
          card.innerHTML = `
            <button class="project-open" type="button">
              <img class="project-thumbnail" alt="" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">
              <span class="project-type">▶</span>
              <strong>v24044gl0000d8bpaa7og65o2to74ma0-captioned-v24044gl0000d8bpaa7og65o2to74ma0</strong>
              <span>23 captions · 2 hours ago</span>
            </button>
            <div class="button-row project-card-actions">
              <button class="project-action" type="button">Duplicate</button>
              <button class="project-action" type="button">Delete</button>
            </div>
            <button class="project-favorite" type="button" aria-label="Add project to favorites">☆</button>`;
          list.append(card);
        }""",
        card_id,
    )


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


def test_card_view_uses_full_width_media_header_and_readable_title(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)
    page.get_by_label("Project view").select_option("default")
    _inject_project_card(page, "card-layout-regression")

    card = page.locator("#card-layout-regression")
    thumbnail = card.locator(".project-thumbnail")
    title = card.locator("strong")
    favorite = card.locator(".project-favorite")
    expect(card.locator(".project-type")).to_be_hidden()

    geometry = card.evaluate(
        """card => {
          const thumb = card.querySelector('.project-thumbnail').getBoundingClientRect();
          const title = card.querySelector('strong').getBoundingClientRect();
          const favorite = card.querySelector('.project-favorite').getBoundingClientRect();
          const box = card.getBoundingClientRect();
          return {
            cardWidth: box.width,
            thumbWidth: thumb.width,
            thumbBottom: thumb.bottom,
            titleTop: title.top,
            titleWidth: title.width,
            favoriteTop: favorite.top,
            favoriteBottom: favorite.bottom,
          };
        }"""
    )
    assert geometry["thumbWidth"] >= geometry["cardWidth"] - 8
    assert geometry["titleTop"] >= geometry["thumbBottom"] - 1
    assert geometry["titleWidth"] >= geometry["cardWidth"] - 8
    assert geometry["favoriteTop"] < geometry["thumbBottom"]
    assert geometry["favoriteBottom"] <= geometry["thumbBottom"]
    assert card.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
    expect(thumbnail).to_be_visible()
    expect(title).to_be_visible()
    expect(favorite).to_be_visible()


def test_compact_view_keeps_copy_actions_and_favorite_separate(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)
    page.get_by_label("Project view").select_option("compact")
    _inject_project_card(page, "compact-layout-regression")

    card = page.locator("#compact-layout-regression")
    geometry = card.evaluate(
        """card => {
          const title = card.querySelector('strong').getBoundingClientRect();
          const actions = card.querySelector('.project-card-actions').getBoundingClientRect();
          const favorite = card.querySelector('.project-favorite').getBoundingClientRect();
          const style = getComputedStyle(card.querySelector('.project-favorite'));
          return {
            titleWidth: title.width,
            actionsRight: actions.right,
            favoriteLeft: favorite.left,
            favoritePosition: style.position,
          };
        }"""
    )
    assert geometry["titleWidth"] >= 300
    assert geometry["actionsRight"] <= geometry["favoriteLeft"]
    assert geometry["favoritePosition"] == "static"
    assert card.evaluate("element => element.scrollWidth <= element.clientWidth + 1")


def test_card_view_uses_uniform_heights_and_preserves_filename_extension(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    long_name = "portrait-recording-" + ("very-long-segment-" * 6) + ".mp4"
    projects = [
        {
            "id": "uniform-long",
            "name": long_name,
            "cues": [],
            "media": {"has_video": False},
            "updated_at": "2026-08-09T07:00:00Z",
            "is_favorite": False,
        },
        {
            "id": "uniform-short",
            "name": "short-project.mov",
            "cues": [],
            "media": {"has_video": False},
            "updated_at": "2026-08-09T06:00:00Z",
            "is_favorite": False,
        },
    ]
    page.route(
        "**/api/projects",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(projects)),
    )
    _open(page, studio_url)
    page.get_by_label("Project view").select_option("default")

    cards = page.locator("#projectList .project-card")
    expect(cards).to_have_count(2)
    heights = cards.evaluate_all("items => items.map(item => Math.round(item.getBoundingClientRect().height))")
    assert len(set(heights)) == 1
    assert heights[0] == 272

    long_title = page.locator('[data-project-id="uniform-long"] .project-open > strong')
    displayed = long_title.inner_text()
    assert displayed.endswith(".mp4")
    assert displayed != long_name
    assert len(displayed) < len(long_name)
    expect(long_title).to_have_attribute("title", long_name)

    page.get_by_label("Project view").select_option("compact")
    expect(long_title).to_have_text(long_name)


def test_favorite_controls_share_one_centered_surface(page: Page, studio_url: str) -> None:
    projects = [
        {
            "id": "favorite-style-project",
            "name": "favorite-style-project.mp4",
            "cues": [],
            "media": {"has_video": False},
            "updated_at": "2026-08-09T08:00:00Z",
            "is_favorite": False,
        }
    ]
    page.route(
        "**/api/projects",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(projects)),
    )
    _open(page, studio_url)
    page.locator("body").evaluate(
        """body => {
          const fixture = document.createElement('div');
          fixture.id = 'font-option-style-fixture';
          fixture.className = 'caption-font-option';
          fixture.innerHTML = `
            <button class="caption-font-option-main" type="button"><span class="caption-font-option-name">Example Font</span></button>
            <button id="font-favorite-style-fixture" class="caption-font-favorite" type="button" aria-label="Favorite font" aria-pressed="false">☆</button>`;
          fixture.style.width = '414px';
          document.body.append(fixture);
        }"""
    )

    project = page.locator('[data-project-id="favorite-style-project"] .project-favorite')
    font = page.locator("#font-favorite-style-fixture")

    def favorite_surface(locator):
        return locator.evaluate(
            """element => {
              const style = getComputedStyle(element);
              const icon = getComputedStyle(element, '::before');
              const rect = element.getBoundingClientRect();
              return {
                background: style.backgroundColor,
                border: style.borderColor,
                width: Math.round(rect.width),
                height: Math.round(rect.height),
                display: style.display,
                alignItems: style.alignItems,
                justifyItems: style.justifyItems,
                iconWidth: icon.width,
                iconHeight: icon.height,
                iconTransform: icon.transform,
                mask: icon.maskImage || icon.webkitMaskImage,
              };
            }"""
        )

    card_surface = favorite_surface(project)
    font_surface = favorite_surface(font)
    assert card_surface["background"] == font_surface["background"]
    assert card_surface["border"] == font_surface["border"]
    assert card_surface["width"] == font_surface["width"] == 34
    assert card_surface["height"] == font_surface["height"] == 34
    assert card_surface["iconWidth"] == font_surface["iconWidth"] == "18px"
    assert card_surface["iconHeight"] == font_surface["iconHeight"] == "18px"
    assert card_surface["iconTransform"] == font_surface["iconTransform"]
    assert card_surface["mask"] == font_surface["mask"]
    assert "data:image/svg+xml;base64" in card_surface["mask"]

    font_geometry = page.locator("#font-option-style-fixture").evaluate(
        """row => {
          const button = row.querySelector('.caption-font-favorite');
          const rowRect = row.getBoundingClientRect();
          const buttonRect = button.getBoundingClientRect();
          return {
            topInset: Math.round(buttonRect.top - rowRect.top),
            bottomInset: Math.round(rowRect.bottom - buttonRect.bottom),
            rightInset: Math.round(rowRect.right - buttonRect.right),
            rowHeight: Math.round(rowRect.height),
            buttonHeight: Math.round(buttonRect.height),
          };
        }"""
    )
    assert font_geometry["rowHeight"] == 60
    assert font_geometry["buttonHeight"] == 34
    assert abs(font_geometry["topInset"] - font_geometry["bottomInset"]) <= 1
    # Includes the font row's 1px outer border plus 8px inner spacing.
    assert font_geometry["rightInset"] == 9

    page.get_by_label("Project view").select_option("compact")
    compact_surface = favorite_surface(project)
    assert compact_surface["background"] == card_surface["background"]
    assert compact_surface["border"] == card_surface["border"]
    assert compact_surface["width"] == card_surface["width"]
    assert compact_surface["height"] == card_surface["height"]
    assert compact_surface["iconTransform"] == card_surface["iconTransform"]

    project.evaluate("element => element.setAttribute('aria-pressed', 'true')")
    font.evaluate("element => element.setAttribute('aria-pressed', 'true')")
    active_project = favorite_surface(project)
    active_font = favorite_surface(font)
    assert active_project["background"] == active_font["background"]
    assert active_project["border"] == active_font["border"]
    assert active_project["mask"] == active_font["mask"]
    assert active_project["mask"] != card_surface["mask"]


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

def test_localization_controls_distinguish_spoken_and_caption_languages(page: Page, studio_url: str) -> None:
    _open(page, studio_url)
    page.locator("#captioningOptions > summary").click()
    spoken = page.locator("#defaultTranscriptionLanguage")
    target = page.locator("#defaultTargetCaptionLanguage")
    expect(spoken).to_be_visible()
    expect(target).to_be_visible()
    spoken.select_option("es")
    target.select_option("fr")
    expect(page.locator("#defaultCaptionLanguageChips")).to_contain_text("French")
    expect(page.locator("#captioningOptionsSummary")).to_contain_text("Spanish")
    expect(page.locator("#captioningOptionsSummary")).to_contain_text("+1 translation")



def test_caption_localization_is_modal_and_preserves_timeline_height(page: Page, studio_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    _open(page, studio_url)

    source = page.evaluate("() => fetch('/final-batch.js').then((response) => response.text())")
    assert 'heading.after(bar);' not in source
    assert 'installCaptionLocalizationDialog' in source
    assert 'installCaptionLocalizationAction' in source

    page.locator("#homeView").evaluate("element => { element.hidden = true; }")
    page.locator("#workspaceView").evaluate("element => { element.hidden = false; }")
    before = page.locator(".column-labels").evaluate("element => Math.round(element.getBoundingClientRect().top)")
    assert page.locator("#captionTrackBar").count() == 0

    page.evaluate(
        """() => {
          state.project = {
            id: 'modal-layout-fixture',
            name: 'Localization layout fixture',
            active_caption_track_id: 'track-original',
            caption_tracks: [
              { id: 'track-original', kind: 'original', language: 'en', review_state: 'reviewed', cues: [{ id: 'cue-1', start: 0, end: 1, text: 'Hello' }] },
              { id: 'track-ko', kind: 'translation', language: 'ko', review_state: 'needs_update', cues: [{ id: 'cue-1-ko', start: 0, end: 1, text: '안녕하세요' }] },
            ],
            cues: [{ id: 'cue-1', start: 0, end: 1, text: 'Hello' }],
          };
          document.querySelector('#captionLocalizationButton').click();
        }"""
    )

    dialog = page.locator("#captionLocalizationDialog")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("heading", name="Languages & translations")).to_be_visible()
    expect(dialog.get_by_label("Caption track", exact=True)).to_have_value("track-original")
    expect(dialog.get_by_label("Translated caption language")).to_be_visible()
    assert page.locator("#captionTrackBar").count() == 0
    after = page.locator(".column-labels").evaluate("element => Math.round(element.getBoundingClientRect().top)")
    assert abs(after - before) <= 1

    page.set_viewport_size({"width": 390, "height": 844})
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
    assert dialog.locator("#captionLocalizationBody").evaluate("element => element.scrollWidth <= element.clientWidth + 1")

