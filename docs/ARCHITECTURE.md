# Architecture and extension guide

## Runtime boundaries

Accessible Caption Studio is a local FastAPI application. The server binds to loopback,
serves a framework-free browser interface, streams media and exports, and persists each
project independently. No external application service or database is required.

`ProjectStore` is the only component that resolves project paths. Project identifiers are
32-character hexadecimal UUIDs; download filenames are matched against persisted export
records. These rules prevent user-provided paths from escaping the storage root.

## Persisted contracts

- `Project`: title, timestamps, media, transcription quality, cues, raw model output,
  findings, and exports
- `MediaAsset`: original/stored names, duration, stream metadata, source URL, and size
- `CaptionCue`: stable ID, interval, text, anonymous speaker, source, confidence, and optional
  overlap-group ID for two utterances sharing one displayed timeframe
- `WordToken`: Whisper word interval, primary/recovery source, confidence, and optional
  word-level anonymous speaker evidence
- `SpeakerTurn`: anonymous interval with audio/visual confidence, evidence method, and an
  optional anonymous face-track reference
- `FaceTrackSummary`: time bounds, optional anonymous speaker mapping, and maximum activity
  confidence; detailed normalized boxes live in `speaker-evidence.json`
- `SoundEvent`: AudioSet label interval and confidence
- `ValidationFinding`: stable rule code, severity, message, and optional cue ID
- `AnalysisJob`: resumable status, stage, progress, message, structured error code, and an
  optional persisted proposal result
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
| `POST` | `/api/projects/{id}/analyze-overlap` | Propose two separated voice lines for a selected interval |
| `POST` | `/api/projects/{id}/reanalyze-speakers` | Build an Auto or exact-count speaker proposal |
| `POST` | `/api/projects/{id}/speaker-proposals/{job}/apply` | Atomically apply a current speaker proposal |
| `POST` | `/api/projects/{id}/repair-transcript` | Build an adaptive dialogue-recovery proposal |
| `POST` | `/api/projects/{id}/transcript-proposals/{job}/apply` | Atomically apply a current transcript proposal |
| `GET` | `/api/projects/{id}/speaker-evidence` | Stream nearby normalized active-face boxes for the player |
| `POST` | `/api/projects/{id}/validate` | Recalculate accessibility findings |
| `GET/POST` | `/api/projects/{id}/jobs/...` | Monitor or cancel background work |
| `POST` | `/api/projects/{id}/exports/{format}` | Create SRT/VTT/HTML/MP4 output |
| `GET` | `/api/projects/{id}/exports/{filename}` | Stream a persisted export |
| `GET/DELETE` | `/api/storage/...` | Inspect or clear non-project caches |

Errors from media or model components use a stable `code` and a plain-language `message`.
Missing setup is never represented as a successful analysis with silently omitted data.

## Model adapters

`LocalAnalyzer` is the integration boundary for ML work:

1. `faster-whisper/distil-large-v3` is the Accurate default and `small.en` remains the Fast
   option. Both return word timestamps and probabilities. Independent Silero VAD regions
   are compared against word coverage; uncovered speech, long gaps, low-confidence passages,
   and rapid visual transitions are retranscribed without previous-text conditioning or an
   old-transcript prompt. Primary and recovery words are reconciled by acoustic time, so
   time-separated repeated dialogue is never removed as duplicate text. Whisper runs in an
   isolated process so CTranslate2 and PyTorch never share competing Intel OpenMP runtimes.
2. Public `speechbrain/spkrec-ecapa-voxceleb` ECAPA embeddings group clean,
   Whisper-derived speech windows by voice similarity. Clusters become anonymous,
   order-of-appearance speaker labels. The pinned model needs no account, access token,
   or gated consent and runs in a cancellable worker.
3. `MIT/ast-finetuned-audioset-10-10-0.4593` scores overlapping audio windows. An
   accessibility-focused whitelist removes generic speech labels, adjacent duplicates are
   merged, and low-confidence events are suppressed.
4. Each word receives independent ECAPA and visible-face evidence before consecutive word
   assignments are compressed into speaker turns. Targeted frames and camera cuts allow a
   supported one-word reply to create a cue boundary without allowing weak visual flicker.
   Useful sound events become bracketed SDH cues.
5. On request, public `speechbrain/sepformer-whamr16k` separates a selected interval into
   at most two streams in an isolated worker. Whisper transcribes each stream, WavLM matches
   established anonymous labels, and the persisted job result remains a proposal until the
   editor applies it. This older overlap-only matching adapter does not participate in
   normal speaker discovery.
6. Video projects run an isolated OpenCV worker with pinned YuNet and SFace models. YuNet
   finds faces, SFace temporarily embeds several high-quality frames per track, and
   average-link cosine clustering anonymously reconnects tracks across camera cuts.
   Mouth-region movement, word-targeted samples, camera cuts, and speech timing identify
   likely speaking faces. Merely being the only visible face is not speaking evidence, and
   moderate reaction-shot motion cannot override a confident voice. A weighted association
   reconciles strong visual evidence with ECAPA clusters at word granularity; either signal
   can degrade independently. Temporary face crops and embeddings are never persisted.

Long-running tools and ML models execute in managed process groups. Cancelling a job first
persists `cancelling`, sends a graceful termination signal, escalates after two seconds,
cleans partial artifacts, and prevents late worker results from changing the cancelled job.

Future models should preserve these return contracts so project storage and the editor do
not depend on a specific ML library.

The browser editor follows the active timed cue inside its own scroll container. Following
is suspended while the user manually scrolls or edits a cue, supports simultaneous rows,
respects reduced-motion preferences, and can be resumed or disabled explicitly.

## Known extension points

- Add a multilingual Whisper adapter alongside the English Fast and Accurate modes.
- Add a verified active-speaker model as an optional replacement for the lightweight
  mouth-activity scorer while preserving the same face-evidence contract.
- Replace the thread job runner with a process worker for parallel model jobs.
- Add signed project archives for portable backup and restore.
- Add formal WCAG-oriented authoring reports without presenting them as legal certification.
