"""Hallucination detector precision gate.

Loads the hand-labelled corpus and asserts the automated detector achieves
precision >= 0.85 against the labels. The corpus spans all four hallucination
categories (event_id, field_path, standard, vendor_misattribution) plus
grounded/clean and heuristic-boundary cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faults.base import InjectionRecord
from scoring.hallucination import detect_hallucinations

CORPUS_PATH = Path(__file__).parent / "data" / "hallucination_corpus.jsonl"
PRECISION_GATE = 0.85
MIN_RECORDS = 30


def _load_corpus():
    records = []
    with CORPUS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def test_corpus_exists_and_is_large_enough():
    records = _load_corpus()
    assert len(records) >= MIN_RECORDS


def test_corpus_records_are_well_formed():
    for rec in _load_corpus():
        assert "run_record" in rec
        assert "ground_truth" in rec
        labels = rec["labels"]
        assert set(labels) == {"event_ids", "field_paths", "standards", "vendor_misattribution"}


def test_detector_meets_precision_gate():
    records = _load_corpus()
    tp = fp = fn = 0
    for rec in records:
        ground_truth = [InjectionRecord(**g) for g in rec["ground_truth"]]
        report = detect_hallucinations(run_record=rec["run_record"], ground_truth=ground_truth)
        labels = rec["labels"]
        for category in ("event_ids", "field_paths", "standards"):
            flagged = set(getattr(report, category))
            labelled = set(labels[category])
            tp += len(flagged & labelled)
            fp += len(flagged - labelled)
            fn += len(labelled - flagged)
        flagged_vendor = report.vendor_misattribution
        labelled_vendor = bool(labels["vendor_misattribution"])
        tp += int(flagged_vendor and labelled_vendor)
        fp += int(flagged_vendor and not labelled_vendor)
        fn += int(labelled_vendor and not flagged_vendor)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    assert precision >= PRECISION_GATE, (
        f"detector precision {precision:.3f} below gate {PRECISION_GATE} (tp={tp} fp={fp})"
    )
    # Sanity: the corpus must actually exercise the detector's positive paths.
    assert tp >= 15
    assert recall > 0.0


@pytest.mark.parametrize("category", ["event_ids", "field_paths", "standards"])
def test_corpus_covers_each_hallucination_category(category):
    records = _load_corpus()
    assert any(rec["labels"][category] for rec in records), f"no corpus coverage for {category}"


def test_corpus_covers_vendor_misattribution():
    records = _load_corpus()
    assert any(rec["labels"]["vendor_misattribution"] for rec in records)
