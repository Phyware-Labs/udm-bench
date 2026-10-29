"""Harness execution loop + CLI entrypoint.

Runs one ``(model, condition, mission)`` triple and emits the canonical
per-run JSON record into ``results/<run_id>.jsonl``.

Usage::

    python -m harness.run \\
        --mission runs/single_tb3_warehouse_nav-abc123 \\
        --condition C \\
        --model mock \\
        --results-root results/

The recorded artifact captures the tool-call
trace, the model output, the latency, the prompt + completion tokens, and
the dollar cost.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from harness.backends import (
    BackendError,
    ModelOutput,
    ToolCall,
    Usage,
    get_backend,
)
from harness.backends import (
    mock as _mock_backend,  # noqa: F401 — register the mock backend
)
from harness.conditions import get_condition
from harness.conditions.base import ToolResult
from harness.prompts import CURRENT_VERSION as PROMPT_TEMPLATE_VERSION

log = logging.getLogger("harness.run")

# Hard cap on the agent loop. Each step is one model turn; tool-call results
# are fed back into the next step.
MAX_AGENT_STEPS_DEFAULT = 20

# Some models (notably gpt-5) end a run in prose without ever calling
# submit_diagnosis, which scored as a non-answer and confounded calibration
# metrics. When a run terminates with no tool call and no diagnosis yet, nudge it
# (bounded) to finalize through the answer channel. Every condition's prompt
# already instructs concluding with submit_diagnosis, so this is a reminder, not
# new guidance, and it never supplies a fault label.
MAX_SUBMIT_NUDGES = 2
_SUBMIT_NUDGE = (
    "You have not called submit_diagnosis yet. You MUST finalize by calling the "
    "submit_diagnosis tool now with your best fault_id (or 'no_fault' if the "
    "mission was clean), the vendor/source_id, the mission-relative onset time, "
    "and any supporting event_ids. Do not answer in prose."
)


@dataclass(frozen=True)
class ToolCallRecord:
    """One step of the agent loop."""

    step: int
    tool_call: dict[str, Any]
    tool_result: dict[str, Any]
    is_diagnosis: bool


@dataclass
class RunRecord:
    """Canonical per-run JSON record."""

    run_id: str
    mission_id: str
    condition_code: str
    model_id: str
    seed: int
    prompt_template_version: str
    composition: str
    vendors: list[str]
    started_at_unix: float
    finished_at_unix: float
    latency_ms: int
    steps: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    final_diagnosis: dict[str, Any] | None = None
    final_content: str = ""
    usage: dict[str, Any] = field(default_factory=lambda: asdict(Usage(0, 0, 0.0)))
    submit_nudges: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_one(
    *,
    mission_dir: Path,
    condition_code: str,
    model_id: str,
    backend_kwargs: dict[str, Any] | None = None,
    seed: int = 0,
    max_steps: int = MAX_AGENT_STEPS_DEFAULT,
    prompt_template_version: str = PROMPT_TEMPLATE_VERSION,
) -> RunRecord:
    """Run one (mission, condition, model) triple to completion."""
    meta_path = mission_dir / "mission_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(meta_path)
    with meta_path.open("r", encoding="utf-8") as f:
        mission_meta = json.load(f)
    mission_id = str(mission_meta.get("mission_id", mission_dir.name))

    condition = get_condition(condition_code)
    backend = get_backend(model_id, **(backend_kwargs or {}))
    tools = condition.tool_specs()
    system_prompt = condition.system_prompt()
    initial_message = condition.initial_user_message(mission_meta=mission_meta)
    # Deterministic, harness-issued orientation: give
    # conditions that can enumerate their store a topology summary so the agent
    # starts oriented instead of guessing source ids / event types. Costs no
    # model turn and is best-effort (never fails the run).
    preamble = condition.orientation_preamble(
        mission_dir=str(mission_dir), mission_meta=mission_meta
    )
    if preamble:
        initial_message = f"{preamble}\n\n{initial_message}"
    messages: list[dict[str, Any]] = [{"role": "user", "content": initial_message}]

    record = RunRecord(
        run_id=f"{mission_id}_{condition.code}_{model_id}_{uuid.uuid4().hex[:8]}",
        mission_id=mission_id,
        condition_code=condition.code,
        model_id=model_id,
        seed=seed,
        prompt_template_version=prompt_template_version,
        composition=str(mission_meta.get("composition", "")),
        vendors=list(mission_meta.get("vendors", [])),
        started_at_unix=time.time(),
        finished_at_unix=0.0,
        latency_ms=0,
        steps=0,
    )
    total_in = total_out = total_cached = 0
    total_usd = 0.0
    t0 = time.perf_counter()

    try:
        for step in range(max_steps):
            output = _generate_with_backoff(
                backend=backend, system_prompt=system_prompt, messages=messages, tools=tools
            )
            total_in += output.usage.prompt_tokens
            total_out += output.usage.completion_tokens
            total_cached += output.usage.cached_prompt_tokens
            total_usd += output.usage.usd_cost
            record.steps = step + 1
            messages.append(
                {
                    "role": "assistant",
                    "content": output.content,
                    "tool_calls": [tc.to_dict() for tc in output.tool_calls],
                }
            )

            if not output.tool_calls:
                # Model produced a terminal natural-language reply with no tool
                # call. If it never submitted a diagnosis, nudge it (bounded) to
                # finalize through the answer channel instead of trailing off.
                if record.final_diagnosis is None and record.submit_nudges < MAX_SUBMIT_NUDGES:
                    record.submit_nudges += 1
                    messages.append({"role": "user", "content": _SUBMIT_NUDGE})
                    continue
                record.final_content = output.content
                break

            tool_results: list[ToolResult] = []
            diagnosis_seen = False
            for tc in output.tool_calls:
                result = condition.execute_tool(tc, mission_dir=str(mission_dir))
                record.tool_calls.append(
                    ToolCallRecord(
                        step=step + 1,
                        tool_call=tc.to_dict(),
                        tool_result={"content": result.content, "is_error": result.is_error},
                        is_diagnosis=(tc.name == "submit_diagnosis"),
                    ).__dict__
                )
                if tc.name == "submit_diagnosis":
                    record.final_diagnosis = dict(tc.arguments)
                    diagnosis_seen = True
                tool_results.append(result)

            # Feed tool results back as a single user message.
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        [
                            {"name": r.name, "content": r.content, "is_error": r.is_error}
                            for r in tool_results
                        ]
                    ),
                }
            )

            if diagnosis_seen:
                record.final_content = output.content
                break
    except BackendError as exc:
        record.error = f"BackendError: {exc}"
        log.error("run failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        record.error = f"{type(exc).__name__}: {exc}"
        log.exception("run crashed")

    record.finished_at_unix = time.time()
    record.latency_ms = int((time.perf_counter() - t0) * 1000)
    record.usage = asdict(
        Usage(
            prompt_tokens=total_in,
            completion_tokens=total_out,
            usd_cost=total_usd,
            cached_prompt_tokens=total_cached,
        )
    )
    return record


@retry(
    retry=retry_if_exception_type(BackendError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=0.5, min=1.0, max=30.0),
    reraise=True,
)
def _generate_with_backoff(
    *,
    backend: Any,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> ModelOutput:
    return backend.generate(system_prompt=system_prompt, messages=messages, tools=tools)


# ---------------------------------------------------------------------- helpers


def append_jsonl(path: Path, record: RunRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict(), sort_keys=True))
        f.write("\n")


# Re-exported for users who need to construct mock responses in tests.
__all__ = [
    "MAX_AGENT_STEPS_DEFAULT",
    "RunRecord",
    "ToolCall",
    "ToolCallRecord",
    "append_jsonl",
    "run_one",
]


# ---------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one (mission, condition, model) triple")
    parser.add_argument(
        "--mission", required=True, type=Path, help="path to a runs/<mission_id>/ directory"
    )
    parser.add_argument("--condition", required=True, help="condition code (A–F)")
    parser.add_argument("--model", required=True, help="model id (registered backend)")
    parser.add_argument("--results-root", type=Path, default=Path("results"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=MAX_AGENT_STEPS_DEFAULT)
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s | %(message)s"
    )

    record = run_one(
        mission_dir=args.mission,
        condition_code=args.condition,
        model_id=args.model,
        seed=args.seed,
        max_steps=args.max_steps,
    )
    out_path = args.results_root / f"{record.run_id}.jsonl"
    append_jsonl(out_path, record)
    if record.error:
        print(f"run completed with error: {record.error}  artifact={out_path}", file=sys.stderr)
        return 2
    print(
        f"run complete: {record.run_id}  diagnosis={bool(record.final_diagnosis)}  artifact={out_path}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
