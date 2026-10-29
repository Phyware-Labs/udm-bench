"""Tests for the spend-logging tool (scoring.spend)."""

from __future__ import annotations

import json

import pytest

from scoring import spend


def _write_run(path, *, model_id, usd, pin=1000, pout=100):
    path.write_text(
        json.dumps(
            {
                "model_id": model_id,
                "usage": {"prompt_tokens": pin, "completion_tokens": pout, "usd_cost": usd},
            }
        ),
        encoding="utf-8",
    )


def test_provider_for():
    assert spend.provider_for("azure-gpt-5") == ("Azure OpenAI", True)
    assert spend.provider_for("azure-gpt-5-mini") == ("Azure OpenAI", True)
    assert spend.provider_for("claude-opus-4-7") == ("Anthropic", False)
    assert spend.provider_for("qwen3-coder") == ("OpenRouter", False)
    assert spend.provider_for("gpt-5") == ("OpenAI", False)


def test_aggregate_sums_by_model(tmp_path):
    _write_run(tmp_path / "a.jsonl", model_id="azure-gpt-5-mini", usd=0.10)
    _write_run(tmp_path / "b.jsonl", model_id="azure-gpt-5-mini", usd=0.20)
    _write_run(tmp_path / "c.jsonl", model_id="azure-gpt-5", usd=1.00)
    agg = spend.aggregate(tmp_path)
    assert agg["azure-gpt-5-mini"].runs == 2
    assert agg["azure-gpt-5-mini"].usd == pytest.approx(0.30)
    assert agg["azure-gpt-5"].runs == 1


def test_aggregate_skips_corrupt_file(tmp_path):
    _write_run(tmp_path / "ok.jsonl", model_id="azure-gpt-5-mini", usd=0.10)
    (tmp_path / "partial.jsonl").write_text('{"model_id": "x", "usage":', encoding="utf-8")
    agg = spend.aggregate(tmp_path)
    assert set(agg) == {"azure-gpt-5-mini"}


def test_credit_row_keeps_out_of_pocket_zero():
    row = spend._row(
        "azure-gpt-5-mini", spend.ModelSpend(runs=5, usd=1.23), day="2026-06-24", note="slice"
    )
    # Cost column is $0.00 for credit-covered Azure; credit amount in notes.
    assert "| $0.00 |" in row
    assert "$1.23 on credit" in row
    assert "5 runs" in row


def test_update_budget_inserts_rows_and_totals(tmp_path):
    budget = tmp_path / "BUDGET.md"
    budget.write_text(
        "# spend\n\n"
        "| Date | Provider | Model | Runs | Cost (USD) | Notes |\n"
        "| ---- | -------- | ----- | ---: | ---------: | ----- |\n"
        "| 2026-06-23 | Anthropic | claude | 1 | $2.50 | prior |\n"
        "\n"
        "**Running total: $2.50**\n",
        encoding="utf-8",
    )
    rows = [
        "| 2026-06-24 | Anthropic | claude | 2 | $1.50 | new |",
        "| 2026-06-24 | Azure OpenAI | azure-gpt-5-mini | 5 | $0.00 | credit |",
    ]
    total = spend.update_budget(budget, rows)
    assert total == 4.00  # 2.50 + 1.50 + 0.00
    text = budget.read_text(encoding="utf-8")
    assert "azure-gpt-5-mini" in text
    assert "**Running total: $4.00**" in text
    # The new rows are inside the table, above the running-total line.
    assert text.index("| 2026-06-24 | Anthropic") < text.index("**Running total")
