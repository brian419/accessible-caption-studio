# Accessible Caption Studio

Accessible Caption Studio is a private, local-first caption authoring application for prerecorded
video and audio. It combines local speech recognition, anonymous speaker labeling, meaningful
sound descriptions, accessibility checks, a synchronized editor, caption appearance controls,
and production-ready exports in one browser-based workspace.

The FastAPI server binds only to `127.0.0.1`. Media analysis runs on the computer after required
models are downloaded, and project media, transcripts, model output, and exports stay under the
ignored local `storage/` directory.

## Screenshots

### Caption editor

![Accessible Caption Studio caption editor](docs/caption-editor.png)

### Caption customization

![Accessible Caption Studio caption customization controls](docs/caption-customization.png)

### Media upload

![Accessible Caption Studio media upload screen](docs/media-upload.png)

### Recent projects

![Accessible Caption Studio recent projects screen](docs/recent-projects.png)

## What it does

### Import and transcription

- Imports MP4, MOV, WebM, MP3, WAV, and M4A media.
- Imports individual YouTube videos when you have permission to download them.
- Can use a locally signed-in browser for YouTube imports without copying browser credentials into
  a project.
- Accepts existing SRT, VTT, TTML, and DFXP caption files.
- Provides Fast and Accurate local Whisper transcription modes with word timestamps.
- Supports language selection and automatic spoken-language detection for multilingual workflows.
- Rechecks suspicious speech gaps and low-confidence regions so legitimate repeated dialogue is
  not discarded as duplicate text.
- Keeps imported captions editable without forcing a new automatic analysis pass.

### Speakers, overlap, and sound descriptions

- Labels voices anonymously as `Speaker 1`, `Speaker 2`, and so on.
- Combines SpeechBrain ECAPA voice embeddings with OpenCV YuNet and SFace face tracking to improve
  speaker consistency in video.
- Uses audio-correlated mouth activity and recurring anonymous face tracks without performing face
  or voice identification.
- Lets users assign optional local display names while preserving anonymous internal speaker IDs.
- Can re-detect speakers using conservative Auto mode or an exact count from 1 to 8.
- Offers non-destructive previews for speaker repair and recovered dialogue before changing captions.
- Represents simultaneous speakers as separately editable caption lines in one timeframe.
- Offers an on-demand SpeechBrain SepFormer pass for short two-voice overlap intervals.
- Provides Off, Conservative, and Full SDH modes for meaningful non-speech sound captions.

### Caption editing and accessibility

- Creates readable caption segments instead of exposing only a raw transcript.
- Provides synchronized video or audio playback with keyboard controls.
- Keeps the active timeline caption centered during playback with a user-controlled follow mode.
- Supports adding, editing, deleting, splitting, merging, reordering, and undoing caption changes.
- Checks timing, overlap, duration, line length, line count, and reading speed.
- Presents accessibility findings alongside the media preview and editable timeline.
- Supports project-level caption tracks for multilingual caption workflows.
- Can export an accessibility authoring report alongside caption deliverables.

### Caption appearance

- Applies caption styling live in the media preview and saves the style with the project.
- Includes Classic Readable, High Contrast, Clean Minimal, Broadcast Blue, and Custom presets.
- Browses locally installed fonts with search, recent-font, and favorite-font views.
- Supports available font styles plus text size, color, outline, and line spacing controls.
- Supports background color, opacity, padding, shadow color, and shadow depth.
- Supports top, middle, or bottom placement; left, center, or right alignment; edge distance; and
  maximum caption width.
- Uses the saved caption appearance when rendering captioned MP4 exports.

### Projects, exports, and local storage

- Saves projects automatically so they can be reopened later.
- Shows recent projects with local thumbnails and project activity state.
- Supports favorite projects and alternate Recent Projects layouts.
- Prevents destructive project actions while active work is still running.
- Keeps long-running job progress visible when navigating between project views.
- Exports UTF-8 SRT, WebVTT, accessible HTML transcripts, and captioned MP4 video.
- Reports export progress and opens a completion dialog with the finished file details.
- Provides local model and storage management so cached models and temporary files can be cleared
  without deleting projects.
- Supports persistent light and dark appearance modes.

## Local-first model stack

The current automatic analysis pipeline uses public local models rather than a hosted caption API.
Model availability and exact processing depend on the selected workflow.

- **Speech recognition:** faster-whisper with Fast and Accurate model choices.
- **Speech coverage:** Silero-based speech detection is used to find suspicious uncovered regions
  for timestamp-aware recovery.
- **Speaker audio:** SpeechBrain ECAPA-TDNN embeddings provide anonymous voice evidence.
- **Speaker video:** OpenCV YuNet and SFace provide anonymous face detection, recurring face
  matching, and visual speaker evidence.
- **Overlapping voices:** SpeechBrain SepFormer can be invoked for short two-speaker intervals.
- **Sound descriptions:** AudioSet-style sound classification supports SDH caption suggestions.

Temporary face crops and embeddings are used only during local processing and are deleted. The
studio stores anonymous identity IDs, timing, normalized boxes, and confidence values rather than
trying to identify a real person.

## Quick start

### macOS

Requirements:

- macOS with a working Python installation available to the private bootstrap process
- FFmpeg and FFprobe on the `PATH`
- Internet access for initial model downloads and YouTube imports
- Several gigabytes of free disk space if all optional ML models are used

Double-click **Start Accessible Caption Studio.command** in Finder. The launcher uses `uv` to
prepare a project-local Python 3.11 runtime and isolated environment when needed, then opens the
studio in the default browser. It does not replace the system Python.

### Linux

Run:

```bash
./start-accessible-caption-studio.sh
```

### Windows

Run **Start Accessible Caption Studio.ps1** from PowerShell.

See [docs/PLATFORM_SETUP.md](docs/PLATFORM_SETUP.md) for platform-specific FFmpeg and launcher
notes.

## Typical workflow

1. Upload local media or paste a YouTube video URL.
2. Optionally import an existing SRT, VTT, TTML, or DFXP file.
3. Choose transcription language, caption targets, SDH behavior, and transcription quality as
   needed.
4. Run local analysis and keep the job panel available while processing continues.
5. Preview captions in sync with the media.
6. Use **Improve transcription** if dialogue appears to be missing.
7. Use **Re-detect speakers** or overlap analysis when speaker labels need additional review.
8. Edit caption text, timing, speakers, and sound descriptions in the timeline.
9. Customize caption appearance and verify it in the live preview.
10. Select **Check captions** and review accessibility findings.
11. Export SRT, VTT, HTML, an accessibility report, or a captioned MP4 as appropriate.

Completed project data is applied only after its worker exits successfully. Cancelling a running
job changes it to a cancelling state, terminates its active local worker, removes partial output,
and finishes without applying incomplete results.

## Developer setup

Accessible Caption Studio supports Python 3.11 and 3.12.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[ml,dev]"
.venv/bin/accessible-caption-studio start
```

For development that does not need the large optional ML dependencies:

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
```

Automatic analysis reports a visible warning when an optional speaker or sound model is not
available. Caption import, editing, validation, project management, and text exports remain usable
without those optional models.

## Architecture

```text
Local file / YouTube / caption import
                |
                v
      FFprobe media validation
                |
                v
       private project folder
                |
                v
      FFmpeg 16 kHz analysis audio
                |
                v
      Whisper timestamped words
                |
        +-------+---------------------------+
        |                                   |
        v                                   v
Silero coverage recovery           ECAPA voice evidence
                                            |
                                  YuNet + SFace evidence
                                            |
                                            v
                                hybrid anonymous speakers
                                            |
              +-----------------------------+------------------+
              |                                                |
              v                                                v
     caption composition                              SDH sound events
              |
              v
   optional overlap review
              |
              v
 editor + caption tracks + appearance + accessibility validation
              |
              v
   SRT / VTT / HTML / report / captioned MP4
```

Pydantic models define persisted project, caption, style, speaker, job, and caption-track data.
Background analysis and MP4 rendering persist progress to disk, while media and export files are
streamed by the local server rather than loaded into browser memory all at once.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for data contracts, API behavior, failure modes,
and extension points.

## Quality checks

```bash
ruff check .
pytest -q --ignore=tests/browser
pytest -q tests/browser
```

CI runs the backend test suite on Python 3.11 and 3.12, checks Python linting and JavaScript syntax,
runs Playwright browser, responsive-layout, and accessibility regressions, and validates Linux and
Windows launcher syntax. GitHub Actions uses read-only repository permissions for these checks.

The broader test suite covers caption parsing and round trips, segmentation, speaker assignment,
sound-event merging, accessibility findings, project persistence, API editing and export, storage
cleanup boundaries, real FFmpeg media inspection, browser behavior, and captioned rendering when
FFmpeg's subtitle filter is available.

See [docs/ACCESSIBILITY_TESTING.md](docs/ACCESSIBILITY_TESTING.md) for the accessibility testing
approach.

## Model benchmarking

The repository includes a repeatable benchmark harness for comparing the current local caption
stack with future models.

```bash
python scripts/benchmark_model.py benchmarks/example.jsonl
```

Reports can include aggregate and per-category word error rate, character error rate, anonymous
speaker-label error, sound-event precision/recall/F1, average runtime, and average peak memory.
Benchmark media should remain outside Git unless it is intentionally licensed and small enough for
the repository.

See [benchmarks/README.md](benchmarks/README.md) for the benchmark format and metric definitions.

## Privacy, accuracy, and limitations

- Speech recognition, speaker clustering, visual speaker matching, overlap separation, and sound
  classification are probabilistic and can make mistakes.
- Unusual pronunciation, music, noise, poor microphones, offscreen speakers, and obscured faces can
  reduce automatic accuracy.
- Speaker labels and visual tracks are intentionally anonymous. The application does not identify
  people by name from their face or voice.
- Simultaneous-speech separation is limited to two voices and requires review before proposed
  results replace existing captions.
- Automatic accessibility checks are authoring assistance, not certification of WCAG, FCC, ADA, or
  another legal standard.
- Captioned MP4 export is available for video projects, not audio-only projects.
- YouTube availability can change, and some videos cannot legally or technically be downloaded.
  Playlists are intentionally not imported.
- Initial ML model downloads can be large. Settings exposes local model storage and removal controls.

## Releases

Version tags matching `v*` run the release workflow, verify the project, build the Python wheel and
source distribution, create a portable source ZIP, generate SHA-256 checksums, and publish the
artifacts to a GitHub Release.
