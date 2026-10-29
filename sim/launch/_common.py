"""Shared helpers used by the per-profile ROS2 launch files.

Keeps environment-variable handling and ``rosbag2`` recorder wiring DRY
across the TurtleBot3, PX4, and multi-vendor launch graphs.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from launch.actions import ExecuteProcess

# ``UDM_BENCH_RUNS_ROOT`` points at the per-mission output directory.
# The mission runner mounts a host directory under ``/runs`` inside
# each container and sets ``UDM_BENCH_MISSION_ID`` per launch, so the
# launch file always writes its bag to ``/runs/<mission_id>/``.
RUNS_ROOT_ENV = "UDM_BENCH_RUNS_ROOT"
MISSION_ID_ENV = "UDM_BENCH_MISSION_ID"
WORLD_ENV = "UDM_BENCH_WORLD"
BAG_DURATION_ENV = "UDM_BENCH_BAG_DURATION_S"
MISSION_SEED_ENV = "UDM_BENCH_MISSION_SEED"

# Topics each profile's ``rosbag2`` recorder captures. Kept here (rather than
# in the per-profile ``*.launch.py`` files) so the multi-vendor launch graph
# can reuse them without importing modules whose filenames contain ``.launch``
# (which are not importable as Python modules).
TB3_BAG_TOPICS: tuple[str, ...] = (
    "/scan",
    "/odom",
    "/imu",
    "/cmd_vel",
    "/amcl_pose",
    "/particle_cloud",
    "/battery_state",
    "/local_costmap/costmap",
    "/global_costmap/costmap",
    "/tf",
    "/tf_static",
)

PX4_BAG_TOPICS: tuple[str, ...] = (
    "/fmu/out/vehicle_global_position",
    "/fmu/out/vehicle_local_position",
    "/fmu/out/vehicle_attitude",
    "/fmu/out/vehicle_status",
    "/fmu/out/battery_status",
    "/fmu/out/actuator_outputs",
    "/fmu/out/sensor_baro",
    "/fmu/out/sensor_mag",
    "/fmu/in/manual_control_input",
)


def runs_root() -> str:
    """Where per-mission artifacts (bags, logs) are written."""
    return os.environ.get(RUNS_ROOT_ENV, "/runs")


def mission_id() -> str:
    return os.environ.get(MISSION_ID_ENV, "interactive")


def world_name(default: str) -> str:
    """Pick the Gazebo world. Falls back to ``default`` when unset."""
    return os.environ.get(WORLD_ENV, default)


def mission_seed(default: int = 0) -> int:
    """Mission RNG seed forwarded by the mission runner.

    Falls back to ``default`` when unset.
    """
    try:
        return int(os.environ.get(MISSION_SEED_ENV, default))
    except ValueError:
        return default


def bag_duration_s(default: float = 90.0) -> float:
    try:
        return float(os.environ.get(BAG_DURATION_ENV, default))
    except ValueError:
        return default


def bag_record_action(
    *,
    bag_name: str,
    topics: Iterable[str],
    storage: str = "sqlite3",
) -> ExecuteProcess:
    """Construct a ``ros2 bag record`` ExecuteProcess for the given topics.

    Output path is ``<runs_root>/<mission_id>/<bag_name>``. The directory
    is created by the orchestrator before the launch graph is started.
    """
    mid = mission_id()
    out_path = os.path.join(runs_root(), mid, bag_name)
    cmd = [
        "ros2",
        "bag",
        "record",
        "--output",
        out_path,
        "--storage",
        storage,
    ]
    cmd.extend(list(topics))
    return ExecuteProcess(cmd=cmd, output="screen")


#: TurtleBot3 sensor topics whose Gazebo producers are remapped to
#: ``<topic>_src`` in the image and republished by a relay on ``<topic>``.
TB3_RELAY_TOPICS: tuple[str, ...] = ("/scan", "/imu")


def passthrough_relay_action(*, topic: str) -> ExecuteProcess:
    """Construct the passthrough relay process for one TurtleBot3 sensor topic.

    The relay subscribes ``<topic>_src`` (the producer's remapped output) and
    republishes ``<topic>`` unchanged. See ``sim/launch/passthrough_relay.py``.
    """
    cmd = [
        "python3",
        "/opt/udm-bench/sim/launch/passthrough_relay.py",
        "--topic",
        topic,
    ]
    return ExecuteProcess(cmd=cmd, output="screen")
