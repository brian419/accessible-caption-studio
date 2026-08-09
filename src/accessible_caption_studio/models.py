from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceType(StrEnum):
    TRANSCRIPTION = "transcription"
    IMPORTED = "imported"
    MANUAL = "manual"
    SOUND = "sound"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaAsset(BaseModel):
    filename: str
    stored_name: str
    content_type: str | None = None
    duration: float = Field(ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    has_video: bool = False
    has_audio: bool = True
    source_url: str | None = None
    size_bytes: int = Field(default=0, ge=0)


class WordToken(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    transcription_source: str = Field(default="primary", pattern="^(primary|recovery)$")
    speaker: str | None = None
    speaker_confidence: float | None = Field(default=None, ge=0, le=1)
    speaker_method: str | None = Field(
        default=None,
        pattern="^(voice_only|voice_face|face_only|uncertain)$",
    )
    face_track_id: str | None = None

    @model_validator(mode="after")
    def valid_interval(self) -> WordToken:
        if self.end < self.start:
            raise ValueError("word end must not precede start")
        return self


class SpeakerTurn(BaseModel):
    speaker: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    audio_confidence: float | None = Field(default=None, ge=0, le=1)
    visual_confidence: float | None = Field(default=None, ge=0, le=1)
    face_track_id: str | None = None
    method: str = Field(
        default="audio",
        pattern=(
            "^(audio|audio_visual|visual_fallback|voice_only|voice_face|face_only|uncertain)$"
        ),
    )


class FaceTrackSummary(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    speaker: str | None = None
    identity_cluster_id: str | None = None
    face_match_confidence: float | None = Field(default=None, ge=0, le=1)
    max_active_confidence: float = Field(default=0, ge=0, le=1)


class FusionSummary(BaseModel):
    voice_cluster_count: int = Field(default=0, ge=0, le=8)
    face_identity_count: int = Field(default=0, ge=0)
    final_speaker_count: int = Field(default=0, ge=0, le=8)
    association_confidence: float | None = Field(default=None, ge=0, le=1)


class SoundEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    label: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class CaptionCue(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    speaker: str | None = None
    source: SourceType = SourceType.MANUAL
    confidence: float | None = Field(default=None, ge=0, le=1)
    sound_event_id: str | None = None
    overlap_group_id: str | None = None
    position_override: Literal["top", "middle", "bottom"] | None = None
    alignment_override: Literal["left", "center", "right"] | None = None
    vertical_margin_percent_override: float | None = Field(default=None, ge=2, le=25)

    @field_validator("text")
    @classmethod
    def text_required(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("caption text is required")
        return value


class CaptionStyle(BaseModel):
    preset: Literal["classic", "high_contrast", "clean", "broadcast", "custom"] = "classic"
    font_family: str = "Arial"
    font_style: str | None = None
    bold: bool = True
    font_size_percent: float = Field(default=7.5, ge=4, le=12)
    max_width_percent: float = Field(default=88, ge=40, le=96)
    text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_opacity: float = Field(default=0.78, ge=0, le=1)
    outline_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_size_percent: float = Field(default=0.16, ge=0, le=0.6)
    shadow_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    shadow_size_percent: float = Field(default=0.18, ge=0, le=0.8)
    padding_percent: float = Field(default=1.0, ge=0.2, le=3)
    line_spacing_percent: float = Field(default=0.7, ge=0, le=3)
    position: Literal["top", "middle", "bottom"] = "bottom"
    alignment: Literal["left", "center", "right"] = "center"
    vertical_margin_percent: float = Field(default=10, ge=2, le=25)

    @field_validator("font_family", "font_style")
    @classmethod
    def normalize_font_name(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        maximum = 120 if info.field_name == "font_family" else 80
        if not cleaned or len(cleaned) > maximum or any(ord(character) < 32 for character in cleaned):
            raise ValueError(f"{info.field_name.replace('_', ' ')} is invalid")
        return cleaned

    @model_validator(mode="after")
    def synchronize_font_style(self) -> CaptionStyle:
        if not self.font_style:
            self.font_style = "Bold" if self.bold else "Regular"
        normalized = self.font_style.casefold()
        self.bold = any(
            marker in normalized
            for marker in ("bold", "black", "heavy", "demi", "semi")
        )
        return self

    @field_validator(
        "text_color",
        "background_color",
        "outline_color",
        "shadow_color",
    )
    @classmethod
    def normalize_color(cls, value: str) -> str:
        return value.upper()


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationFinding(BaseModel):
    code: str
    message: str
    severity: Severity
    cue_id: str | None = None


class ExportArtifact(BaseModel):
    format: str
    filename: str
    created_at: datetime = Field(default_factory=utc_now)
    size_bytes: int = Field(default=0, ge=0)


class CaptionTrack(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    kind: Literal["original", "translation"] = "original"
    source_track_id: str | None = None
    source_language: str | None = Field(
        default=None, pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$"
    )
    review_state: Literal["unreviewed", "in_review", "reviewed", "needs_update"] = (
        "unreviewed"
    )
    cues: list[CaptionCue] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)
    exports: list[ExportArtifact] = Field(default_factory=list)
    translation_model: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalysisJob(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    project_id: str
    kind: str = "analysis"
    state: JobState = JobState.QUEUED
    stage: str = "Waiting"
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    error_code: str | None = None
    error: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = Field(default=1, ge=1)
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    media: MediaAsset | None = None
    cues: list[CaptionCue] = Field(default_factory=list)
    words: list[WordToken] = Field(default_factory=list)
    speakers: list[SpeakerTurn] = Field(default_factory=list)
    sounds: list[SoundEvent] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)
    exports: list[ExportArtifact] = Field(default_factory=list)
    latest_job_id: str | None = None
    expected_speaker_count: int | None = Field(default=None, ge=1, le=8)
    speaker_names: dict[str, str] = Field(default_factory=dict)
    visual_speaker_status: str = "not_analyzed"
    face_tracks: list[FaceTrackSummary] = Field(default_factory=list)
    speaker_engine: str = "legacy_wavlm"
    fusion_summary: FusionSummary = Field(default_factory=FusionSummary)
    transcription_quality: str = Field(default="accurate", pattern="^(fast|accurate)$")
    transcription_language: str = Field(
        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"
    )
    spoken_language: str = Field(
        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"
    )
    detected_language: str | None = Field(
        default=None, pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$"
    )
    requested_caption_languages: list[str] = Field(default_factory=list)
    caption_tracks: list[CaptionTrack] = Field(default_factory=list)
    active_caption_track_id: str | None = None
    sdh_mode: Literal["off", "conservative", "full"] = "full"
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    is_favorite: bool = False

    @field_validator("requested_caption_languages")
    @classmethod
    def valid_requested_caption_languages(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            code = str(item).strip()
            if code in {"auto", "und"}:
                continue
            if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", code):
                raise ValueError("caption language is invalid")
            if code not in cleaned:
                cleaned.append(code)
        return cleaned

    @model_validator(mode="after")
    def synchronize_caption_track_state(self) -> Project:
        # transcription_language is retained as a compatibility alias for older clients.
        if self.spoken_language == "en" and self.transcription_language != "en":
            self.spoken_language = self.transcription_language
        self.transcription_language = self.spoken_language

        if not self.caption_tracks:
            original_language = self.detected_language or (
                self.spoken_language if self.spoken_language != "auto" else "und"
            )
            self.caption_tracks = [
                CaptionTrack(
                    language=original_language,
                    kind="original",
                    cues=[cue.model_copy(deep=True) for cue in self.cues],
                    findings=[finding.model_copy(deep=True) for finding in self.findings],
                    exports=[artifact.model_copy(deep=True) for artifact in self.exports],
                )
            ]

        ids = {track.id for track in self.caption_tracks}
        if self.active_caption_track_id not in ids:
            original = next(
                (track for track in self.caption_tracks if track.kind == "original"),
                self.caption_tracks[0],
            )
            self.active_caption_track_id = original.id
        self.refresh_caption_track_view()
        return self

    def caption_track(self, track_id: str | None = None) -> CaptionTrack | None:
        wanted = track_id or self.active_caption_track_id
        return next((track for track in self.caption_tracks if track.id == wanted), None)

    def active_caption_track(self) -> CaptionTrack:
        track = self.caption_track()
        if track is None:
            raise ValueError("Project has no active caption track")
        return track

    def original_caption_track(self) -> CaptionTrack:
        track = next(
            (item for item in self.caption_tracks if item.kind == "original"),
            None,
        )
        if track is None:
            raise ValueError("Project has no original caption track")
        return track

    def translation_caption_track(self, language: str) -> CaptionTrack | None:
        return next(
            (
                item
                for item in self.caption_tracks
                if item.kind == "translation" and item.language == language
            ),
            None,
        )

    def refresh_caption_track_view(self) -> None:
        track = self.caption_track()
        if track is None:
            self.cues = []
            self.findings = []
            self.exports = []
            return
        self.cues = [cue.model_copy(deep=True) for cue in track.cues]
        self.findings = [finding.model_copy(deep=True) for finding in track.findings]
        self.exports = [artifact.model_copy(deep=True) for artifact in track.exports]

    def sync_active_caption_track(self) -> None:
        track = self.caption_track()
        if track is None:
            return
        cues = [cue.model_copy(deep=True) for cue in self.cues]
        findings = [finding.model_copy(deep=True) for finding in self.findings]
        exports = [artifact.model_copy(deep=True) for artifact in self.exports]
        if track.cues != cues or track.findings != findings or track.exports != exports:
            track.cues = cues
            track.findings = findings
            track.exports = exports
            track.updated_at = utc_now()

    def activate_caption_track(self, track_id: str) -> CaptionTrack:
        track = self.caption_track(track_id)
        if track is None:
            raise KeyError(track_id)
        self.sync_active_caption_track()
        self.active_caption_track_id = track.id
        self.refresh_caption_track_view()
        return track

    def mark_translation_tracks_stale(self) -> None:
        for track in self.caption_tracks:
            if track.kind == "translation" and track.cues:
                track.review_state = "needs_update"
                track.updated_at = utc_now()

    @field_validator("speaker_names")
    @classmethod
    def valid_speaker_names(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for speaker, name in value.items():
            if not re.fullmatch(r"Speaker [1-8]", speaker):
                raise ValueError("speaker names must use an anonymous Speaker 1–8 key")
            display_name = " ".join(name.split()).strip()[:80]
            if display_name:
                cleaned[speaker] = display_name
        return cleaned

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = " ".join(value.split()).strip()
        if not value:
            raise ValueError("project name is required")
        return value[:120]


class StorageSummary(BaseModel):
    projects_bytes: int
    models_bytes: int
    temporary_bytes: int
    project_count: int


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
