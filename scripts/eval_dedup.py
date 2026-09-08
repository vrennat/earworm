"""Replay labeled batches without discovery, queue writes, or publication.

Run with the production runtime/config, but a separate dataset and output path:
python scripts/eval_dedup.py dataset.json --home /path/to/app --output /path/to/eval
The dataset contains `covered` strings and `cases` with id, candidates and
1-based `expected` duplicate numbers. Raw responses and bounded usage are saved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from earworm import dedup, llm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompts", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    dataset = json.loads(args.dataset.read_text())
    prompts = args.prompts or args.home / "prompts"
    results = []
    for i, case in enumerate(dataset["cases"]):
        calls = []
        def judge(prompt: str) -> str:
            response = llm.run_text(
                prompt, cwd=args.home, timeout=180, stage="dedup",
                ledger_path=args.output / f"batch-{i}" / "usage.jsonl",
            )
            calls.append({"prompt": prompt, "response": response})
            (args.output / f"batch-{i}-calls.json").write_text(json.dumps(calls, indent=2))
            return response
        started = time.monotonic()
        kept, dropped = dedup.filter_new(
            case["candidates"], dataset["covered"], judge=judge,
            prompt_path=prompts / "dedup.md",
        )
        predicted = [n for n, candidate in enumerate(case["candidates"], 1) if candidate not in kept]
        expected = set(case["expected"])
        result = {
            "id": case["id"], "expected": sorted(expected), "predicted": predicted,
            "false_negatives": sorted(expected - set(predicted)),
            "false_positives": sorted(set(predicted) - expected),
            "calls": len(calls), "seconds": round(time.monotonic() - started, 3),
            "matches": [{"candidate": d.candidate, "matches": d.matches} for d in dropped],
        }
        results.append(result)
        (args.output / "results.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
