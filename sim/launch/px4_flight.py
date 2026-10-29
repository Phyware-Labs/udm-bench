"""Fly the PX4 SITL vehicle through its mission waypoints (in-container).

Without commanded flight the PX4 ``/fmu`` telemetry is a stationary, disarmed
vehicle, so the position/motion faults (``px4_gps_dropout``,
``px4_motor_failure``, ``px4_battery_sag`` under load, …) are unobservable —
the PX4 analogue of the TurtleBot3 ``nav_waypoints.py`` driver.

This node speaks PX4's offboard-control uORB interface via ``px4_msgs``:

  1. Streams ``OffboardControlMode`` + ``TrajectorySetpoint`` at 10 Hz.
  2. Once the EKF has a valid local-position estimate, switches to OFFBOARD
     and arms.
  3. Climbs to ``UDM_BENCH_PX4_TAKEOFF_ALT`` then cycles the mission waypoints
     (``UDM_BENCH_PX4_WAYPOINTS``, a JSON list of
     ``{lat_offset_m, lon_offset_m, alt_m}``) for the mission duration.
  4. On the deadline it commands LAND and disarms.

Runs only inside the PX4 sim image (needs ``rclpy`` + ``px4_msgs``); it is
launched by ``px4.launch.py`` once SITL + the XRCE agent are up and is
intentionally best-effort — any failure here must not abort the recording
mission.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import time

# NED local setpoints (metres). z is down-negative, so "up" is negative z.
_DEFAULT_TAKEOFF_ALT_M = 5.0
# A small default box patrol (north/east offsets, metres) used when a mission
# defines no waypoints — keeps the vehicle moving above the takeoff point.
_DEFAULT_WAYPOINTS = [
    {"lat_offset_m": 5.0, "lon_offset_m": 0.0, "alt_m": _DEFAULT_TAKEOFF_ALT_M},
    {"lat_offset_m": 5.0, "lon_offset_m": 5.0, "alt_m": _DEFAULT_TAKEOFF_ALT_M},
    {"lat_offset_m": 0.0, "lon_offset_m": 5.0, "alt_m": _DEFAULT_TAKEOFF_ALT_M},
    {"lat_offset_m": 0.0, "lon_offset_m": 0.0, "alt_m": _DEFAULT_TAKEOFF_ALT_M},
]
# How close (metres) the vehicle must get to a setpoint before advancing.
_REACH_RADIUS_M = 1.5


def _takeoff_alt_m() -> float:
    try:
        return float(os.environ.get("UDM_BENCH_PX4_TAKEOFF_ALT", _DEFAULT_TAKEOFF_ALT_M))
    except ValueError:
        return _DEFAULT_TAKEOFF_ALT_M


def _load_waypoints() -> list[dict[str, float]]:
    try:
        wps = json.loads(os.environ.get("UDM_BENCH_PX4_WAYPOINTS", "[]"))
    except json.JSONDecodeError:
        wps = []
    out = [
        w
        for w in (wps or [])
        if isinstance(w, dict) and "lat_offset_m" in w and "lon_offset_m" in w
    ]
    return out or _DEFAULT_WAYPOINTS


def main() -> None:  # noqa: C901 — a flat offboard state machine reads clearer inline
    import rclpy
    from px4_msgs.msg import (
        OffboardControlMode,
        TrajectorySetpoint,
        VehicleCommand,
        VehicleLocalPosition,
        VehicleStatus,
    )
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

    duration_s = float(os.environ.get("UDM_BENCH_BAG_DURATION_S", "90"))
    takeoff_alt = _takeoff_alt_m()
    waypoints = _load_waypoints()

    # NED setpoints: north=+x, east=+y, up=-z. Takeoff point is straight up.
    targets = [(0.0, 0.0, -abs(takeoff_alt))]
    targets += [
        (
            float(w["lat_offset_m"]),
            float(w["lon_offset_m"]),
            -abs(float(w.get("alt_m", takeoff_alt))),
        )
        for w in waypoints
    ]

    class OffboardFlight(Node):
        def __init__(self) -> None:
            super().__init__("udm_px4_offboard")
            # PX4 uORB bridge uses best-effort + transient-local, depth 1.
            qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
            )
            self._ocm = self.create_publisher(
                OffboardControlMode, "/fmu/in/offboard_control_mode", qos
            )
            self._sp = self.create_publisher(TrajectorySetpoint, "/fmu/in/trajectory_setpoint", qos)
            self._cmd = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", qos)
            self.create_subscription(
                VehicleLocalPosition, "/fmu/out/vehicle_local_position", self._on_pos, qos
            )
            self.create_subscription(VehicleStatus, "/fmu/out/vehicle_status", self._on_status, qos)

            self._pos: VehicleLocalPosition | None = None
            self._nav_state = 0
            self._arming_state = 0
            self._tick = 0
            self._wp_idx = 0
            self._deadline = time.time() + duration_s
            self._landing = False
            # PX4 VehicleStatus.ARMING_STATE_ARMED is 2 across the v1.x line;
            # read the constant when present, fall back to the literal.
            self._armed_value = int(getattr(VehicleStatus, "ARMING_STATE_ARMED", 2))
            # 10 Hz control loop — PX4 drops OFFBOARD if setpoints stop arriving.
            self._timer = self.create_timer(0.1, self._loop)

        # --- subscriptions -------------------------------------------------
        def _on_pos(self, msg: VehicleLocalPosition) -> None:
            self._pos = msg

        def _on_status(self, msg: VehicleStatus) -> None:
            self._nav_state = int(msg.nav_state)
            self._arming_state = int(msg.arming_state)

        # --- helpers -------------------------------------------------------
        def _now_us(self) -> int:
            return int(self.get_clock().now().nanoseconds / 1000)

        def _publish_ocm(self) -> None:
            m = OffboardControlMode()
            m.timestamp = self._now_us()
            m.position = True
            m.velocity = False
            m.acceleration = False
            m.attitude = False
            m.body_rate = False
            self._ocm.publish(m)

        def _publish_setpoint(self, x: float, y: float, z: float) -> None:
            m = TrajectorySetpoint()
            m.timestamp = self._now_us()
            m.position = [float(x), float(y), float(z)]
            m.velocity = [math.nan, math.nan, math.nan]
            m.acceleration = [math.nan, math.nan, math.nan]
            m.yaw = 0.0
            m.yawspeed = math.nan
            self._sp.publish(m)

        def _send_command(self, command: int, *, p1: float = 0.0, p2: float = 0.0) -> None:
            m = VehicleCommand()
            m.timestamp = self._now_us()
            m.command = int(command)
            m.param1 = float(p1)
            m.param2 = float(p2)
            m.target_system = 1
            m.target_component = 1
            m.source_system = 1
            m.source_component = 1
            m.from_external = True
            self._cmd.publish(m)

        def _distance_to(self, x: float, y: float, z: float) -> float:
            p = self._pos
            if p is None:
                return math.inf
            return math.sqrt((p.x - x) ** 2 + (p.y - y) ** 2 + (p.z - z) ** 2)

        # --- control loop --------------------------------------------------
        def _loop(self) -> None:
            try:
                self._step()
            except Exception as exc:  # noqa: BLE001 — flight is best-effort
                print(f"[px4_flight] loop error: {exc}", flush=True)

        def _step(self) -> None:
            self._tick += 1

            # Mission time is up: land + disarm, then stop streaming.
            if time.time() >= self._deadline:
                if not self._landing:
                    self._landing = True
                    self._send_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
                    print("[px4_flight] deadline reached — landing", flush=True)
                return

            tx, ty, tz = targets[self._wp_idx]
            # Keep the offboard heartbeat + setpoint flowing every tick.
            self._publish_ocm()
            self._publish_setpoint(tx, ty, tz)

            # Until actually ARMED, keep (re)requesting OFFBOARD + arm once a
            # second. jMAVSim's EKF/GPS can take 20–40 s to pass PX4's preflight
            # checks ("GPS fix too low"), so a single arm request is rejected and
            # must be retried — not latched — until VehicleStatus reports ARMED.
            if self._arming_state != self._armed_value:
                if self._tick >= 10 and self._tick % 10 == 0:
                    # param1=1 (custom mode), param2=6 (PX4 OFFBOARD main mode)
                    self._send_command(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, p1=1.0, p2=6.0)
                    self._send_command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, p1=1.0)
                    print("[px4_flight] (re)requesting OFFBOARD + arm", flush=True)
                return

            # Armed + flying: advance through waypoints once each is reached.
            if self._distance_to(tx, ty, tz) <= _REACH_RADIUS_M:
                self._wp_idx = (self._wp_idx + 1) % len(targets)

    rclpy.init()
    node = OffboardFlight()
    try:
        # Spin until the mission deadline (+ a short grace for the land cmd).
        end = time.time() + duration_s + 5.0
        while time.time() < end:
            rclpy.spin_once(node, timeout_sec=0.1)
    except Exception as exc:  # noqa: BLE001 — flight is best-effort
        print(f"[px4_flight] aborted: {exc}", flush=True)
    finally:
        with contextlib.suppress(Exception):
            node.destroy_node()
        with contextlib.suppress(Exception):
            rclpy.shutdown()


if __name__ == "__main__":
    main()
