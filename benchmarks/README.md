# Caption model benchmarks

This folder defines the repeatable evaluation format used to compare the current local caption stack with future models.

Each benchmark input is JSON Lines: one JSON object per media sample. Keep media itself outside Git unless it is intentionally licensed and small enough for the repository.

Supported fields:

- `id`: stable sample identifier
- `category`: scenario such as `clean_speech`, `background_noise`, `music_under_speech`, `accented_speech`, `overlap`, or `mobile_recording`
- `reference_text`: human-verified transcript
- `hypothesis_text`: model transcript
- `reference_speakers`: optional aligned anonymous speaker labels
- `hypothesis_speakers`: optional aligned model speaker labels
- `reference_sounds`: optional verified SDH sound labels
- `hypothesis_sounds`: optional predicted SDH sound labels
- `runtime_seconds`: optional wall-clock inference time
- `peak_memory_mb`: optional peak process memory

Run:

```bash
python scripts/benchmark_model.py benchmarks/example.jsonl
```

The report includes aggregate and per-category word error rate, character error rate, anonymous speaker-label error, sound-event precision/recall/F1, average runtime, and average peak memory.

The speaker metric is intentionally a label-assignment metric over already aligned benchmark units. It finds the best anonymous-label permutation so `Speaker 1` versus `Voice B` is not counted as an error merely because the names differ. It is not a full diarization error rate and should not be presented as DER.

For meaningful comparisons, keep a fixed held-out benchmark set and do not tune a custom model on those samples.
