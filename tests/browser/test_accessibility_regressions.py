import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _open(page: Page, studio_url: str) -> None:
    page.goto(studio_url, wait_until="networkidle")
    expect(page).to_have_title(re.compile("Accessible Caption Studio"))


@pytest.mark.parametrize("width", [640, 320])
def test_zoom_equivalent_reflow_has_no_page_overflow(
    page: Page, studio_url: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    _open(page, studio_url)
    expect(page.get_by_role("button", name="Create captions")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_reduced_motion_removes_meaningful_ui_transitions(
    page: Page, studio_url: str
) -> None:
    page.emulate_media(reduced_motion="reduce")
    _open(page, studio_url)
    page.evaluate("toast('Reduced motion test')")
    notification = page.locator(".notification").last
    expect(notification).to_be_visible()
    seconds = notification.evaluate(
        "element => parseFloat(getComputedStyle(element).transitionDuration) || 0"
    )
    assert seconds <= 0.001


def test_forced_colors_keeps_primary_controls_visible(page: Page, studio_url: str) -> None:
    page.emulate_media(forced_colors="active")
    _open(page, studio_url)
    expect(page.get_by_role("button", name="Settings")).to_be_visible()
    expect(page.get_by_role("button", name="Create captions")).to_be_visible()
    page.get_by_role("button", name="Settings").focus()
    expect(page.get_by_role("button", name="Settings")).to_be_focused()
