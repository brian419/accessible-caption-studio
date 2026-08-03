# Architecture and extension guide

## Runtime boundaries

Accessible Caption Studio is a local FastAPI application. The server binds to loopback,
serves a framework-free browser interface, streams media and exports, and persists each
project independently. No external application service or database is required.

`ProjectStore` is the only component that resolves project paths. Project identifiers are
32-character hexadecimal UUIDs; download filenames are matched against persisted export
records. These rules prevent user-provided paths from escaping the storage root.

## Persisted contracts

- `Project`: title, timestamps, media, cues, raw model output, findings, and exports
- `MediaAsset`: original/stored names, duration, stream metadata, source URL, and size
- `CaptionCue`: stable ID, interval, text, anonymous speaker, source, and confidence
- `WordToken`: Whisper word interval and confidence
- `SpeakerTurn`: anonymous WavLM-clustered interval
- `SoundEvent`: AudioSet label interval and confidence
- `ValidationFinding`: stable rule code, severity, message, and optional cue ID
- `AnalysisJob`: resumable status, stage, progress, message, and structured error code
- `ExportArtifact`: format, safe filename, creation time, and size

JSON writes use a same-directory temporary file followed by an atomic replace. Media and
exports use the same partial-file pattern.

## Main API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/projects` | List projects by recent activity |
| `POST` | `/api/projects/upload` | Stream a media upload and optional captions |
| `POST` | `/api/projects/youtube` | Create a download-and-analysis job |
| `GET/PATCH/DELETE` | `/api/projects/{id}` | Open, autosave, rename, or delete |
| `POST` | `/api/projects/{id}/duplicate` | Copy a project and local source |
| `POST` | `/api/projects/{id}/analyze` | Start automatic analysis |
| `POST` | `/api/projects/{id}/validate` | Recalculate accessibility findings |
| `GET/POST` | `/api/projects/{id}/jobs/...` | Monitor or cancel background work |
| `POST` | `/api/projects/{id}/exports/{format}` | Create SRT/VTT/HTML/MP4 output |
| `GET` | `/api/projects/{id}/exports/{filename}` | Stream a persisted export |
| `GET/DELETE` | `/api/storage/...` | Inspect or clear non-project caches |

Errors from media or model components use a stable `code` and a plain-language `message`.
Missing setup is never represented as a successful analysis with silently omitted data.

## Model adapters

`LocalAnalyzer` is the integration boundary for ML work:

1. `faster-whisper/small.en` returns word timestamps and probabilities. It runs in an
   isolated worker process so CTranslate2 and PyTorch never load competing Intel OpenMP
   runtimes in the same process.
2. Public `microsoft/wavlm-base-plus-sv` embeddings group Whisper-derived speech windows
   by voice similarity. Clusters become anonymous, order-of-appearance speaker labels.
   The pinned safe-tensor model needs no account, access token, or gated consent.
3. `MIT/ast-finetuned-audioset-10-10-0.4593` scores overlapping audio windows. An
   accessibility-focused whitelist removes generic speech labels, adjacent duplicates are
   merged, and low-confidence events are suppressed.
4. Words become sentence/pause-aware cues, speakers are chosen by maximum overlap, and
   useful sound events become bracketed SDH cues.

Future models should preserve these return contracts so project storage and the editor do
not depend on a specific ML library.

## Known extension points

- Add a model choice field and multilingual Whisper adapter.
- Add a visual scene analyzer behind a separate opt-in interface.
- Replace the thread job runner with a process worker for parallel model jobs.
- Add signed project archives for portable backup and restore.
- Add formal WCAG-oriented authoring reports without presenting them as legal certification.
