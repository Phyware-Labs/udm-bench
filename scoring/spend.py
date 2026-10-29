"""Aggregate recorded run costs and append them to the BUDGET.md ledger.

The harness records a per-run ``usage.usd_cost`` in every results JSONL. This
module sums those by model and appends a dated row per model to the cloud-spend
table in ``BUDGET.md``, keeping the running out-of-pocket total accurate.

Azure GPT spend is covered by subscription credit, so for Azure models the
out-of-pocket ``Cost`` column stays ``$0.00`` and the credit amount is recorded
in the ``Notes`` column (matching the file's logging convention).

Usage::

    python -m scoring.spend --results-root results_live --note "Phase 2 A/B slice"
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path


@dataclass
class ModelSpend:
    runs: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usd: float = 0.0


# model-id prefix -> (provider label, covered-by-credit?)
_PROVIDERS: tuple[tuple[str, str, bool], ...] = (
    ("azure-", "Azure OpenAI", True),
    ("claude-", "Anthropic", False),
    ("qwen", "OpenRouter", False),
    ("gpt-", "OpenAI", False),
    ("mock", "mock", False),
)


def provider_for(model_id: str) -> tuple[str, bool]:
    for prefix, label, credit in _PROVIDERS:
        if model_id.startswith(prefix):
            return label, credit
    return "unknown", False


def aggregate(results_root: Path) -> dict[str, ModelSpend]:
    """Sum runs + tokens + usd per model across ``results_root/*.jsonl``."""
    out: dict[str, ModelSpend] = {}
    for f in sorted(results_root.glob("*.jsonl")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # skip partially-written files mid-run
        mid = str(rec.get("model_id", "unknown"))
        usage = rec.get("usage", {})
        s = out.setdefault(mid, ModelSpend())
        s.runs += 1
        s.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        s.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        s.usd += float(usage.get("usd_cost", 0.0) or 0.0)
    return out


def _row(model_id: str, spend: ModelSpend, *, day: str, note: str) -> str:
    provider, credit = provider_for(model_id)
    out_of_pocket = 0.0 if credit else spend.usd
    note_parts = [note] if note else []
    if credit:
        note_parts.append(f"~${spend.usd:.2f} on credit, $0 out-of-pocket")
    note_parts.append(f"{spend.runs} runs")
    note_text = "; ".join(p for p in note_parts if p)
    return (
        f"| {day} | {provider} | {model_id} | {spend.runs} | ${out_of_pocket:.2f} | {note_text} |"
    )


_COST_RE = re.compile(r"\$([0-9]+(?:\.[0-9]+)?)")


def _running_total(table_rows: list[str]) -> float:
    """Sum the numeric Cost column (5th cell) across data rows."""
    total = 0.0
    for row in table_rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        m = _COST_RE.search(cells[4])
        if m:
            total += float(m.group(1))
    return total


def update_budget(budget_path: Path, new_rows: list[str]) -> float:
    """Insert ``new_rows`` into the spend table and rewrite the running total.

    Returns the new running (out-of-pocket) total.
    """
    lines = budget_path.read_text(encoding="utf-8").splitlines()

    # Locate the table: the header row, its separator, then contiguous data
    # rows (lines starting with ``|``).
    header_idx = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("| Date"))
    data_start = header_idx + 2  # skip header + separator
    data_end = data_start
    while data_end < len(lines) and lines[data_end].lstrip().startswith("|"):
        data_end += 1

    data_rows = lines[data_start:data_end] + new_rows
    total = _running_total(data_rows)

    rebuilt = lines[:data_end] + new_rows + lines[data_end:]
    # Update the running-total line.
    for i, ln in enumerate(rebuilt):
        if ln.startswith("**Running total"):
            rebuilt[i] = (
                f"**Running total: ${total:.2f}** "
                "(out-of-pocket; Azure GPT spend is credit-covered)"
            )
            break

    budget_path.write_text("\n".join(rebuilt) + "\n", encoding="utf-8")
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log recorded run spend to BUDGET.md")
    parser.add_argument("--results-root", required=True, type=Path)
    parser.add_argument("--budget", type=Path, default=Path("BUDGET.md"))
    parser.add_argument("--note", default="", help="free-text note for the ledger rows")
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument(
        "--dry-run", action="store_true", help="print the rows without editing BUDGET.md"
    )
    args = parser.parse_args(argv)

    spend = aggregate(args.results_root)
    if not spend:
        print(f"no result records under {args.results_root}")
        return 0
    rows = [_row(mid, spend[mid], day=args.date, note=args.note) for mid in sorted(spend)]
    total_usd = sum(s.usd for s in spend.values())
    for r in rows:
        print(r)
    print(
        f"# aggregate credit spend: ${total_usd:.4f} across {sum(s.runs for s in spend.values())} runs"
    )
    if not args.dry_run:
        new_total = update_budget(args.budget, rows)
        print(f"# BUDGET.md running (out-of-pocket) total: ${new_total:.2f}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
