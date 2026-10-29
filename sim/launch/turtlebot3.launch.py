"""TurtleBot3 + Gazebo (headless) + Nav2 launch graph for the ``turtlebot3`` profile.

Boots:
  * Headless Gazebo Classic (``gzserver`` only — no ``gzclient``, so no
    ``DISPLAY`` is needed) with the world selected by ``UDM_BENCH_WORLD``
    (default ``small_warehouse``; falls back to the stock ``turtlebot3_world``
    if the requested SDF is missing).
  * The TurtleBot3 ``burger`` model (``robot_state_publisher`` + spawn).
  * The Nav2 stack via ``nav2_bringup`` with the ``turtlebot3_navigation2``
    params + map.
  * A passthrough relay per sensor topic (``passthrough_relay.py``).
  * A ``rosbag2`` recorder capturing the topics the scoring harness relies on.

Configured entirely via environment variables, so a mission runner can drive it
without ROS2-side argument plumbing.
"""

from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource

from sim.launch._common import (
    TB3_BAG_TOPICS,
    TB3_RELAY_TOPICS,
    bag_record_action,
    passthrough_relay_action,
    world_name,
)


def _world_path() -> str:
    """Resolve the Gazebo world SDF, falling back to the stock TB3 world."""
    world = world_name("small_warehouse")
    candidate = f"/opt/udm-bench/worlds/{world}.world"
    if os.path.exists(candidate):
        return candidate
    return os.path.join(
        get_package_share_directory("turtlebot3_gazebo"),
        "worlds",
        "turtlebot3_world.world",
    )


def generate_launch_description() -> LaunchDescription:
    use_sim_time = "true"
    turtlebot3_model = os.environ.get("TURTLEBOT3_MODEL", "burger")

    gazebo_ros = get_package_share_directory("gazebo_ros")
    tb3_gazebo = get_package_share_directory("turtlebot3_gazebo")
    nav2_bringup = get_package_share_directory("nav2_bringup")
    tb3_nav2 = get_package_share_directory("turtlebot3_navigation2")

    # Headless Gazebo: gzserver only. gzclient is the GUI and segfaults with
    # no DISPLAY, so it is intentionally omitted.
    gzserver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(gazebo_ros, "launch", "gzserver.launch.py")),
        launch_arguments={"world": _world_path(), "verbose": "false"}.items(),
    )

    robot_state_publisher = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb3_gazebo, "launch", "robot_state_publisher.launch.py")
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
    )

    # Passthrough relays own the canonical sensor topics. The burger SDF in the
    # image is patched so its producers publish ``<topic>_src``; these relays
    # republish ``<topic>`` unchanged. (The benchmark's faulted missions used a
    # fault-injection relay in this position, which is not part of this
    # repository.) Started before the robot spawns so the topic never gaps.
    relays = [
        TimerAction(
            period=2.0,
            actions=[passthrough_relay_action(topic=topic)],
        )
        for topic in TB3_RELAY_TOPICS
    ]

    # Spawn the robot once gzserver is accepting the /spawn_entity service.
    spawn = TimerAction(
        period=4.0,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(tb3_gazebo, "launch", "spawn_turtlebot3.launch.py")
                ),
                launch_arguments={"x_pose": "0.0", "y_pose": "0.0"}.items(),
            )
        ],
    )

    # Nav2 bringup with the correct turtlebot3_navigation2 params + map.
    nav2 = TimerAction(
        period=10.0,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(nav2_bringup, "launch", "bringup_launch.py")
                ),
                launch_arguments={
                    "use_sim_time": use_sim_time,
                    "params_file": os.path.join(tb3_nav2, "param", f"{turtlebot3_model}.yaml"),
                    "map": os.path.join(tb3_nav2, "map", "map.yaml"),
                    "autostart": "true",
                }.items(),
            )
        ],
    )

    # Start the bag recorder after the topics exist.
    recorder = TimerAction(
        period=14.0,
        actions=[bag_record_action(bag_name="bag_turtlebot3_tb3_0", topics=TB3_BAG_TOPICS)],
    )

    # Drive the robot through its mission waypoints once Nav2 is active so the
    # robot produces motion telemetry. Best-effort: a navigation failure
    # must not abort the recording mission.
    nav_driver = TimerAction(
        period=18.0,
        actions=[
            ExecuteProcess(
                cmd=["python3", "/opt/udm-bench/sim/launch/nav_waypoints.py"],
                output="screen",
            )
        ],
    )

    return LaunchDescription(
        [gzserver, robot_state_publisher, *relays, spawn, nav2, recorder, nav_driver]
    )
