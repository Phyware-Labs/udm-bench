"""Tests for :mod:`baselines.prepare`."""

from __future__ import annotations

import sqlite3

import pytest

from baselines.prepare import (
    find_bags,
    parse_bag_dirname,
    prepare_mission,
)
from tests.baselines._bagfixture import make_twist, write_bag

TWIST = "geometry_msgs/msg/Twist"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("bag_turtlebot3_tb3_0", ("turtlebot3", "tb3_0")),
        ("bag_px4_px4_0", ("px4", "px4_0")),
        ("bag_turtlebot3_robot_12", ("turtlebot3", "robot_12")),
        ("bag_unknownvendor_x", None),
        ("notabag", None),
        ("bag_px4_", None),
    ],
)
def test_parse_bag_dirname(name, expected):
    assert parse_bag_dirname(name) == expected


def test_find_bags_skips_non_bag_and_empty(tmp_path):
    write_bag(tmp_path / "bag_turtlebot3_tb3_0", [("/cmd_vel", TWIST, 1, make_twist(0.1, 0.0))])
    (tmp_path / "bag_px4_px4_0").mkdir()  # no .db3 -> skipped
    (tmp_path / "scenario.yaml").write_text("x", encoding="utf-8")
    bags = find_bags(tmp_path)
    assert [b.source_id for b in bags] == ["tb3_0"]


def test_prepare_mission_no_bags_is_noop(tmp_path):
    summary = prepare_mission(tmp_path)
    assert summary.bags == []
    assert summary.sqlite_path is None


def test_prepare_mission_missing_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare_mission(tmp_path / "nope")


def test_prepare_mission_produces_artifacts(tmp_path):
    write_bag(
        tmp_path / "bag_turtlebot3_tb3_0",
        [
            ("/cmd_vel", TWIST, 1_000_000_000, make_twist(0.1, 0.0)),
            ("/cmd_vel", TWIST, 2_000_000_000, make_twist(0.2, 0.1)),
        ],
    )
    summary = prepare_mission(tmp_path)

    assert summary.bags == ["bag_turtlebot3_tb3_0"]
    txt = tmp_path / "bag_turtlebot3_tb3_0.txt"
    db = tmp_path / "telemetry.sqlite"
    assert txt.exists()
    assert db.exists()
    assert summary.text_files["bag_turtlebot3_tb3_0.txt"] == 2
    assert summary.sqlite_tables["turtlebot3__cmd_vel"] == 2
    with sqlite3.connect(db) as conn:
        (n,) = conn.execute("SELECT COUNT(*) FROM turtlebot3__cmd_vel").fetchone()
        assert n == 2


def test_prepare_mission_rebuilds_sqlite(tmp_path):
    write_bag(tmp_path / "bag_turtlebot3_tb3_0", [("/cmd_vel", TWIST, 1, make_twist(0.1, 0.0))])
    prepare_mission(tmp_path)
    # Run again: telemetry.sqlite is rebuilt from scratch, no stale tables.
    prepare_mission(tmp_path)
    db = tmp_path / "telemetry.sqlite"
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "turtlebot3__cmd_vel" in tables
