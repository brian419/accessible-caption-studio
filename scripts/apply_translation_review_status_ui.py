from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "src/accessible_caption_studio/web/final_batch.js"
TEST = ROOT / "tests/browser/test_browser_ui.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} match, found {count}")
    return text.replace(old, new, 1)


final = FINAL.read_text()
final = replace_once(
    final,
    '      needs_update: "Source changed · review again",\n',
    '      needs_update: "Needs review",\n',
    "needs-update status label",
)
final = replace_once(
    final,
    '''  function installCaptionLocalizationDialog() {\n''',
    '''  function captionTrackStatusDescription(track) {\n    if (!track || track.kind !== "translation") return "";\n    return ({\n      reviewed: "This translation has been marked reviewed.",\n      in_review: "Review this translation, then mark it reviewed when it is ready.",\n      needs_update: "The Original captions changed after this translation was created. Regenerate it before marking it reviewed.",\n      unreviewed: "Review this translation before marking it reviewed.",\n    })[track.review_state] || "Review this translation before marking it reviewed.";\n  }\n\n  function installCaptionLocalizationDialog() {\n''',
    "status description helper",
)
final = replace_once(
    final,
    '''        <div class="caption-track-current">\n          <label class="caption-track-field" for="captionTrackSelect">Caption track\n            <select id="captionTrackSelect" aria-label="Caption track"></select>\n          </label>\n          <span id="captionTrackStatus" class="caption-track-status"></span>\n        </div>\n''',
    '''        <div class="caption-track-current">\n          <label class="caption-track-field" for="captionTrackSelect">Caption track\n            <select id="captionTrackSelect" aria-label="Caption track"></select>\n          </label>\n          <div id="captionTrackReviewStatus" class="caption-track-review-status" role="status" aria-live="polite">\n            <span class="caption-track-review-status-label">Review status</span>\n            <strong id="captionTrackStatus" class="caption-track-status"></strong>\n            <span id="captionTrackStatusDetail" class="caption-track-status-detail"></span>\n          </div>\n        </div>\n''',
    "current-track status markup",
)
final = replace_once(
    final,
    '''    const status = body.querySelector("#captionTrackStatus");\n    status.textContent = captionTrackStatusLabel(active);\n    status.classList.toggle("needs-update", active?.review_state === "needs_update");\n''',
    '''    const reviewStatus = body.querySelector("#captionTrackReviewStatus");\n    const status = body.querySelector("#captionTrackStatus");\n    const statusDetail = body.querySelector("#captionTrackStatusDetail");\n    reviewStatus.hidden = !translated;\n    status.textContent = captionTrackStatusLabel(active);\n    statusDetail.textContent = captionTrackStatusDescription(active);\n    status.classList.toggle("needs-update", active?.review_state === "needs_update");\n''',
    "status rendering",
)
final = replace_once(
    final,
    '      .caption-localization-dialog .caption-track-current { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.65rem; align-items:end; }\n',
    '      .caption-localization-dialog .caption-track-current { display:grid; grid-template-columns:1fr; gap:.7rem; align-items:stretch; }\n',
    "modal current-track layout",
)
final = replace_once(
    final,
    '''      .caption-localization-dialog .caption-track-status { display:inline-flex; align-items:center; justify-self:start; min-height:0; padding:0; border:0; border-radius:0; background:transparent; color:var(--muted); font-size:.7rem; font-weight:750; line-height:1.35; white-space:normal; }\n      .caption-localization-dialog .caption-track-status.needs-update { color:var(--muted); border-color:transparent; background:transparent; }\n''',
    '''      .caption-localization-dialog .caption-track-review-status { display:grid; gap:.12rem; min-width:0; padding-top:.05rem; }\n      .caption-localization-dialog .caption-track-review-status[hidden] { display:none !important; }\n      .caption-localization-dialog .caption-track-review-status-label { color:var(--muted); font-size:.68rem; font-weight:800; line-height:1.35; }\n      .caption-localization-dialog .caption-track-status { display:block; min-height:0; padding:0; border:0; border-radius:0; background:transparent; color:var(--ink); font-size:.76rem; font-weight:800; line-height:1.35; white-space:normal; }\n      .caption-localization-dialog .caption-track-status.needs-update { color:var(--ink); border-color:transparent; background:transparent; }\n      .caption-localization-dialog .caption-track-status-detail { display:block; max-width:560px; color:var(--muted); font-size:.72rem; font-weight:500; line-height:1.45; }\n''',
    "modal review-status styling",
)
FINAL.write_text(final)


test = TEST.read_text()
test = replace_once(
    test,
    "            active_caption_track_id: 'track-original',\n            caption_tracks: [\n              { id: 'track-original', kind: 'original', language: 'en', review_state: 'reviewed', cues: [{ id: 'cue-1', start: 0, end: 1, text: 'Hello' }] },\n              { id: 'track-ko', kind: 'translation', language: 'ko', review_state: 'needs_update', cues: [{ id: 'cue-1-ko', start: 0, end: 1, text: '안녕하세요' }] },\n            ],\n            cues: [{ id: 'cue-1', start: 0, end: 1, text: 'Hello' }],\n",
    "            active_caption_track_id: 'track-ko',\n            caption_tracks: [\n              { id: 'track-original', kind: 'original', language: 'en', review_state: 'reviewed', cues: [{ id: 'cue-1', start: 0, end: 1, text: 'Hello' }] },\n              { id: 'track-ko', kind: 'translation', language: 'ko', review_state: 'needs_update', cues: [{ id: 'cue-1-ko', start: 0, end: 1, text: '안녕하세요' }] },\n            ],\n            cues: [{ id: 'cue-1-ko', start: 0, end: 1, text: '안녕하세요' }],\n",
    "localization browser fixture active track",
)
test = replace_once(
    test,
    '''    status_style = dialog.locator("#captionTrackStatus").evaluate(\n''',
    '''    expect(dialog.get_by_text("Review status", exact=True)).to_be_visible()\n    expect(dialog.locator("#captionTrackStatus")).to_have_text("Needs review")\n    expect(dialog.locator("#captionTrackStatusDetail")).to_have_text(\n        "The Original captions changed after this translation was created. Regenerate it before marking it reviewed."\n    )\n    status_style = dialog.locator("#captionTrackStatus").evaluate(\n''',
    "review-status browser assertions",
)
test = replace_once(
    test,
    '    expect(dialog.get_by_label("Caption track", exact=True)).to_have_value("track-original")\n',
    '    expect(dialog.get_by_label("Caption track", exact=True)).to_have_value("track-ko")\n',
    "active track browser assertion",
)
TEST.write_text(test)
