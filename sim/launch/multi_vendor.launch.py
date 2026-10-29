"""Multi-vendor (TB3 + PX4) launch graph for the ``multi-vendor`` profile.

Both platforms share a single Gazebo world (``multi_vendor_warehouse`` by
default) so they have a common time + coordinate frame. The TB3 stack is
namespaced under ``/tb3`` and PX4 under ``/px4`` so their topics never
clash.

In Docker Compose deployment each platform actually runs in its own
container — Gazebo is hosted by the TB3 container and PX4 SITL connects
to it over the bridge network. This launch file is the *coordinator* used
when running both stacks inside a single container for local debugging.
"""

from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource

from sim.launch._common import (
    PX4_BAG_TOPICS,
    TB3_BAG_TOPICS,
    bag_record_action,
    world_name,
)


def generate_launch_description() -> LaunchDescription:
    world = world_name("multi_vendor_warehouse")
    turtlebot3_model = os.environ.get("TURTLEBOT3_MODEL", "burger")
    px4_home = os.environ.get("PX4_HOME", "/opt/PX4-Autopilot")

    gazebo_pkg = get_package_share_directory("turtlebot3_gazebo")
    nav2_pkg = get_package_share_directory("nav2_bringup")

    # Gazebo hosts the shared world. The TB3 launcher's empty_world action
    # is sufficient — it brings up Gazebo Server + Client + spawns TB3.
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(gazebo_pkg, "launch", "empty_world.launch.py")),
        launch_arguments={
            "use_sim_time": "true",
            "world": f"/opt/udm-bench/worlds/{world}.world",
            "turtlebot3_model": turtlebot3_model,
        }.items(),
    )

    # Nav2 for TB3, namespaced under /tb3.
    nav2 = TimerAction(
        period=5.0,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(nav2_pkg, "launch", "bringup_launch.py")
                ),
                launch_arguments={
                    "use_sim_time": "true",
                    "namespace": "tb3",
                    "params_file": os.path.join(gazebo_pkg, "param", f"{turtlebot3_model}.yaml"),
                    "autostart": "true",
                }.items(),
            )
        ],
    )

    # Micro-XRCE-DDS Agent for PX4 ⇄ ROS2 bridging.
    agent = TimerAction(
        period=2.0,
        actions=[ExecuteProcess(cmd=["MicroXRCEAgent", "udp4", "-p", "8888"], output="screen")],
    )

    # PX4 SITL connected to the shared Gazebo instance (PX4_SIM_HOST=localhost
    # since both processes run in the same container's network namespace).
    px4_sitl = TimerAction(
        period=6.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    "bash",
                    "-lc",
                    (f"cd {px4_home} && PX4_SIM_HOST=localhost HEADLESS=1 make px4_sitl none_iris"),
                ],
                output="screen",
            )
        ],
    )

    # Two recorders — one per vendor — so per-source bags exist for the
    # orchestrator + scoring harness, which expect
    # ``bag_<vendor>_<source_id>``.
    tb3_recorder = TimerAction(
        period=10.0,
        actions=[
            bag_record_action(
                bag_name="bag_turtlebot3_tb3_0",
                topics=tuple(
                    f"/tb3{t}" if t.startswith("/") else f"/tb3/{t}" for t in TB3_BAG_TOPICS
                ),
            )
        ],
    )
    px4_recorder = TimerAction(
        period=12.0,
        actions=[bag_record_action(bag_name="bag_px4_px4_0", topics=PX4_BAG_TOPICS)],
    )

    return LaunchDescription([gazebo, nav2, agent, px4_sitl, tb3_recorder, px4_recorder])
