from __future__ import annotations

import hashlib
import json
import math
import sys
import urllib.request
import wave
from pathlib import Path

OPENCV_ZOO_REVISION = "f88e9b2bafd21f1cad242fb5af6d78f2bcba16a3"
YUNET_NAME = "face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SFACE_NAME = "face_recognition_sface_2021dec.onnx"
SFACE_SHA256 = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
MODEL_ROOT = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
    f"{OPENCV_ZOO_REVISION}/models"
)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_model(directory: Path, name: str, folder: str, expected: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / name
    if destination.is_file() and _digest(destination) == expected:
        return destination
    partial = destination.with_suffix(destination.suffix + ".partial")
    partial.unlink(missing_ok=True)
    try:
        urllib.request.urlretrieve(f"{MODEL_ROOT}/{folder}/{name}", partial)
        if _digest(partial) != expected:
            raise RuntimeError(f"Downloaded {name} did not match its pinned checksum.")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return destination


def _iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = left
    bx, by, bw, bh = right
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0


def _audio_energy(path: Path, start: float, end: float) -> float:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        source.setpos(min(source.getnframes(), max(0, round(start * rate))))
        frames = source.readframes(max(1, round((end - start) * rate)))
        width = source.getsampwidth()
    if width != 2 or not frames:
        return 0
    import array

    samples = array.array("h", frames)
    if sys.byteorder == "big":
        samples.byteswap()
    rms = math.sqrt(sum(value * value for value in samples) / max(1, len(samples)))
    return min(1.0, rms / 3500)


def _normalize(values):
    import numpy as np

    vector = np.asarray(values, dtype="float32").reshape(-1)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def _cluster_tracks(tracks: list[dict], threshold: float = 0.363) -> None:
    import numpy as np

    candidates = [track for track in tracks if track.get("embedding") is not None]
    clusters: list[list[dict]] = [[track] for track in candidates]

    def centroid(cluster: list[dict]):
        weights = np.asarray([max(1, item["embedding_count"]) for item in cluster])
        values = np.stack([item["embedding"] for item in cluster])
        return _normalize(np.average(values, axis=0, weights=weights))

    while len(clusters) > 1:
        best: tuple[float, int, int] | None = None
        centroids = [centroid(cluster) for cluster in clusters]
        for left in range(len(clusters)):
            for right in range(left + 1, len(clusters)):
                similarity = float(np.dot(centroids[left], centroids[right]))
                if best is None or similarity > best[0]:
                    best = (similarity, left, right)
        if best is None or best[0] < threshold:
            break
        _, left, right = best
        clusters[left].extend(clusters.pop(right))

    clusters.sort(key=lambda cluster: min(item["samples"][0]["time"] for item in cluster))
    for number, cluster in enumerate(clusters, 1):
        center = centroid(cluster)
        for track in cluster:
            similarity = float(np.dot(track["embedding"], center))
            track["identity_cluster_id"] = f"Face identity {number}"
            track["face_match_confidence"] = round(max(0.0, min(1.0, similarity)), 4)


def analyze(
    video: Path,
    audio: Path,
    model_dir: Path,
    output: Path,
    words_path: Path | None = None,
) -> None:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is not installed; run the launcher setup again.") from exc

    yunet = _ensure_model(model_dir, YUNET_NAME, "face_detection_yunet", YUNET_SHA256)
    sface = _ensure_model(
        model_dir, SFACE_NAME, "face_recognition_sface", SFACE_SHA256
    )
    detector = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), 0.78, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(str(sface), "")

    capture = cv2.VideoCapture(str(video))
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    original_width = max(1, int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    original_height = max(1, int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    scale = min(1.0, 720 / max(original_width, original_height))
    width, height = round(original_width * scale), round(original_height * scale)
    detector.setInputSize((width, height))
    stride = max(1, round(fps / 8))
    target_frames: set[int] = set()
    if words_path and words_path.is_file():
        for word in json.loads(words_path.read_text(encoding="utf-8")):
            midpoint = (float(word["start"]) + float(word["end"])) / 2
            for moment in (midpoint - 0.12, midpoint, midpoint + 0.12):
                target_frames.add(max(0, round(moment * fps)))
    tracks: dict[str, dict] = {}
    previous_mouth: dict[str, object] = {}
    previous_hist = None
    camera_cuts: list[float] = []
    shot_id = 1
    next_track = 1
    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        targeted = frame_index in target_frames
        if frame_index % stride and not targeted:
            frame_index += 1
            continue
        timecode = frame_index / fps
        detector_frame = (
            cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            if scale < 1
            else frame
        )
        gray = cv2.cvtColor(detector_frame, cv2.COLOR_BGR2GRAY)
        histogram = cv2.calcHist([gray], [0], None, [32], [0, 256])
        cv2.normalize(histogram, histogram)
        cut = bool(
            previous_hist is not None
            and cv2.compareHist(previous_hist, histogram, cv2.HISTCMP_CORREL) < 0.35
        )
        previous_hist = histogram
        if cut:
            camera_cuts.append(round(timecode, 3))
            previous_mouth.clear()
            shot_id += 1
        _retval, faces = detector.detect(detector_frame)
        face_rows = [] if faces is None else list(faces)
        available = {
            track_id
            for track_id, track in tracks.items()
            if timecode - track["last"] <= 0.55
        }
        if cut:
            available.clear()
        for face in face_rows:
            x, y, w, h = (round(float(value)) for value in face[:4])
            box = (x, y, w, h)
            best = max(
                available,
                key=lambda item: _iou(tracks[item]["box"], box),
                default=None,
            )
            if best is None or _iou(tracks[best]["box"], box) < 0.28:
                best = f"face-{next_track}"
                next_track += 1
                tracks[best] = {
                    "id": best,
                    "last": timecode,
                    "box": box,
                    "samples": [],
                    "embedding_sum": None,
                    "embedding_count": 0,
                }
            else:
                available.remove(best)

            mouth = gray[
                max(0, y + h // 2) : min(height, y + h),
                max(0, x) : min(width, x + w),
            ]
            motion = 0.0
            old = previous_mouth.get(best)
            if old is not None and getattr(old, "shape", None) == mouth.shape and mouth.size:
                motion = float(cv2.absdiff(old, mouth).mean())
            previous_mouth[best] = mouth.copy()
            energy = _audio_energy(audio, timecode, timecode + stride / fps)
            active = min(1.0, max(0.0, (motion - 0.8) / 4.0)) * (
                0.45 + 0.55 * energy
            )
            if min(w, h) >= 70 and tracks[best]["embedding_count"] < 12:
                try:
                    aligned = recognizer.alignCrop(detector_frame, face)
                    feature = _normalize(recognizer.feature(aligned))
                    if tracks[best]["embedding_sum"] is None:
                        tracks[best]["embedding_sum"] = feature
                    else:
                        tracks[best]["embedding_sum"] += feature
                    tracks[best]["embedding_count"] += 1
                except cv2.error:
                    pass
            tracks[best]["last"] = timecode
            tracks[best]["box"] = box
            tracks[best]["samples"].append(
                {
                    "time": round(timecode, 3),
                    "x": round(x / width, 5),
                    "y": round(y / height, 5),
                    "width": round(w / width, 5),
                    "height": round(h / height, 5),
                    "active_confidence": round(active, 4),
                    "shot_id": shot_id,
                    "targeted": targeted,
                }
            )
        frame_index += 1
    capture.release()

    useful = [track for track in tracks.values() if len(track["samples"]) >= 3]
    for track in useful:
        total = track.pop("embedding_sum", None)
        if total is not None and track["embedding_count"]:
            track["embedding"] = _normalize(total / track["embedding_count"])
        else:
            track["embedding"] = None
    _cluster_tracks(useful)
    for track in useful:
        track.pop("embedding", None)
        track.pop("embedding_count", None)
        track.pop("box", None)
        track.pop("last", None)
        track["speaker"] = None
    output.write_text(
        json.dumps(
            {
                "engine": "sface_ecapa_v1",
                "tracks": useful,
                "camera_cuts": camera_cuts,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    analyze(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]),
        Path(sys.argv[4]),
        Path(sys.argv[5]) if len(sys.argv) > 5 else None,
    )
