# `sim/launch/`

ROS2 launch files per simulation profile. Each file boots only what its
profile needs.

| File                       | Profile        | Brings up                                                       |
| -------------------------- | -------------- | --------------------------------------------------------------- |
| `turtlebot3.launch.py`     | `turtlebot3`   | Gazebo + TB3 model + Nav2 bringup + bag recorder                |
| `px4.launch.py`            | `px4`          | Micro-XRCE-DDS Agent + PX4 SITL + bag recorder                  |
| `multi_vendor.launch.py`   | `multi-vendor` | Shared Gazebo + namespaced Nav2 (`/tb3`) + Agent + PX4 SITL + 2 recorders |
| `_common.py`               | shared         | Environment-variable reading + `ros2 bag record` helper         |
| `passthrough_relay.py`     | `turtlebot3`   | Republishes `/scan` and `/imu` from the remapped `<topic>_src` |

All three are configured via environment variables (see `_common.py`)
so a mission runner can drive them without ROS2-side argument
plumbing:

| Env var                   | Used by                | Purpose                                            |
| ------------------------- | ---------------------- | -------------------------------------------------- |
| `UDM_BENCH_RUNS_ROOT`     | `_common.py`           | Host-mounted directory for per-mission artifacts   |
| `UDM_BENCH_MISSION_ID`    | `_common.py`           | Per-launch mission id (sub-directory under RUNS_ROOT) |
| `UDM_BENCH_WORLD`         | all launch files       | Which world to load (must match `sim/worlds/*.world`)  |
| `UDM_BENCH_BAG_DURATION_S`| `_common.py`           | Stop the recorder after N seconds (default 90)     |
| `TURTLEBOT3_MODEL`        | TB3 + multi-vendor     | `burger`, `waffle`, or `waffle_pi`                 |
| `PX4_HOME`                | PX4 + multi-vendor     | PX4-Autopilot checkout root (default `/opt/PX4-Autopilot`) |

