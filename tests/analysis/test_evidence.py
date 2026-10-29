"""Tests for analysis.evidence — the evidence-ceiling oracle."""

from __future__ import annotations

import math

from analysis.evidence import FAULT_SIGNAL, assess, fault_vendor, rolling_max_mean


def test_rolling_max_mean():
    assert rolling_max_mean([0, 0, 3, 3, 0], 2) == 3.0
    assert rolling_max_mean([1, 2, 3], 3) == 2.0
    assert math.isnan(rolling_max_mean([1.0], 2))


def test_fault_vendor():
    assert fault_vendor("px4_gps_dropout") == "px4"
    assert fault_vendor("tb3_lidar_noise") == "turtlebot3"


def test_every_signal_fault_has_known_vendor():
    for fault_id in FAULT_SIGNAL:
        assert fault_vendor(fault_id) in {"px4", "turtlebot3"}


def _mission(comp, faults, **stats):
    base = {"turtlebot3_msgs": 100.0, "px4_msgs": 100.0}
    base.update(stats)
    return {
        "composition": comp,
        "faults": [{"fault_id": f, "vendor": fault_vendor(f)} for f in faults],
        "stats": base,
    }


def test_assess_compares_against_clean_max_of_same_composition():
    missions = {
        "clean-s": _mission("single-vendor", [], scan_gap_s=0.6),
        "clean-m": _mission("multi-vendor", [], scan_gap_s=9.0),
        "fault-s": _mission("single-vendor", ["tb3_lidar_dropout"], scan_gap_s=5.0),
        "fault-m": _mission("multi-vendor", ["tb3_lidar_dropout"], scan_gap_s=5.0),
    }
    out = assess(missions)
    assert set(out) == {"fault-s", "fault-m"}
    assert out["fault-s"]["detectable"] is True
    assert out["fault-s"]["clean_max"] == 0.6
    # same value, but a multi-vendor clean mission already reaches 9.0
    assert out["fault-m"]["detectable"] is False
    assert out["fault-m"]["reason"] == "within clean-mission range"


def test_assess_requires_faulted_robot_telemetry():
    missions = {
        "clean": _mission("multi-vendor", [], cmd_odom_resid=0.3),
        "fault": _mission("multi-vendor", ["tb3_motor_stall"], turtlebot3_msgs=0.0),
    }
    out = assess(missions)["fault"]
    assert out["detectable"] is False
    assert out["reason"] == "no turtlebot3 telemetry recorded"


def test_mission_stats_on_synthetic_db(tmp_path):
    import sqlite3

    from analysis.evidence import mission_stats

    db = tmp_path / "telemetry.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE _messages (table_name TEXT, vendor TEXT, source_id TEXT, topic TEXT,
                                msgtype TEXT, message_count INTEGER);
        INSERT INTO _messages VALUES ('px4__a', 'px4', 'px4_0', '/fmu/out/vehicle_attitude',
                                      'x', 3);
        INSERT INTO _messages VALUES ('px4__g', 'px4', 'px4_0',
                                      '/fmu/out/vehicle_global_position', 'x', 3);
        CREATE TABLE px4__fmu_out_vehicle_attitude (_t_ns INTEGER, q TEXT);
        INSERT INTO px4__fmu_out_vehicle_attitude VALUES (0, '[1.0, 0.0, 0.0, 0.0]');
        INSERT INTO px4__fmu_out_vehicle_attitude VALUES (1, '[NaN, 0.0, 0.0, 0.0]');
        INSERT INTO px4__fmu_out_vehicle_attitude VALUES (2, '[Infinity, 0.0, 0.0, 0.0]');
        CREATE TABLE px4__fmu_out_vehicle_global_position (_t_ns INTEGER);
        INSERT INTO px4__fmu_out_vehicle_global_position VALUES (0);
        INSERT INTO px4__fmu_out_vehicle_global_position VALUES (500000000);
        INSERT INTO px4__fmu_out_vehicle_global_position VALUES (8500000000);
        """
    )
    conn.commit()
    conn.close()
    stats = mission_stats(db)
    assert stats["turtlebot3_msgs"] == 0
    assert stats["att_nonfinite"] == 2
    assert stats["gps_gap_s"] == 8.0
    assert "scan_gap_s" not in stats
