from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
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

    @field_validator("text")
    @classmethod
    def text_required(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("caption text is required")
        return value


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
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")

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
