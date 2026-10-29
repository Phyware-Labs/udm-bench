"""udm-bench scoring harness.

Modules:
  - scoring.metrics             — per-run scorecard math
  - scoring.hallucination       — automated hallucination detector
  - scoring.composition_delta   — single-vs-multi-vendor delta tables
  - scoring.score               — CLI entrypoint
"""

from scoring.composition_delta import compute_composition_deltas
from scoring.hallucination import HallucinationReport, detect_hallucinations
from scoring.metrics import Scorecard, score_run

__all__ = [
    "HallucinationReport",
    "Scorecard",
    "compute_composition_deltas",
    "detect_hallucinations",
    "score_run",
]
