"""Tests for the bag reader + Condition A/B converters.

The reader/converter integration tests build a synthetic rosbag2 ``.db3`` (see
:mod:`tests.baselines._bagfixture`) so CDR deserialization is exercised for
real. The pure rendering / SQL-helper logic is also tested directly against
synthetic ``DecodedMessage`` streams.
"""

from __future__ import annotations

import sqlite3

import pytest

from baselines.bag_reader import DecodedMessage, iter_messages, read_topics, to_plain
from baselines.bag_to_sqlite import bag_to_sqlite, table_name
from baselines.bag_to_text import render_lines, render_message
from tests.baselines._bagfixture import make_twist, write_bag

TWIST = "geometry_msgs/msg/Twist"


@pytest.fixture
def twist_bag(tmp_path):
    return write_bag(
        tmp_path / "bag_turtlebot3_tb3_0",
        [
            ("/cmd_vel", TWIST, 1_000_000_000, make_twist(0.1, 0.0)),
            ("/cmd_vel", TWIST, 1_500_000_000, make_twist(0.2, 0.5)),
            ("/cmd_vel", TWIST, 2_000_000_000, make_twist(0.0, -0.5)),
        ],
    )


# ------------------------------- bag_reader --------------------------------


def test_read_topics_counts(twist_bag):
    topics = read_topics(str(twist_bag))
    assert len(topics) == 1
    assert topics[0].name == "/cmd_vel"
    assert topics[0].msgtype == TWIST
    assert topics[0].count == 3


def test_iter_messages_decodes_in_order(twist_bag):
    msgs = list(iter_messages(str(twist_bag)))
    assert [m.t_ns for m in msgs] == [1_000_000_000, 1_500_000_000, 2_000_000_000]
    assert msgs[0].fields["linear"]["x"] == pytest.approx(0.1)
    assert msgs[1].fields["angular"]["z"] == pytest.approx(0.5)


def test_iter_messages_topic_filter(twist_bag):
    assert list(iter_messages(str(twist_bag), topics=["/nope"])) == []
    assert len(list(iter_messages(str(twist_bag), topics=["/cmd_vel"]))) == 3


def test_to_plain_handles_bytes_and_scalars():
    assert to_plain(b"\x01\x02") == "0102"
    assert to_plain("x") == "x"
    assert to_plain([1, 2]) == [1, 2]


# ------------------------------- bag_to_text -------------------------------


def test_render_message_uses_relative_time():
    msg = DecodedMessage(
        topic="/imu", msgtype="sensor_msgs/msg/Imu", t_ns=2_000_000_000, fields={"a": 1}
    )
    line = render_message(msg, t0_ns=1_000_000_000)
    assert "/imu" in line
    assert "[t=    1.000]" in line
    assert "a=1" in line


def test_render_lines_first_message_is_zero():
    stream = [
        DecodedMessage(topic="/t", msgtype="m", t_ns=5_000_000_000, fields={"v": 1}),
        DecodedMessage(topic="/t", msgtype="m", t_ns=6_000_000_000, fields={"v": 2}),
    ]
    lines = list(render_lines(stream))
    assert "[t=    0.000]" in lines[0]
    assert "[t=    1.000]" in lines[1]


def test_bag_to_text_writes_header_and_lines(twist_bag, tmp_path):
    from baselines.bag_to_text import bag_to_text

    out = tmp_path / "out.txt"
    n = bag_to_text(str(twist_bag), str(out), vendor="turtlebot3", source_id="tb3_0")
    assert n == 3
    text = out.read_text(encoding="utf-8")
    assert "# UDM-Bench raw bag dump" in text
    assert "messages=3" in text
    assert text.count("/cmd_vel") >= 3


# ------------------------------ bag_to_sqlite ------------------------------


def test_table_name_sanitizes():
    assert table_name("turtlebot3", "/scan") == "turtlebot3__scan"
    assert table_name("px4", "/fmu/out/vehicle_status") == "px4__fmu_out_vehicle_status"
    assert not table_name("px4", "/1bad")[0].isdigit()


def test_bag_to_sqlite_flattens_columns(twist_bag, tmp_path):
    db = tmp_path / "telemetry.sqlite"
    inserted = bag_to_sqlite(str(twist_bag), str(db), vendor="turtlebot3", source_id="tb3_0")
    assert inserted == {"turtlebot3__cmd_vel": 3}
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(turtlebot3__cmd_vel)")}
        assert {"_t_ns", "linear__x", "angular__z"} <= cols
        rows = conn.execute("SELECT linear__x FROM turtlebot3__cmd_vel ORDER BY _t_ns").fetchall()
        assert rows[0][0] == pytest.approx(0.1)
        meta = conn.execute("SELECT vendor, source_id, message_count FROM _messages").fetchone()
        assert meta == ("turtlebot3", "tb3_0", 3)


def test_bag_to_sqlite_is_idempotent(twist_bag, tmp_path):
    db = tmp_path / "telemetry.sqlite"
    bag_to_sqlite(str(twist_bag), str(db), vendor="turtlebot3", source_id="tb3_0")
    bag_to_sqlite(str(twist_bag), str(db), vendor="turtlebot3", source_id="tb3_0")
    with sqlite3.connect(db) as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM turtlebot3__cmd_vel").fetchone()
        assert count == 3  # rebuilt, not doubled
