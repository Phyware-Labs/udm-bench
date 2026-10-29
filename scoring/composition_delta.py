"""Same-vs-multi-vendor delta tables.

The headline result table of the benchmark: for each (condition, model)
pair, compute the multi-vendor minus single-vendor delta for every metric.

Produces a list of :class:`CompositionDelta` rows that the leaderboard
renderer can serialize to CSV.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from scoring.metrics import Scorecard


@dataclass(frozen=True)
class CompositionDelta:
    condition_code: str
    model_id: str
    metric: str
    single_vendor_value: float
    multi_vendor_value: float
    delta: float  # multi - single
    single_vendor_n: int
    multi_vendor_n: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_METRIC_EXTRACTORS = {
    "root_cause_accuracy": lambda s: _bool_to_float(s.root_cause_correct),
    "time_of_onset_error_s": lambda s: _none_to_nan(s.time_of_onset_error_s),
    "hallucination_total": lambda s: float(s.hallucination.total),
    "tool_call_count": lambda s: float(s.tool_call_count),
    "usd_cost": lambda s: float(s.usd_cost),
}


def compute_composition_deltas(scorecards: Iterable[Scorecard]) -> list[CompositionDelta]:
    """Compute (multi − single)-vendor deltas per (condition, model, metric)."""
    by_cell: dict[tuple[str, str, str], list[Scorecard]] = defaultdict(list)
    for s in scorecards:
        if s.is_clean_mission:
            continue  # clean missions don't have root-cause / onset metrics
        by_cell[(s.condition_code, s.model_id, s.composition)].append(s)

    out: list[CompositionDelta] = []
    # Group by (condition, model) and produce a row per metric.
    pairs: set[tuple[str, str]] = {(c, m) for (c, m, _) in by_cell}
    for cond, model in sorted(pairs):
        single = by_cell.get((cond, model, "single-vendor"), [])
        multi = by_cell.get((cond, model, "multi-vendor"), [])
        if not single or not multi:
            continue  # no delta possible
        for metric_name, extractor in _METRIC_EXTRACTORS.items():
            s_vals = _filter_nan([extractor(s) for s in single])
            m_vals = _filter_nan([extractor(s) for s in multi])
            if not s_vals or not m_vals:
                continue
            s_mean = sum(s_vals) / len(s_vals)
            m_mean = sum(m_vals) / len(m_vals)
            out.append(
                CompositionDelta(
                    condition_code=cond,
                    model_id=model,
                    metric=metric_name,
                    single_vendor_value=round(s_mean, 6),
                    multi_vendor_value=round(m_mean, 6),
                    delta=round(m_mean - s_mean, 6),
                    single_vendor_n=len(s_vals),
                    multi_vendor_n=len(m_vals),
                )
            )
    return out


def _bool_to_float(v: bool | None) -> float:
    if v is None:
        return float("nan")
    return 1.0 if v else 0.0


def _none_to_nan(v: float | None) -> float:
    return float("nan") if v is None else float(v)


def _filter_nan(xs: list[float]) -> list[float]:
    return [x for x in xs if x == x]  # NaN != NaN
