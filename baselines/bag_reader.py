"""Read a rosbag2 SQLite bag and yield decoded messages as plain Python.

The recorded bags are rosbag2 ``.db3`` files (SQLite storage plugin). We read
the ``topics`` and ``messages`` tables directly rather than relying on the
high-level :class:`rosbags.rosbag2.Reader`, because the bags produced inside the
sim containers do not always ship a ``metadata.yaml`` alongside the ``.db3``.

CDR payloads are deserialized with the pure-Python :mod:`rosbags` typestore
(ROS 2 Humble), so no ROS installation is required. Message objects are
converted to plain dicts / lists / scalars (:func:`to_plain`) so that the
downstream text and SQL converters never touch ``rosbags`` types.
"""

from __future__ import annotations

import dataclasses
import glob
import os
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

#: Suffix some recorded PX4 topics carry from the recording relay. Stripped on
#: read so every artifact shows the canonical ``/fmu/out/<x>`` name.
_RELAY_OUT_SUFFIX = "__faulted"


def canonical_topic(name: str) -> str:
    """Strip the recording relay's suffix; a no-op for every other topic."""
    if name.endswith(_RELAY_OUT_SUFFIX):
        return name[: -len(_RELAY_OUT_SUFFIX)]
    return name


try:  # pragma: no cover - import guard
    from rosbags.typesys import Stores, get_typestore

    _TYPESTORE: Any = get_typestore(Stores.ROS2_HUMBLE)
except Exception:  # pragma: no cover - rosbags optional at import time
    _TYPESTORE = None


# Vendored px4_msgs ``.msg`` definitions (snapshot of the px4_msgs commit pinned
# in ``sim/Dockerfile.px4``). The stock ROS 2 Humble typestore has no knowledge
# of the PX4 ``/fmu/*`` custom types, so without registering these every PX4
# message decodes to ``KeyError: 'px4_msgs/msg/...'`` and the multi-vendor PX4
# telemetry is unusable for the baseline converters.
_PX4_MSG_DIR = os.path.join(os.path.dirname(__file__), "px4_msgs_defs", "msg")


def _register_px4_types(typestore: Any) -> int:
    """Register vendored px4_msgs types with ``typestore``. Best-effort.

    Returns the number of types registered (0 if rosbags is absent, the
    vendored defs are missing, or the rosbags API differs).
    """
    if typestore is None or not os.path.isdir(_PX4_MSG_DIR):
        return 0
    try:  # pragma: no cover - depends on optional rosbags
        from rosbags.typesys import get_types_from_msg
    except Exception:
        return 0
    types: dict[str, Any] = {}
    for path in sorted(glob.glob(os.path.join(_PX4_MSG_DIR, "*.msg"))):
        name = f"px4_msgs/msg/{os.path.splitext(os.path.basename(path))[0]}"
        try:
            with open(path, encoding="utf-8") as fh:
                types.update(get_types_from_msg(fh.read(), name))
        except Exception:  # noqa: BLE001 - skip any unparseable def
            continue
    if not types:
        return 0
    try:  # pragma: no cover - depends on optional rosbags
        typestore.register(types)
    except Exception:
        return 0
    return len(types)


if _TYPESTORE is not None:  # pragma: no cover - exercised only with rosbags
    _register_px4_types(_TYPESTORE)


@dataclass(frozen=True)
class TopicInfo:
    """One recorded topic."""

    name: str
    msgtype: str
    count: int


@dataclass(frozen=True)
class DecodedMessage:
    """One decoded message: a plain-Python view of a single bag row."""

    topic: str
    msgtype: str
    t_ns: int
    fields: dict[str, Any]


def to_plain(obj: Any) -> Any:
    """Recursively convert a rosbags message object to plain Python.

    * message dataclasses -> ``dict`` (dropping the internal ``__msgtype__``)
    * numpy arrays -> ``list``
    * numpy scalars -> Python scalars
    * bytes -> hex string
    * everything else returned unchanged
    """
    # numpy is a transitive dependency of rosbags; import lazily so this module
    # stays importable (for the synthetic-stream tests) even if numpy is absent.
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            if f.name == "__msgtype__":
                continue
            out[f.name] = to_plain(getattr(obj, f.name))
        return out
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).hex()
    # numpy types expose ``.tolist()`` / ``.item()`` without an explicit import.
    if hasattr(obj, "tolist") and not isinstance(obj, (str, bytes)):
        return obj.tolist()
    if hasattr(obj, "item") and obj.__class__.__module__ == "numpy":
        return obj.item()
    if isinstance(obj, (list, tuple)):
        return [to_plain(x) for x in obj]
    return obj


def find_db3(bag_dir: str) -> str:
    """Return the ``.db3`` file inside a rosbag2 bag directory.

    Accepts either the bag directory or the ``.db3`` path directly.
    """
    if os.path.isfile(bag_dir) and bag_dir.endswith(".db3"):
        return bag_dir
    matches = sorted(glob.glob(os.path.join(bag_dir, "*.db3")))
    if not matches:
        raise FileNotFoundError(f"no .db3 file found under {bag_dir!r}")
    return matches[0]


def read_topics(bag: str) -> list[TopicInfo]:
    """Return the topics in a bag with per-topic message counts."""
    db = find_db3(bag)
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT t.name, t.type, COUNT(m.id) "
            "FROM topics t LEFT JOIN messages m ON m.topic_id = t.id "
            "GROUP BY t.id ORDER BY t.name"
        ).fetchall()
    return [TopicInfo(name=canonical_topic(r[0]), msgtype=r[1], count=int(r[2])) for r in rows]


def iter_messages(
    bag: str,
    *,
    topics: list[str] | None = None,
    typestore: Any | None = None,
) -> Iterator[DecodedMessage]:
    """Yield :class:`DecodedMessage` rows in chronological (timestamp) order.

    Messages whose type cannot be deserialized are still yielded, with
    ``fields={"_decode_error": "..."}`` so the converters can record the gap
    instead of crashing the whole mission.
    """
    ts = typestore if typestore is not None else _TYPESTORE
    if ts is None:  # pragma: no cover - exercised only without rosbags installed
        raise RuntimeError(
            "rosbags is required to decode bags; install with 'pip install rosbags' "
            "or the 'bag' extra"
        )
    db = find_db3(bag)
    wanted = set(topics) if topics else None
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        q = (
            "SELECT t.name, t.type, m.timestamp, m.data "
            "FROM messages m JOIN topics t ON m.topic_id = t.id "
            "ORDER BY m.timestamp ASC"
        )
        for name, typ, t_ns, data in conn.execute(q):
            name = canonical_topic(name)
            if wanted is not None and name not in wanted:
                continue
            try:
                msg = ts.deserialize_cdr(bytes(data), typ)
                fields = to_plain(msg)
            except Exception as exc:  # noqa: BLE001 - degrade, never crash a mission
                fields = {"_decode_error": f"{type(exc).__name__}: {exc}"}
            yield DecodedMessage(topic=name, msgtype=typ, t_ns=int(t_ns), fields=fields)


def decimate(
    messages: Iterable[DecodedMessage], *, max_hz: float | None
) -> Iterator[DecodedMessage]:
    """Rate-limit a message stream to at most ``max_hz`` per topic per second.

    Buckets each topic's timeline into ``1/max_hz``-second windows and keeps the
    first message in each window. ``max_hz`` of ``None`` or ``<= 0`` is a no-op
    (the stream passes through unchanged).

    This is the single downsampling primitive shared by the Condition A/B
    converters (:mod:`baselines.bag_to_text`, :mod:`baselines.bag_to_sqlite`) and
    the UDM ingest used for the UDM conditions, so every condition sees
    identically-decimated data and cross-condition comparisons stay fair.
    """
    if not max_hz or max_hz <= 0:
        yield from messages
        return
    bucket_ns = int(1e9 / max_hz)
    seen: set[tuple[str, int]] = set()
    for msg in messages:
        key = (msg.topic, msg.t_ns // bucket_ns)
        if key in seen:
            continue
        seen.add(key)
        yield msg
