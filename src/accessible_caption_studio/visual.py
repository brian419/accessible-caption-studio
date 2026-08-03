from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from .errors import StudioError
from .models import FaceTrackSummary, FusionSummary, SpeakerTurn, WordToken


def _speaker_number(label: str) -> int:
    try:
        return int(label.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 99


def _turn_identity_scores(turn: SpeakerTurn, tracks: list[dict]) -> list[tuple[float, str]]:
    values: dict[str, list[float]] = defaultdict(list)
    visible: set[str] = set()
    for track in tracks:
        identity = track.get("identity_cluster_id")
        if not identity:
            continue
        samples = [
            sample
            for sample in track.get("samples", [])
            if turn.start - 0.08 <= float(sample["time"]) <= turn.end + 0.08
        ]
        if samples:
            visible.add(identity)
            values[identity].extend(float(sample["active_confidence"]) for sample in samples)
    scores = []
    for identity, activity in values.items():
        mean = sum(activity) / len(activity)
        peak = max(activity)
        score = 0.55 * mean + 0.45 * peak
        if len(visible) == 1:
            score = max(score, 0.72)
        scores.append((min(1.0, score), identity))
    return sorted(scores, reverse=True)


def _audio_turn(start: float, end: float, speakers: list[SpeakerTurn]) -> SpeakerTurn | None:
    best = max(
        speakers,
        key=lambda turn: max(0.0, min(end, turn.end) - max(start, turn.start)),
        default=None,
    )
    if best is None or min(end, best.end) - max(start, best.start) <= 0:
        return None
    return best


def _compress_word_turns(turns: list[SpeakerTurn]) -> list[SpeakerTurn]:
    merged: list[SpeakerTurn] = []
    for turn in turns:
        previous = merged[-1] if merged else None
        if previous and previous.speaker == turn.speaker and turn.start - previous.end <= 0.65:
            previous.end = max(previous.end, turn.end)
            values = [
                value
                for value in (previous.confidence, turn.confidence)
                if value is not None
            ]
            previous.confidence = sum(values) / len(values) if values else None
            previous.visual_confidence = max(
                previous.visual_confidence or 0, turn.visual_confidence or 0
            ) or None
            if previous.method != turn.method:
                previous.method = (
                    "voice_face"
                    if any("face" in method for method in (previous.method, turn.method))
                    else "uncertain"
                )
        else:
            merged.append(turn.model_copy(deep=True))
    return merged


def _fuse_words(
    speakers: list[SpeakerTurn],
    tracks: list[dict],
    words: list[WordToken],
    expected_speaker_count: int | None,
    voice_cluster_count: int | None,
    camera_cuts: list[float] | None,
) -> tuple[list[SpeakerTurn], list[FaceTrackSummary], FusionSummary]:
    word_decisions: list[tuple[str | None, float, str | None]] = []
    evidence_seconds: dict[str, float] = defaultdict(float)
    evidence_words: dict[str, int] = defaultdict(int)
    first_seen: dict[str, float] = {}
    for word in words:
        probe = SpeakerTurn(
            speaker="Speaker 1",
            start=max(0.0, word.start - 0.2),
            end=word.end + 0.2,
            method="uncertain",
        )
        scores = _turn_identity_scores(probe, tracks)
        best_score, identity = scores[0] if scores else (0.0, None)
        runner_up = scores[1][0] if len(scores) > 1 else 0.0
        matching_tracks = [
            track
            for track in tracks
            if track.get("identity_cluster_id") == identity
            and sum(
                1
                for sample in track.get("samples", [])
                if probe.start <= float(sample["time"]) <= probe.end
            ) >= 2
        ]
        decisive = bool(
            identity
            and matching_tracks
            and best_score >= 0.65
            and best_score - runner_up >= 0.15
        )
        track_id = matching_tracks[0]["id"] if decisive else None
        if decisive and identity:
            duration = max(0.1, word.end - word.start)
            evidence_seconds[identity] += duration * best_score
            evidence_words[identity] += 1
            first_seen.setdefault(identity, word.start)
            word_decisions.append((identity, best_score, track_id))
        else:
            word_decisions.append((None, best_score, None))

    ranked = sorted(
        evidence_seconds,
        key=lambda identity: (-evidence_seconds[identity], first_seen[identity]),
    )
    supported = [
        identity
        for identity in ranked
        if evidence_words[identity] >= 2 or evidence_seconds[identity] >= 0.8
    ]
    if expected_speaker_count:
        supported = ranked[:expected_speaker_count]
    supported.sort(key=lambda identity: first_seen[identity])
    voice_labels = sorted(
        {turn.speaker for turn in speakers if turn.speaker}, key=_speaker_number
    )
    voice_count = len(voice_labels) if voice_cluster_count is None else voice_cluster_count
    final_limit = expected_speaker_count or min(8, max(voice_count, len(supported), 1))
    identity_speakers = {
        identity: f"Speaker {index + 1}"
        for index, identity in enumerate(supported[:final_limit])
    }

    voice_votes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    audio_by_word: list[SpeakerTurn | None] = []
    for word, (identity, confidence, _track) in zip(words, word_decisions, strict=True):
        audio = _audio_turn(word.start, word.end, speakers)
        audio_by_word.append(audio)
        if audio and identity in identity_speakers:
            voice_votes[audio.speaker][identity_speakers[identity]] += confidence
    voice_mapping: dict[str, str] = {}
    used: set[str] = set()
    for voice in voice_labels:
        votes = voice_votes.get(voice, {})
        available_votes = {
            speaker: score for speaker, score in votes.items() if speaker not in used
        }
        if available_votes:
            voice_mapping[voice] = max(available_votes, key=available_votes.get)
        else:
            voice_mapping[voice] = next(
                (
                    f"Speaker {number}"
                    for number in range(1, final_limit + 1)
                    if f"Speaker {number}" not in used
                ),
                voice,
            )
        used.add(voice_mapping[voice])

    word_turns: list[SpeakerTurn] = []
    associations: list[float] = []
    for word, audio, (identity, visual_confidence, track_id) in zip(
        words, audio_by_word, word_decisions, strict=True
    ):
        face_speaker = identity_speakers.get(identity or "")
        voice_speaker = voice_mapping.get(audio.speaker, audio.speaker) if audio else None
        if face_speaker:
            speaker = face_speaker
            associations.append(visual_confidence)
            method = "voice_face" if audio else "face_only"
        else:
            speaker = voice_speaker
            method = "voice_only" if audio and (audio.confidence or 0) >= 0.5 else "uncertain"
        if not speaker:
            word.speaker = None
            word.speaker_confidence = None
            word.speaker_method = "uncertain"
            continue
        confidence_values = [
            value
            for value in (
                audio.confidence if audio else None,
                visual_confidence if face_speaker else None,
            )
            if value is not None
        ]
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else None
        word.speaker = speaker
        word.speaker_confidence = confidence
        word.speaker_method = method
        word.face_track_id = track_id
        word_turns.append(
            SpeakerTurn(
                speaker=speaker,
                start=word.start,
                end=word.end,
                confidence=confidence,
                audio_confidence=audio.confidence if audio else None,
                visual_confidence=visual_confidence if face_speaker else None,
                face_track_id=track_id,
                method=method,
            )
        )
    if expected_speaker_count == 2:
        turns_by_time = {(turn.start, turn.end): turn for turn in word_turns}
        for left, right in zip(words, words[1:], strict=False):
            cut_between = any(
                left.end - 0.05 <= cut <= right.start + 0.05
                for cut in camera_cuts or []
            )
            supported_boundary = bool(
                cut_between
                and right.start - left.end >= 0.2
                and left.end - left.start <= 1.2
                and re.search(r"[.!?][\"']?$", left.text.strip())
                and right.speaker_method in {"voice_face", "face_only"}
                and (right.speaker_confidence or 0) >= 0.6
                and left.speaker_method in {"voice_only", "uncertain"}
            )
            if supported_boundary and right.speaker in {"Speaker 1", "Speaker 2"}:
                inferred = "Speaker 2" if right.speaker == "Speaker 1" else "Speaker 1"
                left.speaker = inferred
                left.speaker_method = "uncertain"
                left.speaker_confidence = min(0.65, right.speaker_confidence or 0.65)
                matching = turns_by_time.get((left.start, left.end))
                if matching:
                    matching.speaker = inferred
                    matching.method = "uncertain"
                    matching.confidence = left.speaker_confidence
    fused = _compress_word_turns(word_turns)
    for track in tracks:
        track["speaker"] = identity_speakers.get(track.get("identity_cluster_id"))
    summaries = [
        FaceTrackSummary(
            id=track["id"],
            start=track["samples"][0]["time"],
            end=track["samples"][-1]["time"],
            speaker=track.get("speaker"),
            identity_cluster_id=track.get("identity_cluster_id"),
            face_match_confidence=track.get("face_match_confidence"),
            max_active_confidence=max(
                (sample["active_confidence"] for sample in track["samples"]), default=0
            ),
        )
        for track in tracks
        if track.get("samples")
    ]
    final_count = len({turn.speaker for turn in fused})
    return fused, summaries, FusionSummary(
        voice_cluster_count=voice_count,
        face_identity_count=len(supported),
        final_speaker_count=min(8, final_count),
        association_confidence=(sum(associations) / len(associations) if associations else None),
    )


def fuse_speaker_evidence(
    speakers: list[SpeakerTurn],
    tracks: list[dict],
    expected_speaker_count: int | None = None,
    voice_cluster_count: int | None = None,
    words: list[WordToken] | None = None,
    camera_cuts: list[float] | None = None,
) -> tuple[list[SpeakerTurn], list[FaceTrackSummary], FusionSummary]:
    if words:
        return _fuse_words(
            speakers,
            tracks,
            words,
            expected_speaker_count,
            voice_cluster_count,
            camera_cuts,
        )
    decisions: list[tuple[str | None, float]] = []
    evidence_seconds: dict[str, float] = defaultdict(float)
    evidence_turns: dict[str, int] = defaultdict(int)
    first_seen: dict[str, float] = {}
    for turn in speakers:
        scores = _turn_identity_scores(turn, tracks)
        best_score, identity = scores[0] if scores else (0.0, None)
        runner_up = scores[1][0] if len(scores) > 1 else 0.0
        decisive = bool(identity and best_score >= 0.35 and best_score - runner_up >= 0.15)
        if decisive and identity:
            duration = max(0.0, turn.end - turn.start)
            evidence_seconds[identity] += duration * best_score
            evidence_turns[identity] += 1
            first_seen.setdefault(identity, turn.start)
            decisions.append((identity, best_score))
        else:
            decisions.append((None, best_score))

    supported = [
        identity
        for identity in evidence_seconds
        if evidence_turns[identity] >= 2 or evidence_seconds[identity] >= 1.2
    ]
    if expected_speaker_count:
        ranked = sorted(
            evidence_seconds,
            key=lambda item: (-evidence_seconds[item], first_seen.get(item, float("inf"))),
        )
        supported = ranked[:expected_speaker_count]
    supported.sort(key=lambda item: first_seen.get(item, float("inf")))

    voice_labels = sorted(
        {turn.speaker for turn in speakers if turn.speaker}, key=_speaker_number
    )
    voice_count = (
        len(voice_labels) if voice_cluster_count is None else voice_cluster_count
    )
    final_limit = expected_speaker_count or min(8, max(voice_count, len(supported), 1))
    identity_speakers = {
        identity: f"Speaker {index + 1}"
        for index, identity in enumerate(supported[:final_limit])
    }

    voice_votes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for turn, (identity, confidence) in zip(speakers, decisions, strict=True):
        if identity in identity_speakers:
            voice_votes[turn.speaker][identity_speakers[identity]] += (
                max(0.1, turn.end - turn.start) * confidence
            )
    voice_mapping: dict[str, str] = {}
    used = set(identity_speakers.values())
    for voice in voice_labels:
        votes = voice_votes.get(voice, {})
        if votes:
            voice_mapping[voice] = max(votes, key=votes.get)
            continue
        available = next(
            (
                f"Speaker {number}"
                for number in range(1, final_limit + 1)
                if f"Speaker {number}" not in used
            ),
            None,
        )
        voice_mapping[voice] = available or voice
        used.add(voice_mapping[voice])

    fused: list[SpeakerTurn] = []
    association_scores: list[float] = []
    for turn, (identity, visual_confidence) in zip(speakers, decisions, strict=True):
        face_speaker = identity_speakers.get(identity or "")
        voice_speaker = voice_mapping.get(turn.speaker, turn.speaker)
        if face_speaker:
            final_speaker = face_speaker
            association_scores.append(visual_confidence)
            method = (
                "voice_face"
                if (turn.audio_confidence or turn.confidence or 0) >= 0.5
                else "face_only"
            )
        else:
            final_speaker = voice_speaker
            method = "voice_only" if (turn.confidence or 0) >= 0.5 else "uncertain"
        matching_track = next(
            (
                track["id"]
                for track in tracks
                if track.get("identity_cluster_id") == identity
                and any(
                    turn.start - 0.08 <= float(sample["time"]) <= turn.end + 0.08
                    for sample in track.get("samples", [])
                )
            ),
            None,
        )
        fused.append(
            turn.model_copy(
                update={
                    "speaker": final_speaker,
                    "audio_confidence": turn.audio_confidence or turn.confidence,
                    "visual_confidence": visual_confidence or None,
                    "face_track_id": matching_track,
                    "method": method,
                }
            )
        )

    for track in tracks:
        track["speaker"] = identity_speakers.get(track.get("identity_cluster_id"))
    summaries = [
        FaceTrackSummary(
            id=track["id"],
            start=track["samples"][0]["time"],
            end=track["samples"][-1]["time"],
            speaker=track.get("speaker"),
            identity_cluster_id=track.get("identity_cluster_id"),
            face_match_confidence=track.get("face_match_confidence"),
            max_active_confidence=max(
                (sample["active_confidence"] for sample in track["samples"]), default=0
            ),
        )
        for track in tracks
        if track.get("samples")
    ]
    final_count = len({turn.speaker for turn in fused if turn.speaker})
    summary = FusionSummary(
        voice_cluster_count=voice_count,
        face_identity_count=len(supported),
        final_speaker_count=min(8, final_count),
        association_confidence=(
            sum(association_scores) / len(association_scores)
            if association_scores
            else None
        ),
    )
    return fused, summaries, summary


def analyze_active_speakers(
    video: Path,
    audio: Path,
    model_dir: Path,
    output: Path,
    speakers: list[SpeakerTurn],
    progress: Callable[[str, int, str], None],
    expected_speaker_count: int | None = None,
    voice_cluster_count: int | None = None,
    words: list[WordToken] | None = None,
) -> tuple[list[SpeakerTurn], list[FaceTrackSummary], str, FusionSummary]:
    progress("Matching recurring faces", 69, "Loading private YuNet and SFace models")
    result = output.with_suffix(".partial.json")
    words_path = output.with_suffix(".words.json")
    if words:
        words_path.write_text(
            json.dumps([word.model_dump(mode="json") for word in words]),
            encoding="utf-8",
        )
    command = [
        sys.executable,
        "-m",
        "accessible_caption_studio.visual_worker",
        str(video),
        str(audio),
        str(model_dir / "opencv-face"),
        str(result),
        str(words_path),
    ]
    runner = getattr(progress, "run_process", None)
    if runner:
        process = runner(command)
    else:
        import subprocess

        process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode:
        words_path.unlink(missing_ok=True)
        detail = (process.stderr or process.stdout or "").strip()
        raise StudioError("visual_speaker_failed", detail[-900:] or "Visual analysis failed.")
    try:
        payload = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StudioError(
            "visual_speaker_failed", "Visual analysis returned no usable result."
        ) from exc
    finally:
        result.unlink(missing_ok=True)
        words_path.unlink(missing_ok=True)
    tracks = payload.get("tracks", [])
    progress("Finding active speakers", 77, "Comparing visible identities with speech timing")
    fused, summaries, summary = fuse_speaker_evidence(
        speakers,
        tracks,
        expected_speaker_count,
        voice_cluster_count,
        words,
        payload.get("camera_cuts", []),
    )
    progress("Combining evidence", 82, "Reconciling independent voice and face identities")
    output.write_text(
        json.dumps(
            {
                "engine": "sface_ecapa_v1",
                "tracks": tracks,
                "camera_cuts": payload.get("camera_cuts", []),
            }
        ),
        encoding="utf-8",
    )
    status = "complete" if summaries else "no_faces"
    return fused, summaries, status, summary
