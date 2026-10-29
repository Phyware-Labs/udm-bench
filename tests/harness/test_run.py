"""Tests for the harness run loop (orchestrates condition × backend)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import run as run_mod
from harness.backends import ModelOutput, ToolCall, register_backend
from harness.backends.base import Backend, BackendError
from harness.backends.mock import MockBackend


def _make_mission(tmp_path: Path, *, composition: str = "single-vendor") -> Path:
    mission_id = "fixture-mission-0001"
    runs = tmp_path / "runs"
    mission_dir = runs / mission_id
    mission_dir.mkdir(parents=True)
    meta = {
        "mission_id": mission_id,
        "scenario_id": "fixture",
        "composition": composition,
        "vendors": ["tb3"] if composition == "single-vendor" else ["tb3", "px4"],
        "world": "small_warehouse",
        "seed": 1,
        "injections": [],
        "mission_template": {},
    }
    (mission_dir / "mission_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return mission_dir


def _register_scripted_backend(model_id: str, responses):
    register_backend(model_id, lambda **kw: MockBackend(responses=list(responses), **kw))


def test_run_one_submits_diagnosis(tmp_path):
    mission_dir = _make_mission(tmp_path)
    responses = [
        ModelOutput(
            content="diagnosing",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": "tb3_lidar_dropout",
                        "vendor": "turtlebot3",
                        "source_id": "tb3_0",
                        "claimed_onset_time_s": 12.0,
                    },
                ),
            ),
        ),
    ]
    _register_scripted_backend("mock-diag", responses)
    record = run_mod.run_one(
        mission_dir=mission_dir,
        condition_code="A",
        model_id="mock-diag",
    )
    assert record.final_diagnosis is not None
    assert record.final_diagnosis["fault_id"] == "tb3_lidar_dropout"
    assert record.tool_calls[0]["is_diagnosis"]
    assert record.error is None


def test_run_one_terminates_on_no_tool_call(tmp_path):
    mission_dir = _make_mission(tmp_path)
    # After the bounded submit nudges are exhausted, a persistent no-tool-call
    # prose reply terminates the run and its content is captured.
    responses = [
        ModelOutput(content="I don't have enough information.")
        for _ in range(run_mod.MAX_SUBMIT_NUDGES + 1)
    ]
    _register_scripted_backend("mock-nodiag", responses)
    record = run_mod.run_one(
        mission_dir=mission_dir,
        condition_code="A",
        model_id="mock-nodiag",
    )
    assert record.final_diagnosis is None
    assert record.final_content == "I don't have enough information."
    assert record.submit_nudges == run_mod.MAX_SUBMIT_NUDGES


def test_run_one_records_usage(tmp_path):
    mission_dir = _make_mission(tmp_path)
    responses = [
        ModelOutput(
            content="ok",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": "x",
                        "vendor": "y",
                        "source_id": "z",
                        "claimed_onset_time_s": 0.0,
                    },
                ),
            ),
        )
    ]
    register_backend(
        "mock-usage",
        lambda **kw: MockBackend(responses=list(responses), usd_per_run=0.25, **kw),
    )
    record = run_mod.run_one(
        mission_dir=mission_dir,
        condition_code="A",
        model_id="mock-usage",
    )
    assert record.usage["usd_cost"] > 0
    assert record.steps == 1


def test_run_one_handles_backend_error(tmp_path):
    mission_dir = _make_mission(tmp_path)

    class _Boom(Backend):
        model_id = "mock-boom"

        def generate(self, *, system_prompt, messages, tools):
            raise BackendError("nope")

    register_backend("mock-boom", lambda **kw: _Boom(**kw))
    record = run_mod.run_one(
        mission_dir=mission_dir,
        condition_code="A",
        model_id="mock-boom",
    )
    assert record.error is not None
    assert "nope" in record.error


def test_run_one_missing_meta_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_mod.run_one(
            mission_dir=tmp_path / "does_not_exist",
            condition_code="A",
            model_id="mock",
        )


def test_append_jsonl_writes_one_line(tmp_path):
    record = run_mod.RunRecord(
        run_id="r1",
        mission_id="m1",
        condition_code="A",
        model_id="mock",
        seed=0,
        prompt_template_version="v0",
        composition="single-vendor",
        vendors=["tb3"],
        started_at_unix=0.0,
        finished_at_unix=0.0,
        latency_ms=0,
        steps=0,
    )
    out = tmp_path / "results" / "r1.jsonl"
    run_mod.append_jsonl(out, record)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run_id"] == "r1"


def test_run_main_cli(tmp_path, capsys):
    mission_dir = _make_mission(tmp_path)
    responses = [
        ModelOutput(
            content="done",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": "tb3_lidar_dropout",
                        "vendor": "turtlebot3",
                        "source_id": "tb3_0",
                        "claimed_onset_time_s": 1.0,
                    },
                ),
            ),
        )
    ]
    register_backend("mock-cli", lambda **kw: MockBackend(responses=list(responses), **kw))
    results = tmp_path / "results"
    rc = run_mod.main(
        [
            "--mission",
            str(mission_dir),
            "--condition",
            "A",
            "--model",
            "mock-cli",
            "--results-root",
            str(results),
            "--log-level",
            "ERROR",
        ]
    )
    assert rc == 0
    files = list(results.glob("*.jsonl"))
    assert len(files) == 1


def test_run_one_loops_until_diagnosis(tmp_path):
    mission_dir = _make_mission(tmp_path)
    responses = [
        ModelOutput(
            content="",
            tool_calls=(
                ToolCall(
                    name="read_bag_text", arguments={"vendor": "turtlebot3", "source_id": "tb3_0"}
                ),
            ),
        ),
        ModelOutput(
            content="done",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": "tb3_lidar_dropout",
                        "vendor": "turtlebot3",
                        "source_id": "tb3_0",
                        "claimed_onset_time_s": 4.0,
                    },
                ),
            ),
        ),
    ]
    _register_scripted_backend("mock-loop", responses)
    record = run_mod.run_one(
        mission_dir=mission_dir,
        condition_code="A",
        model_id="mock-loop",
        max_steps=5,
    )
    assert record.steps == 2
    assert record.final_diagnosis is not None


def test_run_one_no_preamble_for_baseline(tmp_path):
    mission_dir = _make_mission(tmp_path)
    captured: dict[str, MockBackend] = {}

    def _factory(**kw):
        backend = MockBackend(responses=[ModelOutput(content="done")], **kw)
        captured["backend"] = backend
        return backend

    register_backend("mock-noorient", _factory)
    run_mod.run_one(mission_dir=mission_dir, condition_code="A", model_id="mock-noorient")
    first_user = captured["backend"].calls[0]["messages"][0]["content"]
    assert "ORIENTATION" not in first_user


def test_run_one_nudges_prose_reply_to_submit(tmp_path):
    # A model that trails off in prose (no tool call) must be nudged to finalize
    # via submit_diagnosis instead of scoring as a non-answer.
    mission_dir = _make_mission(tmp_path)
    responses = [
        ModelOutput(content="I think the lidar looks off, but I'm not sure."),  # no tool call
        ModelOutput(
            content="finalizing",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": "tb3_lidar_dropout",
                        "vendor": "turtlebot3",
                        "source_id": "tb3_0",
                        "claimed_onset_time_s": 5.0,
                    },
                ),
            ),
        ),
    ]
    _register_scripted_backend("mock-nudge", responses)
    record = run_mod.run_one(
        mission_dir=mission_dir, condition_code="A", model_id="mock-nudge", max_steps=5
    )
    assert record.submit_nudges == 1
    assert record.final_diagnosis is not None
    assert record.final_diagnosis["fault_id"] == "tb3_lidar_dropout"


def test_run_one_nudge_is_bounded(tmp_path):
    # A model that never submits is nudged at most MAX_SUBMIT_NUDGES times, then
    # the run terminates with the prose reply rather than looping forever.
    mission_dir = _make_mission(tmp_path)
    responses = [ModelOutput(content=f"still thinking {i}") for i in range(6)]
    _register_scripted_backend("mock-stubborn", responses)
    record = run_mod.run_one(
        mission_dir=mission_dir, condition_code="A", model_id="mock-stubborn", max_steps=10
    )
    assert record.submit_nudges == run_mod.MAX_SUBMIT_NUDGES
    assert record.final_diagnosis is None
    # 1 initial prose + MAX_SUBMIT_NUDGES follow-ups = MAX_SUBMIT_NUDGES + 1 turns.
    assert record.steps == run_mod.MAX_SUBMIT_NUDGES + 1
