"""Baseline data-preparation utilities for UDM-Bench Phase 2.

These modules turn a recorded ROS2 bag (rosbag2 SQLite ``.db3``) into the
artifacts the baseline conditions consume:

* :mod:`baselines.bag_to_text` — a chronological text dump (Condition A)
* :mod:`baselines.bag_to_sqlite` — one SQL table per topic (Condition B)

The heavy CDR deserialization is isolated in :mod:`baselines.bag_reader`, so the
text/SQL formatting logic can be unit-tested against synthetic decoded-message
streams without a ROS install.
"""

from __future__ import annotations

from baselines.bag_to_sqlite import bag_to_sqlite
from baselines.bag_to_text import bag_to_text
from baselines.prepare import PrepareSummary, prepare_mission

__all__ = [
    "PrepareSummary",
    "bag_to_sqlite",
    "bag_to_text",
    "prepare_mission",
]
