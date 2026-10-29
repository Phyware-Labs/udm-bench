"""PX4 SITL (jMAVSim) + ``px4_ros_com`` bridge launch graph (``px4`` profile).

Boots:
  * The Micro-XRCE-DDS Agent (UDP 8888) — surfaces ``px4_msgs`` topics on
    the ROS2 side once PX4 SITL connects.
  * PX4 SITL via ``make px4_sitl jmavsim`` (headless). jMAVSim is a
    lightweight Java quad simulator that boots reliably headless in Docker —
    unlike the gz (Gazebo Garden) target whose ``gz_bridge`` cannot reach a
    headless gz server in this image. The benchmark only needs observable
    ``/fmu`` telemetry, not a shared 3D world (TB3 and
    PX4 run in separate containers regardless), so jMAVSim is sufficient.
  * An offboard flight driver (``px4_flight.py``) that arms the vehicle and
    flies the mission waypoints — without commanded flight the motion/position
    faults are unobservable.
  * A ``rosbag2`` recorder capturing the topics the scoring harness relies on.

The actual ROS2 ⇄ PX4 bridge runs inside the Agent and is configured by
the ``dds_topics.yaml`` in ``px4_ros_com`` — no additional ROS2 node is
required to surface ``/fmu/out/*`` topics.
"""

from __future__ import annotations

import os

from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction

from sim.launch._common import (
    PX4_BAG_TOPICS,
    bag_record_action,
)


def generate_launch_description() -> LaunchDescription:
    px4_home = os.environ.get("PX4_HOME", "/opt/PX4-Autopilot")
    # The public release records the firmware's canonical ``/fmu/out`` topics
    # directly. (The benchmark's faulted missions were recorded through a
    # fault-injection relay that is not part of this repository.)
    recorder_topics = list(PX4_BAG_TOPICS)

    # 1. Micro-XRCE-DDS Agent — must be up before SITL boots so the
    #    px4_msgs topics surface on the ROS2 side promptly.
    agent = ExecuteProcess(
        cmd=["MicroXRCEAgent", "udp4", "-p", "8888"],
        output="screen",
    )

    # 2. PX4 SITL via jMAVSim, started 3 s after the agent. HEADLESS=1 runs the
    #    sim with no GUI (no DISPLAY needed). The firmware + jMAVSim jar are
    #    pre-built into the image so this launches without a compile.
    px4_sitl = TimerAction(
        period=3.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    "bash",
                    "-lc",
                    (f"cd {px4_home} && HEADLESS=1 make px4_sitl jmavsim"),
                ],
                output="screen",
            )
        ],
    )

    # 3. Bag recorder, started 12 s after agent (gives SITL + bridge time
    #    to start publishing the /fmu topics).
    recorder = TimerAction(
        period=12.0,
        actions=[bag_record_action(bag_name="bag_px4_px4_0", topics=recorder_topics)],
    )

    # 4. Offboard flight driver — arms + flies the mission waypoints so the
    #    vehicle produces motion/position telemetry. Best-effort: a flight failure
    #    must not abort the recording mission. Started after SITL + EKF warmup.
    flight = TimerAction(
        period=18.0,
        actions=[
            ExecuteProcess(
                cmd=["python3", "/opt/udm-bench/sim/launch/px4_flight.py"],
                output="screen",
            )
        ],
    )

    return LaunchDescription([agent, px4_sitl, recorder, flight])
