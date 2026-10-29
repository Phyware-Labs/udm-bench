"""Unit tests for :mod:`baselines.flatten`."""

from __future__ import annotations

import json

from baselines.flatten import flatten_scalars


def test_flatten_nested_dicts():
    fields = {"linear": {"x": 1.0, "y": 2.0}, "angular": {"z": 3.0}}
    out = flatten_scalars(fields)
    assert out == {"linear__x": 1.0, "linear__y": 2.0, "angular__z": 3.0}


def test_flatten_lists_become_json():
    out = flatten_scalars({"ranges": [1.0, 2.0, 3.0]})
    assert json.loads(out["ranges"]) == [1.0, 2.0, 3.0]


def test_flatten_scalars_passthrough():
    out = flatten_scalars({"frame_id": "imu", "sec": 5, "ok": True, "missing": None})
    assert out == {"frame_id": "imu", "sec": 5, "ok": True, "missing": None}


def test_flatten_custom_separator():
    out = flatten_scalars({"a": {"b": 1}}, sep=".")
    assert out == {"a.b": 1}


def test_flatten_nested_list_of_dicts():
    out = flatten_scalars({"transforms": [{"x": 1}, {"x": 2}]})
    assert json.loads(out["transforms"]) == [{"x": 1}, {"x": 2}]
