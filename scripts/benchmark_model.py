from __future__ import annotations

import argparse
import json
from pathlib import Path

from accessible_caption_studio.benchmarking import evaluate_records


def load_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON on line {line_number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise SystemExit(f"Line {line_number} must contain one JSON object")
        records.append(value)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate caption-model outputs from a JSONL benchmark manifest."
    )
    parser.add_argument("manifest", type=Path, help="JSONL file with references and hypotheses")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    report = evaluate_records(load_records(args.manifest))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
