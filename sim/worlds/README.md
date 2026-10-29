# `sim/worlds/`

Checked-in Gazebo world files used by the udm-bench Docker profiles.

| File                              | Used by                | Source / status            |
| --------------------------------- | ---------------------- | -------------------------- |
| `turtlebot3_world.world`          | `turtlebot3` profile   | Minimal SDF (this repo)    |
| `small_warehouse.world`           | `turtlebot3` profile   | Minimal SDF (this repo)    |
| `px4_default_world.world`         | `px4` profile          | Minimal SDF (this repo)    |
| `multi_vendor_warehouse.world`    | `multi-vendor` profile | Minimal SDF (this repo)    |

All four worlds load with stock Gazebo Classic 11 (the version that
ships with `osrf/ros:humble-desktop-full`). They reference only the
built-in `model://sun` and `model://ground_plane` models, plus inline
geometry — no external model downloads required at boot time.

Worlds are checked in (not generated at image-build time) so the
experiment is bit-for-bit reproducible across CI and local runs.

