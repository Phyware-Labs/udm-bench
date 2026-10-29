"""Tests for the hallucination detector."""

from __future__ import annotations

import json

from faults.base import InjectionRecord
from scoring.hallucination import detect_hallucinations


def _tool_call(name, args=None, content="", is_error=False):
    return {
        "step": 1,
        "tool_call": {"name": name, "arguments": args or {}},
        "tool_result": {"content": content, "is_error": is_error},
        "is_diagnosis": name == "submit_diagnosis",
    }


def test_no_hallucinations_when_explanation_is_empty():
    rec = {
        "composition": "single-vendor",
        "tool_calls": [],
        "final_diagnosis": None,
        "final_content": "",
    }
    report = detect_hallucinations(run_record=rec, ground_truth=[])
    assert report.total == 0


def test_event_id_hallucination_detected():
    rec = {
        "composition": "single-vendor",
        "tool_calls": [
            _tool_call(
                "list_events",
                content=json.dumps([{"event_id": "evt_aaaa1111"}, {"event_id": "evt_bbbb2222"}]),
            ),
        ],
        "final_diagnosis": {
            "fault_id": "x",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
            "explanation": "Based on evt_aaaa1111 and evt_ccccdead.",
        },
        "final_content": "",
    }
    report = detect_hallucinations(run_record=rec, ground_truth=[])
    assert "evt_ccccdead" in report.event_ids
    assert "evt_aaaa1111" not in report.event_ids


def test_bare_uuid_citation_from_compact_row_is_grounded():
    # Real store uses bare UUIDs surfaced inside compact rows / previews (a
    # string the JSON walk can't descend into). Citing one must NOT be flagged.
    uuid = "06a4acf9-482b-7f6d-8000-c1817b985f29"
    rec = {
        "composition": "single-vendor",
        "tool_calls": [
            _tool_call(
                "query_events",
                content=json.dumps(
                    {"rows": [{"event_id": uuid, "captured_at": "t"}], "omitted_rows": 5}
                ),
            ),
        ],
        "final_diagnosis": {
            "fault_id": "x",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
            "cited_event_ids": [uuid],
            "explanation": f"Confirmed by {uuid}.",
        },
        "final_content": "",
    }
    report = detect_hallucinations(run_record=rec, ground_truth=[])
    assert uuid not in report.event_ids
    assert report.event_ids == ()


def test_bare_uuid_not_in_trace_is_flagged():
    real = "06a4acf9-482b-7f6d-8000-c1817b985f29"
    fake = "deadbeef-0000-1111-2222-333344445555"
    rec = {
        "composition": "single-vendor",
        "tool_calls": [
            _tool_call("query_events", content=json.dumps({"rows": [{"event_id": real}]}))
        ],
        "final_diagnosis": {
            "fault_id": "x",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
            "cited_event_ids": [real, fake],
        },
        "final_content": "",
    }
    report = detect_hallucinations(run_record=rec, ground_truth=[])
    assert fake in report.event_ids
    assert real not in report.event_ids


def test_real_udm_field_paths_not_flagged_and_prose_abbrev_ignored():
    rec = {
        "composition": "single-vendor",
        "tool_calls": [],
        "final_diagnosis": {
            "fault_id": "x",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
            "explanation": (
                "extensions.lidar.valid_fraction dropped and "
                "power.battery.voltage_v fell, e.g. mid-mission."
            ),
        },
        "final_content": "",
    }
    report = detect_hallucinations(run_record=rec, ground_truth=[])
    # Real UDM paths are allowed; prose 'e.g' is no longer mis-flagged.
    assert report.field_paths == ()


def test_standard_hallucination_detected():
    rec = {
        "composition": "single-vendor",
        "tool_calls": [],
        "final_diagnosis": {
            "fault_id": "x",
            "vendor": "tb3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
            "explanation": "Per ISO 21448 the fault is severe.",
        },
        "final_content": "",
    }
    report = detect_hallucinations(run_record=rec, ground_truth=[])
    assert "ISO 21448" in report.standards


def test_standard_citation_grounded_by_compliance_call():
    rec = {
        "composition": "single-vendor",
        "tool_calls": [_tool_call("compliance_audit", args={"standard": "ISO 21448"})],
        "final_diagnosis": {
            "fault_id": "x",
            "vendor": "tb3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
            "explanation": "Per ISO 21448 the fault is severe.",
        },
        "final_content": "",
    }
    report = detect_hallucinations(run_record=rec, ground_truth=[])
    assert "ISO 21448" not in report.standards


def test_vendor_misattribution_multi_vendor():
    rec = {
        "composition": "multi-vendor",
        "tool_calls": [],
        "final_diagnosis": {
            "fault_id": "px4_gps_dropout",
            "vendor": "px4",
            "source_id": "px4_0",
            "claimed_onset_time_s": 1.0,
        },
        "final_content": "",
    }
    truth = [
        InjectionRecord(
            vendor="turtlebot3",
            fault_id="tb3_lidar_dropout",
            source_id="tb3_0",
            injection_time=1.0,
            mission_id="m",
            parameters={},
        )
    ]
    report = detect_hallucinations(run_record=rec, ground_truth=truth)
    assert report.vendor_misattribution is True


def test_vendor_attribution_correct_single_vendor():
    rec = {
        "composition": "single-vendor",
        "tool_calls": [],
        "final_diagnosis": {
            "fault_id": "tb3_lidar_dropout",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
        },
        "final_content": "",
    }
    truth = [
        InjectionRecord(
            vendor="turtlebot3",
            fault_id="tb3_lidar_dropout",
            source_id="tb3_0",
            injection_time=1.0,
            mission_id="m",
            parameters={},
        )
    ]
    report = detect_hallucinations(run_record=rec, ground_truth=truth)
    assert report.vendor_misattribution is False
