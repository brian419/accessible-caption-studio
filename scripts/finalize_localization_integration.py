from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, found {count}: {old[:120]!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8")


# Scope the browser test to the new-project controls. There are intentionally two
# "Spoken language" controls because project preferences use the same terminology.
replace_once(
    "tests/browser/test_browser_ui.py",
    '''def test_localization_controls_distinguish_spoken_and_caption_languages(page: Page, studio_url: str) -> None:\n    _open(page, studio_url)\n    expect(page.get_by_label("Spoken language")).to_be_visible()\n    expect(page.get_by_label("Add translated caption track")).to_be_visible()\n    page.get_by_label("Spoken language").select_option("es")\n    page.get_by_label("Add translated caption track").select_option("fr")\n''',
    '''def test_localization_controls_distinguish_spoken_and_caption_languages(page: Page, studio_url: str) -> None:\n    _open(page, studio_url)\n    spoken = page.locator("#defaultTranscriptionLanguage")\n    target = page.locator("#defaultTargetCaptionLanguage")\n    expect(spoken).to_be_visible()\n    expect(target).to_be_visible()\n    spoken.select_option("es")\n    target.select_option("fr")\n''',
)

# Translation-specific QA must be recomputed whenever a translated track is edited or
# explicitly validated, and original-track edits must mark translations stale.
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''from .localization import create_translation_track, normalize_target_languages\n''',
    '''from .localization import (\n    create_translation_track,\n    normalize_target_languages,\n    translation_findings,\n)\n''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        if request.cues is not None:\n            project.cues = request.cues\n            project.findings = validate_cues(\n                project.cues, project.media.duration if project.media else None\n            )\n''',
    '''        if request.cues is not None:\n            project.cues = request.cues\n            duration = project.media.duration if project.media else None\n            active_track = project.active_caption_track()\n            if active_track.kind == "translation":\n                source = project.original_caption_track()\n                project.findings = translation_findings(\n                    source.cues,\n                    project.cues,\n                    source.language,\n                    active_track.language,\n                    duration,\n                )\n            else:\n                project.findings = validate_cues(project.cues, duration)\n                project.mark_translation_tracks_stale()\n''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    def apply_speaker_proposal(project_id: str, job_id: str) -> Project:\n        project = _get_project(store, project_id)\n        try:\n''',
    '''    def apply_speaker_proposal(project_id: str, job_id: str) -> Project:\n        project = _get_project(store, project_id)\n        _require_original_caption_track(project)\n        try:\n''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        project.findings = [\n            ValidationFinding.model_validate(item) for item in result["findings"]\n        ]\n        evidence_name = result.get("evidence_temp")\n''',
    '''        project.findings = [\n            ValidationFinding.model_validate(item) for item in result["findings"]\n        ]\n        project.mark_translation_tracks_stale()\n        evidence_name = result.get("evidence_temp")\n''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    def apply_transcript_proposal(project_id: str, job_id: str) -> Project:\n        project = _get_project(store, project_id)\n        try:\n''',
    '''    def apply_transcript_proposal(project_id: str, job_id: str) -> Project:\n        project = _get_project(store, project_id)\n        _require_original_caption_track(project)\n        try:\n''',
)
# The transcript proposal has a second identical findings block. Replace the occurrence
# nearest the transcript apply route by splitting around that route.
webapp_path = ROOT / "src/accessible_caption_studio/webapp.py"
webapp = webapp_path.read_text(encoding="utf-8")
route_marker = '    def apply_transcript_proposal(project_id: str, job_id: str) -> Project:\n'
head, tail = webapp.split(route_marker, 1)
old = '''        project.findings = [\n            ValidationFinding.model_validate(item) for item in result["findings"]\n        ]\n        project.face_tracks = result.get("face_tracks", [])\n'''
new = '''        project.findings = [\n            ValidationFinding.model_validate(item) for item in result["findings"]\n        ]\n        project.mark_translation_tracks_stale()\n        project.face_tracks = result.get("face_tracks", [])\n'''
if tail.count(old) != 1:
    raise RuntimeError(f"Expected transcript proposal findings anchor once, found {tail.count(old)}")
tail = tail.replace(old, new, 1)
webapp_path.write_text(head + route_marker + tail, encoding="utf-8")

replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    @app.post("/api/projects/{project_id}/validate")\n    def validate_project(project_id: str) -> Project:\n        project = _get_project(store, project_id)\n        project.findings = validate_cues(\n            project.cues, project.media.duration if project.media else None\n        )\n        return store.save(project)\n''',
    '''    @app.post("/api/projects/{project_id}/validate")\n    def validate_project(project_id: str) -> Project:\n        project = _get_project(store, project_id)\n        duration = project.media.duration if project.media else None\n        active_track = project.active_caption_track()\n        if active_track.kind == "translation":\n            source = project.original_caption_track()\n            project.findings = translation_findings(\n                source.cues,\n                project.cues,\n                source.language,\n                active_track.language,\n                duration,\n            )\n        else:\n            project.findings = validate_cues(project.cues, duration)\n        return store.save(project)\n''',
)

# Strengthen the API regression: explicit validation of a translated track must retain
# localization QA, not downgrade to generic caption checks only.
test_path = ROOT / "tests/test_localization.py"
tests = test_path.read_text(encoding="utf-8")
anchor = '''def test_translation_job_creates_track_without_real_model(monkeypatch, tmp_path: Path) -> None:\n'''
qa_test = '''def test_validate_endpoint_recomputes_translation_qa(tmp_path: Path) -> None:\n    app = create_app(tmp_path / "storage")\n    store = app.state.store\n    project = store.create("Translation validation")\n    project.media = MediaAsset(\n        filename="audio.wav",\n        stored_name="audio.wav",\n        duration=5,\n        has_video=False,\n    )\n    project.cues = [CaptionCue(start=0, end=2, text="Alice paid 42 dollars")]\n    store.save(project)\n    project = store.get(project.id)\n    original = project.original_caption_track()\n    translated = CaptionTrack(\n        language="es",\n        kind="translation",\n        source_track_id=original.id,\n        source_language="en",\n        cues=[CaptionCue(start=0, end=2, text="Alicia pagó 24 dólares")],\n    )\n    project.caption_tracks.append(translated)\n    project.activate_caption_track(translated.id)\n    store.save(project)\n\n    with TestClient(app) as client:\n        response = client.post(f"/api/projects/{project.id}/validate")\n\n    assert response.status_code == 200\n    codes = {item["code"] for item in response.json()["findings"]}\n    assert "translation_number_changed" in codes\n    assert "translation_name_changed" in codes\n\n\n'''
if anchor not in tests:
    raise RuntimeError("Could not find translation-job test anchor")
test_path.write_text(tests.replace(anchor, qa_test + anchor, 1), encoding="utf-8")

# Clean up this one-time integration script/workflow/trigger in the same commit.
for temporary in (
    ROOT / "scripts" / "finalize_localization_integration.py",
    ROOT / ".github" / "workflows" / "finalize-localization-integration.yml",
    ROOT / ".github" / "localization-finalize-trigger.txt",
):
    temporary.unlink(missing_ok=True)

print("Finalized localization integration safeguards and browser test")
