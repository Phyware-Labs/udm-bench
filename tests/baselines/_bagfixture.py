"""Shared helpers for baseline-converter tests.

Builds a minimal rosbag2 SQLite ``.db3`` with CDR-serialized messages using the
pure-Python :mod:`rosbags` typestore, so the bag reader and converters get real
deserialization coverage without a ROS install or a recorded bag.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

rosbags = pytest.importorskip("rosbags")
from rosbags.typesys import Stores, get_typestore  # noqa: E402

TS = get_typestore(Stores.ROS2_HUMBLE)

_SCHEMA = """
CREATE TABLE topics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    serialization_format TEXT NOT NULL,
    offered_qos_profiles TEXT NOT NULL
);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    data BLOB NOT NULL
);
"""


def make_twist(lx: float, az: float):
    """A ``geometry_msgs/msg/Twist`` with nested Vector3 fields."""
    Twist = TS.types["geometry_msgs/msg/Twist"]
    Vector3 = TS.types["geometry_msgs/msg/Vector3"]
    return Twist(
        linear=Vector3(x=lx, y=0.0, z=0.0),
        angular=Vector3(x=0.0, y=0.0, z=az),
    )


def write_bag(
    bag_dir: Path,
    messages: list[tuple[str, str, int, object]],
) -> Path:
    """Write ``messages`` (topic, msgtype, t_ns, msg) into a rosbag2 ``.db3``.

    Returns the bag directory path. The directory name is reused for the
    ``.db3`` filename, mirroring how rosbag2 lays bags out on disk.
    """
    bag_dir.mkdir(parents=True, exist_ok=True)
    db = bag_dir / f"{bag_dir.name}_0.db3"
    topic_ids: dict[str, int] = {}
    with sqlite3.connect(db) as conn:
        conn.executescript(_SCHEMA)
        next_topic = 1
        next_msg = 1
        for topic, msgtype, t_ns, msg in messages:
            if topic not in topic_ids:
                conn.execute(
                    "INSERT INTO topics VALUES (?, ?, ?, ?, ?)",
                    (next_topic, topic, msgtype, "cdr", ""),
                )
                topic_ids[topic] = next_topic
                next_topic += 1
            data = TS.serialize_cdr(msg, msgtype)
            conn.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?)",
                (next_msg, topic_ids[topic], t_ns, bytes(data)),
            )
            next_msg += 1
        conn.commit()
    return bag_dir
