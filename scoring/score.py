"""Scoring CLI — reduces ``results/*.jsonl`` + ``runs/<mission_id>/`` into
per-run scorecards, aggregate leaderboard rows, and the same-vs-multi-vendor
delta CSV.

Usage::

    python -m scoring.score \\
        --runs runs/ \\
        --results results/ \\
        --out scoring_out/

Outputs into ``--out``:

* ``scorecards.jsonl``          — one Scorecard per run
* ``leaderboard.json``          — aggregated (condition × model × composition) cells
* ``composition_delta.csv``     — paper-ready same-vs-multi delta table
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from scoring.composition_delta import compute_composition_deltas
from scoring.metrics import Scorecard, score_run
from scoring.stats import cell_stats

log = logging.getLogger("scoring.score")


def _iter_run_records(results_dir: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(results_dir.rglob("*.jsonl")):
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def score_all(*, runs_root: Path, results_root: Path) -> list[Scorecard]:
    cards: list[Scorecard] = []
    for rec in _iter_run_records(results_root):
        try:
            card = score_run(rec, runs_root=runs_root)
        except FileNotFoundError as exc:
            log.error("skipping run %s (missing): %s", rec.get("run_id"), exc)
            continue
        cards.append(card)
    return cards


def aggregate_leaderboard(scorecards: Iterable[Scorecard]) -> dict[str, Any]:
    """Aggregate per-cell mean metrics over (condition, model, composition)."""
    by_cell: dict[tuple[str, str, str], list[Scorecard]] = defaultdict(list)
    for s in scorecards:
        by_cell[(s.condition_code, s.model_id, s.composition)].append(s)
    cells: list[dict[str, Any]] = []
    for (cond, model, comp), bucket in sorted(by_cell.items()):
        # Faulty missions only for accuracy/onset; full bucket for cost/tool calls.
        faulty = [s for s in bucket if not s.is_clean_mission]
        clean = [s for s in bucket if s.is_clean_mission]
        stats = cell_stats(
            [s.root_cause_correct for s in faulty],
            [s.root_cause_correct for s in clean],
        )
        cells.append(
            {
                "condition_code": cond,
                "model_id": model,
                "composition": comp,
                "n": len(bucket),
                "n_faulty": len(faulty),
                "root_cause_accuracy": _mean_bool([s.root_cause_correct for s in faulty]),
                # Correct on BOTH faulty (right fault) and clean (correct abstain);
                # rewards calibration and penalises false alarms.
                "overall_accuracy": _mean_bool([s.root_cause_correct for s in bucket]),
                # Correct-abstention rate on clean missions (1 - false-alarm rate).
                "clean_mission_accuracy": _mean_bool([s.root_cause_correct for s in clean]),
                "cross_vendor_attribution_accuracy": _mean_bool(
                    [
                        s.cross_vendor_attribution_correct
                        for s in faulty
                        if s.cross_vendor_attribution_correct is not None
                    ]
                ),
                "time_of_onset_error_s_mean": _mean_float(
                    [s.time_of_onset_error_s for s in faulty if s.time_of_onset_error_s is not None]
                ),
                "hallucination_total_mean": _mean_float(
                    [float(s.hallucination.total) for s in bucket]
                ),
                "tool_call_count_mean": _mean_float([float(s.tool_call_count) for s in bucket]),
                "usd_cost_mean": _mean_float([s.usd_cost for s in bucket]),
                "usd_cost_total": round(sum(s.usd_cost for s in bucket), 6),
                # Efficiency / scalability axes (back-filled from every record).
                "latency_s_mean": _mean_float([s.latency_s for s in bucket]),
                "prompt_tokens_mean": _mean_float([float(s.prompt_tokens) for s in bucket]),
                # Four-way detection breakdown + bootstrap 95% CIs (found/missed/
                # false-alarm/correct-abstain, and intervals on recall/spec/balanced).
                **stats.to_dict(),
            }
        )
    return {"cells": cells, "n_runs_total": sum(c["n"] for c in cells)}


def write_outputs(
    *,
    scorecards: list[Scorecard],
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "scorecards.jsonl").open("w", encoding="utf-8") as f:
        for s in scorecards:
            f.write(json.dumps(s.to_dict(), sort_keys=True))
            f.write("\n")

    leaderboard = aggregate_leaderboard(scorecards)
    with (out_dir / "leaderboard.json").open("w", encoding="utf-8") as f:
        json.dump(leaderboard, f, indent=2, sort_keys=True)
        f.write("\n")

    deltas = compute_composition_deltas(scorecards)
    csv_path = out_dir / "composition_delta.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "condition_code",
                "model_id",
                "metric",
                "single_vendor_value",
                "multi_vendor_value",
                "delta",
                "single_vendor_n",
                "multi_vendor_n",
            ]
        )
        for d in deltas:
            writer.writerow(
                [
                    d.condition_code,
                    d.model_id,
                    d.metric,
                    d.single_vendor_value,
                    d.multi_vendor_value,
                    d.delta,
                    d.single_vendor_n,
                    d.multi_vendor_n,
                ]
            )

    _write_detection_breakdown_csv(out_dir / "detection_breakdown.csv", leaderboard["cells"])


def _fmt_ci(ci: dict[str, Any] | None) -> tuple[str, str, str]:
    """Point / lo / hi as strings for CSV, blank when the CI is undefined."""
    if not ci:
        return "", "", ""
    return f"{ci['point']:.4f}", f"{ci['lo']:.4f}", f"{ci['hi']:.4f}"


def _write_detection_breakdown_csv(path: Path, cells: list[dict[str, Any]]) -> None:
    """Paper-ready four-way breakdown + bootstrap 95% CIs, one row per cell."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "condition_code",
                "model_id",
                "composition",
                "found",
                "missed",
                "false_alarm",
                "correct_abstain",
                "n_faulty",
                "n_clean",
                "recall",
                "recall_lo",
                "recall_hi",
                "specificity",
                "specificity_lo",
                "specificity_hi",
                "balanced_acc",
                "balanced_lo",
                "balanced_hi",
            ]
        )
        for c in cells:
            bd = c.get("detection_breakdown", {})
            rp, rlo, rhi = _fmt_ci(c.get("recall_ci"))
            sp, slo, shi = _fmt_ci(c.get("specificity_ci"))
            bp, blo, bhi = _fmt_ci(c.get("balanced_accuracy_ci"))
            writer.writerow(
                [
                    c["condition_code"],
                    c["model_id"],
                    c["composition"],
                    bd.get("found", ""),
                    bd.get("missed", ""),
                    bd.get("false_alarm", ""),
                    bd.get("correct_abstain", ""),
                    bd.get("n_faulty", ""),
                    bd.get("n_clean", ""),
                    rp,
                    rlo,
                    rhi,
                    sp,
                    slo,
                    shi,
                    bp,
                    blo,
                    bhi,
                ]
            )


def _mean_bool(xs: list[bool | None]) -> float | None:
    filtered = [1.0 if x else 0.0 for x in xs if x is not None]
    return None if not filtered else round(sum(filtered) / len(filtered), 6)


def _mean_float(xs: list[float | None]) -> float | None:
    filtered = [float(x) for x in xs if x is not None]
    return None if not filtered else round(sum(filtered) / len(filtered), 6)


# ---------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score udm-bench runs")
    parser.add_argument("--runs", required=True, type=Path, help="path to runs/ root")
    parser.add_argument("--results", required=True, type=Path, help="path to results/ root")
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s | %(message)s"
    )

    cards = score_all(runs_root=args.runs, results_root=args.results)
    if not cards:
        print("no scorecards produced (empty results or missing ground truth)", file=sys.stderr)
        return 1
    write_outputs(scorecards=cards, out_dir=args.out)
    print(f"scored {len(cards)} runs → {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
