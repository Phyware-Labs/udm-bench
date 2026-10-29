"""Evidence ceiling: is each injected fault actually visible in the recording?

Several catalogue faults may leave no discriminating trace in the telemetry the
agents see. If a fault is invisible, *no* condition can find it, and counting it
in recall understates every condition equally. This module measures that ceiling.

Method — a fault-aware *oracle*, deliberately generous:

1. For every mission, compute a handful of signal statistics over the same 2 Hz
   ``telemetry.sqlite`` that conditions A–G are derived from.
2. Each fault is assigned the one statistic its injection mechanism should move
   (:data:`FAULT_SIGNAL`).
3. A faulty mission's fault is *detectable* iff that statistic exceeds the
   maximum seen across every **clean** mission of the same composition, and the
   faulted robot actually recorded telemetry.

The oracle knows which fault to look for, so it is an *upper bound* on
evidence, not a fair detector. "Not detectable" means "no signal under the
statistic its mechanism should move" — strong evidence the recording lacks it,
not proof.
"""

from __future__ import annotations

import bisect
import json
import math
import sqlite3
import statistics
from pathlib import Path
from typing import Any

# fault_id -> (statistic, why that statistic)
FAULT_SIGNAL: dict[str, tuple[str, str]] = {
    "px4_gps_dropout": ("gps_gap_s", "longest gap between global-position samples"),
    "px4_imu_saturation": ("att_nonfinite", "attitude quaternions with NaN/inf"),
    "tb3_lidar_dropout": ("scan_gap_s", "longest gap between LaserScan samples"),
    "tb3_lidar_noise": ("scan_rough_max", "peak ray-to-ray roughness of LaserScan ranges"),
    "tb3_imu_bias": ("imu_odom_wz_resid", "peak |IMU yaw rate - odometry yaw rate|"),
    "tb3_motor_stall": ("cmd_odom_resid", "peak |commanded - measured velocity|"),
    "tb3_odometry_drift": ("odom_amcl_div", "growth of odometry vs AMCL position gap"),
    "tb3_map_mismatch": ("amcl_cov_max", "peak AMCL x/y position variance"),
    "tb3_costmap_inflation_drift": ("local_costmap_occ_max", "peak local-costmap occupancy"),
}

_VENDOR_OF_PREFIX = {"tb3": "turtlebot3", "px4": "px4"}


def _load(text: str) -> Any:
    """Parse the JSON-ish array columns (bare NaN / Infinity tokens)."""
    text = text.replace("-Infinity", '"-inf"').replace("Infinity", '"inf"')
    return json.loads(text.replace("NaN", "null"))


def _num(x: Any) -> float:
    if x is None:
        return math.nan
    return float(x)


def _max_gap_s(conn: sqlite3.Connection, table: str) -> float:
    ts = [r[0] for r in conn.execute(f'SELECT _t_ns FROM "{table}" ORDER BY _t_ns')]
    if len(ts) < 2:
        return math.nan
    return max(b - a for a, b in zip(ts, ts[1:], strict=False)) / 1e9


def rolling_max_mean(xs: list[float], window: int) -> float:
    """Largest mean over any ``window`` consecutive values (NaN if too short)."""
    if len(xs) < window:
        return math.nan
    s = sum(xs[:window])
    best = s
    for i in range(window, len(xs)):
        s += xs[i] - xs[i - window]
        best = max(best, s)
    return best / window


def _nearest(ts: list[int], vals: list[float], t: int) -> float:
    i = bisect.bisect_left(ts, t)
    if i >= len(ts):
        i = len(ts) - 1
    if i > 0 and abs(ts[i - 1] - t) < abs(ts[i] - t):
        i -= 1
    return vals[i]


def _tb3_stats(conn: sqlite3.Connection) -> dict[str, float]:
    out: dict[str, float] = {"scan_gap_s": _max_gap_s(conn, "turtlebot3__scan")}

    rough, nonfinite = [], []
    for (ranges,) in conn.execute("SELECT ranges FROM turtlebot3__scan"):
        v = [_num(x) for x in _load(ranges)]
        finite = [x for x in v if math.isfinite(x)]
        nonfinite.append(1 - len(finite) / max(1, len(v)))
        d = [
            abs(a - b)
            for a, b in zip(v, v[1:], strict=False)
            if math.isfinite(a) and math.isfinite(b)
        ]
        rough.append(statistics.median(d) if d else 0.0)
    out["scan_rough_max"] = rolling_max_mean(rough, 4)
    out["scan_nonfinite_max"] = rolling_max_mean(nonfinite, 4)

    odom = conn.execute(
        "SELECT _t_ns, twist__twist__linear__x, twist__twist__angular__z, "
        "pose__pose__position__x, pose__pose__position__y "
        "FROM turtlebot3__odom ORDER BY _t_ns"
    ).fetchall()
    ot = [r[0] for r in odom]
    o_v, o_w = [r[1] for r in odom], [r[2] for r in odom]
    o_x, o_y = [r[3] for r in odom], [r[4] for r in odom]

    imu = conn.execute(
        "SELECT _t_ns, angular_velocity__z FROM turtlebot3__imu ORDER BY _t_ns"
    ).fetchall()
    out["imu_odom_wz_resid"] = rolling_max_mean([abs(w - _nearest(ot, o_w, t)) for t, w in imu], 20)

    cmd = conn.execute(
        "SELECT _t_ns, linear__x, angular__z FROM turtlebot3__cmd_vel ORDER BY _t_ns"
    ).fetchall()
    out["cmd_odom_resid"] = rolling_max_mean(
        [abs(v - _nearest(ot, o_v, t)) + abs(w - _nearest(ot, o_w, t)) for t, v, w in cmd], 10
    )

    amcl = conn.execute(
        "SELECT _t_ns, pose__pose__position__x, pose__pose__position__y, pose__covariance "
        "FROM turtlebot3__amcl_pose ORDER BY _t_ns"
    ).fetchall()
    if amcl:
        dist = [
            math.hypot(x - _nearest(ot, o_x, t), y - _nearest(ot, o_y, t)) for t, x, y, _ in amcl
        ]
        out["odom_amcl_div"] = max(dist) - dist[0]
        covs = [_load(cv) for *_, cv in amcl]
        out["amcl_cov_max"] = max(cv[0] + cv[7] for cv in covs)

    occ = []
    for (data,) in conn.execute("SELECT data FROM turtlebot3__local_costmap_costmap"):
        cells = _load(data)
        occ.append(sum(1 for c in cells if c and c > 0) / len(cells))
    out["local_costmap_occ_max"] = rolling_max_mean(occ, 6)
    return out


def _px4_stats(conn: sqlite3.Connection) -> dict[str, float]:
    nonfinite = sum(
        1
        for (q,) in conn.execute("SELECT q FROM px4__fmu_out_vehicle_attitude")
        if any(not math.isfinite(_num(x)) for x in _load(q))
    )
    return {
        "gps_gap_s": _max_gap_s(conn, "px4__fmu_out_vehicle_global_position"),
        "att_nonfinite": float(nonfinite),
    }


def mission_stats(telemetry_db: Path) -> dict[str, float]:
    """All signal statistics for one mission's ``telemetry.sqlite`` (read-only)."""
    conn = sqlite3.connect(f"file:{telemetry_db}?mode=ro", uri=True)
    try:
        counts = dict(
            conn.execute(
                "SELECT vendor, SUM(message_count) FROM _messages "
                "WHERE topic != '/tf_static' GROUP BY vendor"
            ).fetchall()
        )
        out: dict[str, float] = {
            "turtlebot3_msgs": float(counts.get("turtlebot3", 0) or 0),
            "px4_msgs": float(counts.get("px4", 0) or 0),
        }
        if out["turtlebot3_msgs"] > 0:
            out.update(_tb3_stats(conn))
        if out["px4_msgs"] > 0:
            out.update(_px4_stats(conn))
        return out
    finally:
        conn.close()


def fault_vendor(fault_id: str) -> str:
    return _VENDOR_OF_PREFIX[fault_id.split("_", 1)[0]]


def assess(missions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per faulty mission: is its fault detectable by the oracle?

    ``missions`` maps mission_id -> {"composition", "faults": [{fault_id, vendor}],
    "stats": {...}}. Returns mission_id -> {fault_id, statistic, value,
    clean_max, margin, detectable, reason}.
    """
    clean_max: dict[tuple[str, str], float] = {}
    for m in missions.values():
        if m["faults"]:
            continue
        for k, v in m["stats"].items():
            if math.isfinite(v):
                key = (m["composition"], k)
                clean_max[key] = max(clean_max.get(key, -math.inf), v)

    out: dict[str, dict[str, Any]] = {}
    for mid, m in missions.items():
        if not m["faults"]:
            continue
        fault_id = m["faults"][0]["fault_id"]
        stat, _ = FAULT_SIGNAL[fault_id]
        vendor = fault_vendor(fault_id)
        value = m["stats"].get(stat, math.nan)
        cmax = clean_max.get((m["composition"], stat), math.nan)
        if m["stats"].get(f"{vendor}_msgs", 0) == 0:
            detectable, reason = False, f"no {vendor} telemetry recorded"
        elif not math.isfinite(value):
            detectable, reason = False, "statistic unavailable"
        elif value > cmax:
            detectable, reason = True, "above every clean mission"
        else:
            detectable, reason = False, "within clean-mission range"
        out[mid] = {
            "fault_id": fault_id,
            "statistic": stat,
            "value": value,
            "clean_max": cmax,
            "margin": value / cmax if (math.isfinite(value) and cmax) else math.nan,
            "detectable": detectable,
            "reason": reason,
        }
    return out
