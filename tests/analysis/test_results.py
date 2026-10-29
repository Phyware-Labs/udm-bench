"""Smoke test: the Phase 4 analysis regenerates from the committed snapshot."""

from __future__ import annotations

import functools

from analysis import paired, results


def test_results_regenerate_from_snapshot(tmp_path, monkeypatch):
    # Fewer bootstrap resamples keeps this fast; the real run uses 10 000.
    monkeypatch.setattr(results, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(
        results,
        "paired_bootstrap_diff",
        functools.partial(paired.paired_bootstrap_diff, resamples=50),
    )
    monkeypatch.setattr(
        results,
        "stratified_bootstrap",
        functools.partial(paired.stratified_bootstrap, resamples=50),
    )
    assert results.main() == 0

    tables = (tmp_path / "tables.md").read_text(encoding="utf-8")
    # Headline cells the paper reports must survive regeneration unchanged.
    assert "| gpt-5 | C UDM+health_scan | all | 47 | 10/23 | 6/24 |" in tables
    assert "| gpt-5-mini | C UDM+health_scan | all | 47 | 11/23 | 22/24 |" in tables
    assert "| **all** |  | **16/23** |" in tables
    for name in ("matrix", "paired_mcnemar", "composition_delta", "failure_taxonomy"):
        assert (tmp_path / f"{name}.csv").exists()
    assert (tmp_path / "fig_per_fault.tex").read_text().startswith("% AUTO-GENERATED")
