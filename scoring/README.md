# `scoring/` — scoring harness

Reduces `results/*.jsonl` + `runs/<mission_id>/` into per-run scorecards, an
aggregate leaderboard, and the single- vs multi-vendor delta CSV. This is the
code that scored every run in the paper; the scored outputs are committed under
`scoring_results_*/`.

## Metrics

| Metric                                  | Type                              |
| --------------------------------------- | --------------------------------- |
| `root_cause_correct`                    | Binary                            |
| `cross_vendor_attribution_correct`      | Binary (multi-vendor missions)    |
| `time_of_onset_error_s`                 | Continuous (seconds)              |
| `hallucination.event_ids`               | Count                             |
| `hallucination.field_paths`             | Count                             |
| `hallucination.standards`               | Count                             |
| `hallucination.vendor_misattribution`   | Boolean (multi-vendor)            |
| `tool_call_count`                       | Integer                           |
| `usd_cost`                              | Dollar (sum across the agent loop)|

## Usage

```bash
python -m scoring.score --runs runs/ --results results/ --out scoring_out/
```

Outputs into `scoring_out/`:

* `scorecards.jsonl`        — one scorecard per run
* `leaderboard.json`        — aggregated (condition × model × composition) cells
* `composition_delta.csv`   — paper-ready same-vs-multi delta table

## Single- vs multi-vendor delta

For each `(condition, model)` pair, the delta table reports the multi-vendor
minus single-vendor value of every metric. The benchmark's original hypothesis
was that UDM conditions show a smaller delta than the baselines. The paper's
mission set cannot test it because the two compositions differ in fault mix; see
[`analysis/multi_vendor_delta.md`](../analysis/multi_vendor_delta.md).

## Hallucination detector

`scoring.hallucination` categorises hallucinations into:

| Type                       | Example                                     |
| -------------------------- | ------------------------------------------- |
| `event_id`                 | Cited `evt_abc12345` that was never returned by a tool call |
| `field_path`               | Cited `payload.imaginary_field`             |
| `standard`                 | Cited "ISO 21448" without calling `compliance_audit` |
| `vendor_misattribution`    | Attributed a TB3 fault to the PX4 drone     |

A hand-labelled corpus (≥30 known-hallucinated outputs) lives under
`tests/scoring/data/` and gates the detector at precision ≥ 0.85.
