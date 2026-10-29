"""Snapshot the inputs the Phase 4 analysis needs into small, committed files.

The raw inputs are large and git-ignored (``runs_live/`` is ~7 GB of bags and
telemetry; the per-run result traces are tens of MB per set). This step reads
them once and writes two compact files under ``analysis/data/`` so that
:mod:`analysis.results` reproduces every number from the repo alone:

* ``missions.json`` — per mission: composition, ground-truth faults, and the
  evidence-ceiling signal statistics (:mod:`analysis.evidence`).
* ``runs.jsonl`` — per run: the scorecard fields plus the submitted
  ``fault_id`` / ``vendor`` (scorecards omit those; they come from the traces).

Cell sources match ``paper/gen_tables.py`` (the paper's canonical sets), plus
the gpt-5-mini D/E ablations, which ran in the same v4 batch as C/G.

Usage::

    python -m analysis.extract --runs runs_live
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.evidence import mission_stats

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = Path(__file__).resolve().parent / "data"

# (model, condition) -> (scoring dir, results dir)
SOURCES: dict[tuple[str, str], tuple[str, str]] = {
    ("azure-gpt-5-mini", "A"): ("scoring_results_phase4", "results_phase4"),
    ("azure-gpt-5-mini", "B"): ("scoring_results_phase4", "results_phase4"),
    ("azure-gpt-5-mini", "C"): ("scoring_results_phase4_v4", "results_phase4_v4"),
    ("azure-gpt-5-mini", "D"): ("scoring_results_phase4_v4", "results_phase4_v4"),
    ("azure-gpt-5-mini", "E"): ("scoring_results_phase4_v4", "results_phase4_v4"),
    ("azure-gpt-5-mini", "G"): ("scoring_results_phase4_v4", "results_phase4_v4"),
    ("azure-gpt-5", "A"): ("scoring_results_phase4_gpt5_ab", "results_phase4_gpt5_ab"),
    ("azure-gpt-5", "B"): ("scoring_results_phase4_gpt5_ab", "results_phase4_gpt5_ab"),
    ("azure-gpt-5", "C"): ("scoring_results_phase4_gpt5_cg", "results_phase4_gpt5_cg"),
    ("azure-gpt-5", "G"): ("scoring_results_phase4_gpt5_cg", "results_phase4_gpt5_cg"),
}

_CARD_FIELDS = (
    "run_id",
    "mission_id",
    "model_id",
    "condition_code",
    "composition",
    "is_clean_mission",
    "root_cause_correct",
    "cross_vendor_attribution_correct",
    "submitted_diagnosis",
    "tool_call_count",
    "usd_cost",
    "prompt_tokens",
)


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _diagnoses(results_dir: Path) -> dict[str, dict | None]:
    """run_id -> final_diagnosis (None when the agent never submitted)."""
    out: dict[str, dict | None] = {}
    for f in sorted(results_dir.glob("*.jsonl")):
        if f.name == "manifest.json":
            continue
        rec = _read_jsonl(f)[0]
        out[rec["run_id"]] = rec.get("final_diagnosis")
    return out


def extract_runs() -> list[dict]:
    rows: list[dict] = []
    cards_cache: dict[str, list[dict]] = {}
    diag_cache: dict[str, dict[str, dict | None]] = {}
    for (model, cond), (scoring_dir, results_dir) in SOURCES.items():
        if scoring_dir not in cards_cache:
            cards_cache[scoring_dir] = _read_jsonl(_REPO_ROOT / scoring_dir / "scorecards.jsonl")
        if results_dir not in diag_cache:
            diag_cache[results_dir] = _diagnoses(_REPO_ROOT / results_dir)
        cards = [
            c
            for c in cards_cache[scoring_dir]
            if c["model_id"] == model and c["condition_code"] == cond
        ]
        if len(cards) != 47:
            raise ValueError(f"{model}/{cond}: expected 47 scorecards, got {len(cards)}")
        for c in cards:
            if c["run_id"] not in diag_cache[results_dir]:
                raise KeyError(f"{c['run_id']} missing from {results_dir}")
            diag = diag_cache[results_dir][c["run_id"]] or {}
            row = {k: c.get(k) for k in _CARD_FIELDS}
            row["hallucination_total"] = c["hallucination"]["total"]
            row["vendor_misattribution"] = c["hallucination"]["vendor_misattribution"]
            row["submitted_fault_id"] = diag.get("fault_id")
            row["submitted_vendor"] = diag.get("vendor")
            rows.append(row)
    return rows


def extract_missions(runs_root: Path, mission_ids: set[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for mid in sorted(mission_ids):
        mdir = runs_root / mid
        meta = json.loads((mdir / "mission_meta.json").read_text(encoding="utf-8"))
        gt_path = mdir / "ground_truth.json"
        injections = (
            json.loads(gt_path.read_text(encoding="utf-8"))["injections"]
            if gt_path.exists()
            else []
        )
        out[mid] = {
            "composition": meta["composition"],
            "faults": [{"fault_id": i["fault_id"], "vendor": i["vendor"]} for i in injections],
            "stats": mission_stats(mdir / "telemetry.sqlite"),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=_REPO_ROOT / "runs_live")
    args = parser.parse_args(argv)

    runs = extract_runs()
    missions = extract_missions(args.runs, {r["mission_id"] for r in runs})
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (_DATA_DIR / "runs.jsonl").open("w", encoding="utf-8") as fh:
        for r in sorted(runs, key=lambda r: (r["model_id"], r["condition_code"], r["mission_id"])):
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    (_DATA_DIR / "missions.json").write_text(
        json.dumps(missions, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(runs)} runs and {len(missions)} missions to {_DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
