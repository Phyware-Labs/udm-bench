# `sim/` — Reproducible multi-platform simulation environment

The ROS 2 / Gazebo / PX4 SITL environment the benchmark's missions were recorded
in. The public release records **clean** missions: sensor topics pass through
unchanged (see `launch/passthrough_relay.py`). The fault injectors and the
mission runner that produced the benchmark's faulted missions are not part of
this repository; see the top-level README.

Provides three Docker Compose profiles:

| Profile        | What boots                                                   | Boot budget |
| -------------- | ------------------------------------------------------------ | ----------- |
| `turtlebot3`   | TurtleBot3 + Nav2 + Gazebo (ROS2 humble)                     | ≤ 60 s      |
| `px4`          | PX4 SITL + Gazebo + `px4_ros_com` ROS2 bridge (`px4_msgs`)   | ≤ 90 s      |
| `multi-vendor` | Both above, in a shared `multi_vendor_warehouse` world       | ≤ 120 s     |

No GPU required. CPU-only. Works on a clean Linux laptop and on the GitHub
Actions Ubuntu runner.

## Usage

```bash
# TurtleBot3 profile
docker compose -f sim/docker-compose.yml --profile turtlebot3 up

# PX4 SITL profile
docker compose -f sim/docker-compose.yml --profile px4 up

# Multi-vendor (both)
docker compose -f sim/docker-compose.yml --profile multi-vendor up
```

## Record a mission by hand

```bash
# 1. Build the images (cached; ~15 min the first time)
docker compose -f sim/docker-compose.yml --profile turtlebot3 build

# 2. Record one mission (the recorder stops after UDM_BENCH_BAG_DURATION_S)
UDM_BENCH_MISSION_ID=demo-0001 \
    docker compose -f sim/docker-compose.yml --profile turtlebot3 up

# 3. Check the bag
ls runs/demo-0001/bag_turtlebot3_tb3_0*
```

To run the baselines on it, add a `mission_meta.json` (see
`tests/test_pipeline_smoke.py` for the fields), then
`python -m baselines.prepare runs/demo-0001` and `python -m harness.run`.

## Host portability

The compose file is tested against Docker on Ubuntu 22.04 / 24.04 and
should also work on:

| Host              | Notes                                                                    |
| ----------------- | ------------------------------------------------------------------------ |
| RHEL 8/9, Rocky 8/9, Fedora | SELinux enforcing is fine — bind mounts use the `:Z` suffix so Docker relabels the host directory per-container. |
| Podman (any distro) | Compose syntax works with `podman compose` ≥ 4.4. The `cpus:` / `mem_limit:` keys are honoured; container names use the same `udm-bench-*` prefix. |
| Rootless Docker / Podman | Bind-mount path must be readable+writable by the user running the daemon. Set `UDM_BENCH_RUNS_ROOT_HOST=/absolute/host/path` to override the default `../runs` if rootless can't resolve the relative path. |

Override the host-side artifact directory without touching the compose
file:

```bash
UDM_BENCH_RUNS_ROOT_HOST=/data/udm-bench-runs \
    docker compose -f sim/docker-compose.yml --profile turtlebot3 up
```

## Worlds

Checked in under [worlds/](worlds/):

| World                       | Used by profile         | Source                  |
| --------------------------- | ----------------------- | ----------------------- |
| `turtlebot3_world`          | `turtlebot3`            | This repo (minimal SDF) |
| `small_warehouse`           | `turtlebot3`            | This repo (minimal SDF) |
| `px4_default_world`         | `px4`                   | This repo (minimal SDF) |
| `multi_vendor_warehouse`    | `multi-vendor`          | This repo (minimal SDF) |

## Launch files

Per-profile ROS2 launch files live in [launch/](launch/). Each launch file
boots only the ROS2 stack components that profile needs (Nav2 stack for
`turtlebot3`, `px4_ros_com` bridge for `px4`, both for `multi-vendor`)
and a `rosbag2` recorder configured via environment variables (see
[launch/README.md](launch/README.md)).
