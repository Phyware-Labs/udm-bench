"""Per-run scoring math.

Inputs:
  * One harness ``RunRecord`` (as dict) from ``results/<run_id>.jsonl``
  * The corresponding ``runs/<mission_id>/ground_truth.json`` parsed into
    :class:`InjectionRecord` objects via :func:`faults.ground_truth.load_ground_truth`

Output: :class:`Scorecard` with every metric.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from faults.base import InjectionRecord
from faults.ground_truth import load_ground_truth
from scoring.hallucination import HallucinationReport, detect_hallucinations


@dataclass(frozen=True)
class Scorecard:
    run_id: str
    mission_id: str
    condition_code: str
    model_id: str
    composition: str  # "single-vendor" | "multi-vendor"
    is_clean_mission: bool
    root_cause_correct: bool | None  # None for clean missions if no diagnosis was demanded
    cross_vendor_attribution_correct: bool | None  # None for single-vendor
    time_of_onset_error_s: float | None
    hallucination: HallucinationReport
    tool_call_count: int
    usd_cost: float
    submitted_diagnosis: bool
    # Efficiency axes — recorded on every run, so fully back-fillable for past
    # result sets. Context volume (prompt tokens) is the reproducible cost/speed
    # driver; wall-clock latency is illustrative (varies with API load/retries).
    latency_s: float = 0.0
    prompt_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "hallucination": self.hallucination.to_dict()}


# Optional sentinel meaning "I detected no fault" so clean-mission scoring
# can distinguish a calibrated answer from an unfilled one.
NO_FAULT_FAULT_ID = "no_fault"

# Upper bound (seconds) on a plausible mission-relative onset estimate. Missions
# run for a few minutes, so any claimed onset beyond this is a unit error — most
# commonly a model emitting an absolute Unix epoch instead of a mission-relative
# offset. Such values are dropped (``time_of_onset_error_s = None``) rather than
# allowed to corrupt the aggregate onset error.
MAX_PLAUSIBLE_ONSET_S = 3600.0


def score_run(
    run_record: dict[str, Any],
    ground_truth: list[InjectionRecord] | None = None,
    *,
    runs_root: Path | None = None,
) -> Scorecard:
    """Score one harness run."""
    if ground_truth is None:
        if runs_root is None:
            raise ValueError("provide either ground_truth or runs_root")
        gt_path = runs_root / run_record["mission_id"] / "ground_truth.json"
        ground_truth = load_ground_truth(gt_path) if gt_path.exists() else []

    is_clean = len(ground_truth) == 0
    composition = str(run_record.get("composition", ""))
    diagnosis = run_record.get("final_diagnosis")
    submitted = diagnosis is not None
    tool_calls = run_record.get("tool_calls", [])

    # Root-cause accuracy
    if is_clean:
        # The agent is correct iff it either declined to submit a diagnosis OR
        # explicitly attributed to NO_FAULT_FAULT_ID. Either is a calibrated
        # response to a clean mission.
        if not submitted:
            root_cause_correct: bool | None = True
        else:
            root_cause_correct = str(diagnosis.get("fault_id", "")) == NO_FAULT_FAULT_ID
    elif not submitted:
        root_cause_correct = False
    else:
        truth_ids = {gt.fault_id for gt in ground_truth}
        root_cause_correct = str(diagnosis.get("fault_id", "")) in truth_ids

    # Cross-vendor attribution accuracy (multi-vendor missions only)
    cross_vendor_correct: bool | None
    if composition != "multi-vendor" or is_clean:
        cross_vendor_correct = None
    elif not submitted:
        cross_vendor_correct = False
    else:
        truth_vendors = {gt.vendor for gt in ground_truth}
        cross_vendor_correct = str(diagnosis.get("vendor", "")) in truth_vendors

    # Time-of-onset accuracy
    time_err: float | None
    if is_clean or not submitted:
        time_err = None
    else:
        claimed = float(diagnosis.get("claimed_onset_time_s", 0.0))
        # Reject implausible onsets (e.g. an absolute epoch instead of a
        # mission-relative offset) so one bad value cannot corrupt the aggregate.
        if not math.isfinite(claimed) or not (0.0 <= claimed <= MAX_PLAUSIBLE_ONSET_S):
            time_err = None
        else:
            # Smallest delta across all injections in the mission (handles
            # multi-fault future expansion gracefully).
            time_err = min(abs(claimed - gt.injection_time) for gt in ground_truth)

    halluc = detect_hallucinations(run_record=run_record, ground_truth=ground_truth)
    cost = float(run_record.get("usage", {}).get("usd_cost", 0.0))
    latency_s = float(run_record.get("latency_ms", 0.0)) / 1000.0
    prompt_tokens = int(run_record.get("usage", {}).get("prompt_tokens", 0) or 0)

    return Scorecard(
        run_id=str(run_record.get("run_id", "")),
        mission_id=str(run_record.get("mission_id", "")),
        condition_code=str(run_record.get("condition_code", "")),
        model_id=str(run_record.get("model_id", "")),
        composition=composition,
        is_clean_mission=is_clean,
        root_cause_correct=root_cause_correct,
        cross_vendor_attribution_correct=cross_vendor_correct,
        time_of_onset_error_s=time_err,
        hallucination=halluc,
        tool_call_count=len(tool_calls),
        usd_cost=cost,
        submitted_diagnosis=submitted,
        latency_s=latency_s,
        prompt_tokens=prompt_tokens,
    )
