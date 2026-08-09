from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

CURRENT_PROJECT_SCHEMA_VERSION = 4


def migrate_project_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return a current project payload and whether a migration changed it."""
    data = deepcopy(payload)
    raw_version = data.get("schema_version", 0)
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise ValueError("Project schema version is invalid") from exc

    if version < 0:
        raise ValueError("Project schema version is invalid")
    if version > CURRENT_PROJECT_SCHEMA_VERSION:
        raise ValueError(
            "This project was created by a newer Accessible Caption Studio version"
        )

    changed = False
    while version < CURRENT_PROJECT_SCHEMA_VERSION:
        if version == 0:
            data["schema_version"] = 1
            version = 1
            changed = True
            continue
        if version == 1:
            data.setdefault("is_favorite", False)
            for cue in data.get("cues", []) or []:
                if isinstance(cue, dict):
                    cue.setdefault("position_override", None)
                    cue.setdefault("alignment_override", None)
                    cue.setdefault("vertical_margin_percent_override", None)
            data["schema_version"] = 2
            version = 2
            changed = True
            continue
        if version == 2:
            data.setdefault("transcription_language", "en")
            data.setdefault("sdh_mode", "full")
            data["schema_version"] = 3
            version = 3
            changed = True
            continue
        if version == 3:
            spoken_language = str(data.get("transcription_language") or "en")
            original_language = spoken_language if spoken_language != "auto" else "und"
            track_id = uuid4().hex
            data.setdefault("spoken_language", spoken_language)
            data.setdefault("detected_language", None)
            data.setdefault("requested_caption_languages", [])
            data["caption_tracks"] = [
                {
                    "id": track_id,
                    "language": original_language,
                    "kind": "original",
                    "source_track_id": None,
                    "source_language": None,
                    "review_state": "unreviewed",
                    "cues": deepcopy(data.get("cues", []) or []),
                    "findings": deepcopy(data.get("findings", []) or []),
                    "exports": deepcopy(data.get("exports", []) or []),
                    "translation_model": None,
                }
            ]
            data["active_caption_track_id"] = track_id
            data["schema_version"] = 4
            version = 4
            changed = True
            continue
        raise ValueError(f"No migration path exists for project schema version {version}")

    return data, changed
