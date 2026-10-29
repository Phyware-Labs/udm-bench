"""Condition A converter: rosbag2 ``.db3`` -> chronological text dump.

Produces ``bag_<vendor>_<source_id>.txt`` next to the recorded bag directory.
The format is deliberately simple and vendor-native — one line per message,
``[t=<seconds>] <topic> (<msgtype>) <flattened fields>`` — so the Condition A
agent sees raw decoded telemetry with no structured query surface.

The decoding is delegated to :mod:`baselines.bag_reader`; the line-rendering
logic here is pure and unit-tested against synthetic ``DecodedMessage`` streams.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

from baselines.bag_reader import DecodedMessage, decimate, iter_messages, read_topics
from baselines.flatten import flatten_scalars


def _fmt_value(value: Any) -> str:
    if isinstance(value, float):
        # Keep dumps compact but lossless enough for diagnosis.
        return f"{value:.6g}"
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def render_message(msg: DecodedMessage, *, t0_ns: int) -> str:
    """Render a single decoded message as one text line.

    ``t0_ns`` is the mission's first-message timestamp so the printed time is
    seconds-since-start rather than an absolute epoch.
    """
    t_s = (msg.t_ns - t0_ns) / 1e9
    scalars = flatten_scalars(msg.fields)
    body = " ".join(f"{k}={_fmt_value(v)}" for k, v in sorted(scalars.items()))
    return f"[t={t_s:9.3f}] {msg.topic} ({msg.msgtype}) {body}"


def render_lines(messages: Iterable[DecodedMessage]) -> Iterator[str]:
    """Yield rendered text lines for a chronological message stream."""
    t0_ns: int | None = None
    for msg in messages:
        if t0_ns is None:
            t0_ns = msg.t_ns
        yield render_message(msg, t0_ns=t0_ns)


def _header(bag: str, vendor: str, source_id: str) -> Iterator[str]:
    yield f"# UDM-Bench raw bag dump — vendor={vendor} source_id={source_id}"
    topics = read_topics(bag)
    yield f"# topics ({len(topics)}):"
    for t in topics:
        yield f"#   {t.name}  type={t.msgtype}  messages={t.count}"
    yield "#"


def bag_to_text(
    bag: str,
    out_path: str,
    *,
    vendor: str,
    source_id: str,
    topics: list[str] | None = None,
    max_hz: float | None = None,
) -> int:
    """Write a chronological text dump of ``bag`` to ``out_path``.

    When ``max_hz`` is set the stream is decimated to at most ``max_hz`` per
    topic per second (shared :func:`baselines.bag_reader.decimate`), so the
    Condition A dump matches the resolution of the UDM event store.

    Returns the number of message lines written.
    """
    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for line in _header(bag, vendor, source_id):
            f.write(line + "\n")
        stream = decimate(iter_messages(bag, topics=topics), max_hz=max_hz)
        for line in render_lines(stream):
            f.write(line + "\n")
            count += 1
    return count
