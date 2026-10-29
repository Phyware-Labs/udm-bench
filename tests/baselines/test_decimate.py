"""Tests for the shared ``decimate`` primitive and ``max_hz`` plumbing."""

from __future__ import annotations

from baselines.bag_reader import DecodedMessage, decimate
from baselines.bag_to_text import bag_to_text
from tests.baselines._bagfixture import make_twist, write_bag

TWIST = "geometry_msgs/msg/Twist"


def _msgs(topic: str, ts: list[int]) -> list[DecodedMessage]:
    return [DecodedMessage(topic=topic, msgtype="X", t_ns=t, fields={}) for t in ts]


def test_decimate_keeps_first_per_time_bucket():
    ts = [int(i * 1e8) for i in range(10)]  # 10 msgs over ~1 s (10 Hz)
    out = list(decimate(_msgs("/a", ts), max_hz=2))  # bucket = 0.5 s
    assert [m.t_ns for m in out] == [0, int(5e8)]


def test_decimate_is_per_topic():
    msgs = _msgs("/a", [0, int(1e8)]) + _msgs("/b", [0, int(1e8)])
    out = list(decimate(msgs, max_hz=2))
    # Each topic keeps its own first-in-bucket independently.
    assert sorted((m.topic, m.t_ns) for m in out) == [("/a", 0), ("/b", 0)]


def test_decimate_noop_when_disabled():
    ts = [0, 1, 2]
    assert [m.t_ns for m in decimate(_msgs("/a", ts), max_hz=None)] == ts
    assert [m.t_ns for m in decimate(_msgs("/a", ts), max_hz=0)] == ts


def test_bag_to_text_max_hz_reduces_lines(tmp_path):
    bag = tmp_path / "bag_turtlebot3_tb3_0"
    # 10 messages over ~1 s on one topic (10 Hz).
    msgs = [("/cmd_vel", TWIST, int(i * 1e8), make_twist(0.1 * i, 0.0)) for i in range(10)]
    write_bag(bag, msgs)
    out = tmp_path / "dump.txt"

    full = bag_to_text(str(bag), str(out), vendor="turtlebot3", source_id="tb3_0")
    capped = bag_to_text(str(bag), str(out), vendor="turtlebot3", source_id="tb3_0", max_hz=2)
    assert full == 10
    assert capped == 2  # 0.5 s buckets -> 2 kept
