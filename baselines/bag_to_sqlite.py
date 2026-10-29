"""Condition B converter: rosbag2 ``.db3`` -> per-topic SQL tables.

Builds (or extends) a ``telemetry.sqlite`` database holding one table per
``(vendor, topic)`` pair. Column names follow each vendor's native message
schema (flattened with ``__``), so the Condition B agent must bridge vendor
terminology itself — exactly the friction UDM is meant to remove.

Table naming: ``<vendor>__<topic>`` with non-identifier characters replaced by
``_`` (e.g. ``turtlebot3__scan``, ``px4__fmu_out_vehicle_status``). A
``_messages`` meta-table records the original topic/type/vendor for each table.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from baselines.bag_reader import decimate, iter_messages, read_topics
from baselines.flatten import flatten_scalars

_COL_TYPES = {bool: "INTEGER", int: "INTEGER", float: "REAL", str: "TEXT"}


def table_name(vendor: str, topic: str) -> str:
    """Map a ``(vendor, topic)`` pair to a safe SQL identifier."""
    raw = f"{vendor}__{topic.lstrip('/')}"
    safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in raw)
    if safe and safe[0].isdigit():
        safe = f"t_{safe}"
    return safe


def _sql_type(value: Any) -> str:
    return _COL_TYPES.get(type(value), "TEXT")


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _messages ("
        "table_name TEXT PRIMARY KEY, vendor TEXT, source_id TEXT, "
        "topic TEXT, msgtype TEXT, message_count INTEGER)"
    )


def bag_to_sqlite(
    bag: str,
    db_path: str,
    *,
    vendor: str,
    source_id: str,
    topics: list[str] | None = None,
    max_hz: float | None = None,
) -> dict[str, int]:
    """Load every topic in ``bag`` into ``db_path`` as per-topic tables.

    Returns ``{table_name: rows_inserted}``. Idempotent per table: an existing
    table for the same ``(vendor, topic)`` is dropped and rebuilt so re-running
    the prepare step never double-counts.
    """
    wanted = set(topics) if topics else None
    bag_topics = [t for t in read_topics(bag) if wanted is None or t.name in wanted]
    type_by_topic = {t.name: t.msgtype for t in bag_topics}

    # Single pass: bucket (t_ns, flattened-fields) per topic. We need the union
    # of columns before CREATE TABLE, and recorded bags are small enough to
    # hold in memory.
    rows_by_topic: dict[str, list[tuple[int, dict[str, Any]]]] = {t.name: [] for t in bag_topics}
    for msg in decimate(iter_messages(bag, topics=list(type_by_topic) or None), max_hz=max_hz):
        rows_by_topic.setdefault(msg.topic, []).append((msg.t_ns, flatten_scalars(msg.fields)))

    inserted: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        _ensure_meta(conn)
        for topic, rows in rows_by_topic.items():
            tbl = table_name(vendor, topic)
            field_rows = [fields for _, fields in rows]
            columns = _ordered_columns(field_rows)
            col_types = _infer_types(columns, field_rows)
            conn.execute(f'DROP TABLE IF EXISTS "{tbl}"')
            col_defs = ", ".join(f'"{c}" {col_types[c]}' for c in columns)
            conn.execute(
                f'CREATE TABLE "{tbl}" ("_t_ns" INTEGER'
                + (", " + col_defs if columns else "")
                + ")"
            )
            placeholders = ", ".join(["?"] * (len(columns) + 1))
            conn.executemany(
                f'INSERT INTO "{tbl}" VALUES ({placeholders})',
                [[t_ns] + [fields.get(c) for c in columns] for t_ns, fields in rows],
            )
            inserted[tbl] = len(rows)
            conn.execute(
                "INSERT OR REPLACE INTO _messages VALUES (?, ?, ?, ?, ?, ?)",
                (tbl, vendor, source_id, topic, type_by_topic.get(topic, ""), len(rows)),
            )
        conn.commit()
    return inserted


def _ordered_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Union of column names across rows, preserving first-seen order."""
    seen: dict[str, None] = {}
    for r in rows:
        for k in r:
            seen.setdefault(k, None)
    return list(seen)


def _infer_types(columns: list[str], rows: list[dict[str, Any]]) -> dict[str, str]:
    types: dict[str, str] = {}
    for c in columns:
        chosen = "TEXT"
        for r in rows:
            v = r.get(c)
            if v is not None:
                chosen = _sql_type(v)
                break
        types[c] = chosen
    return types
