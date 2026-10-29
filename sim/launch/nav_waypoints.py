"""Drive the TurtleBot3 through its mission waypoints (in-container).

Without commanded motion the odometry/motor/localisation faults are
unobservable, so this node sends the robot on a continuous patrol of the
mission's waypoints (``UDM_BENCH_TB3_WAYPOINTS``, a JSON list of ``{x, y}``)
for the mission duration, using the Nav2 ``BasicNavigator`` API.

Runs only inside the TurtleBot3 sim image (needs ``rclpy`` +
``nav2_simple_commander``); it is launched by ``turtlebot3.launch.py`` once
Nav2 is active and is intentionally best-effort — any failure here must not
abort the recording mission.
"""

from __future__ import annotations

import contextlib
import json
import os
import time

# Fallback patrol loop (metres, map frame) used when a mission defines no
# waypoints — a small box that keeps the robot moving within the warehouse.
_DEFAULT_WAYPOINTS = [
    {"x": 1.0, "y": 0.0},
    {"x": 1.5, "y": 1.0},
    {"x": 0.0, "y": 1.0},
    {"x": 0.0, "y": 0.0},
]


def _load_waypoints() -> list[dict[str, float]]:
    try:
        wps = json.loads(os.environ.get("UDM_BENCH_TB3_WAYPOINTS", "[]"))
    except json.JSONDecodeError:
        wps = []
    wps = [w for w in wps if isinstance(w, dict) and "x" in w and "y" in w]
    return wps or _DEFAULT_WAYPOINTS


def main() -> None:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from nav2_simple_commander.robot_navigator import BasicNavigator

    duration_s = float(os.environ.get("UDM_BENCH_BAG_DURATION_S", "90"))
    waypoints = _load_waypoints()

    rclpy.init()
    nav = BasicNavigator()
    try:
        # Blocks until amcl + bt_navigator are active (set_initial_pose seeds
        # amcl, so this returns without an RViz pose estimate).
        nav.waitUntilNav2Active()

        def _pose(wp: dict[str, float]) -> PoseStamped:
            p = PoseStamped()
            p.header.frame_id = "map"
            p.header.stamp = nav.get_clock().now().to_msg()
            p.pose.position.x = wp["x"]
            p.pose.position.y = wp["y"]
            p.pose.orientation.w = 1.0
            return p

        poses = [_pose(w) for w in waypoints]
        deadline = time.time() + duration_s
        while time.time() < deadline:
            # Refresh stamps each lap, then follow the waypoint loop.
            for p in poses:
                p.header.stamp = nav.get_clock().now().to_msg()
            nav.followWaypoints(poses)
            while not nav.isTaskComplete():
                if time.time() >= deadline:
                    nav.cancelTask()
                    break
                time.sleep(0.5)
    except Exception as exc:  # noqa: BLE001 — navigation is best-effort
        print(f"[nav_waypoints] navigation aborted: {exc}", flush=True)
    finally:
        with contextlib.suppress(Exception):
            rclpy.shutdown()


if __name__ == "__main__":
    main()
