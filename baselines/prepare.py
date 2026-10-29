"""Mission artifact preparation — turn recorded bags into baseline inputs.

A mission directory produced by the orchestrator contains one recorded bag per
participating source::

    runs/<mission_id>/
        bag_<vendor>_<source_id>/   # rosbag2 .db3 directory
        ...

:func:`prepare_mission` scans for those bags and produces the artifacts the
baseline conditions read:

* ``bag_<vendor>_<source_id>.txt`` — Condition A
* ``telemetry.sqlite`` — Condition B, one table per (vendor, topic)

It is safe to call repeatedly: text dumps are overwritten and SQL tables are
rebuilt per ``(vendor, topic)``. The step is a no-op (returns an empty summary)
when a mission has no recorded bags, so it can run unconditionally before the
harness even for plan-only missions.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from baselines.bag_reader import find_db3
from baselines.bag_to_sqlite import bag_to_sqlite
from baselines.bag_to_text import bag_to_text

log = logging.getLogger("baselines.prepare")

# Vendor tokens never contain an underscore, so the source_id is everything
# after the first ``_`` following the vendor.
KNOWN_VENDORS = ("turtlebot3", "px4")


@dataclass(frozen=True)
class BagRef:
    """A located bag directory and its parsed identity."""

    path: Path
    vendor: str
    source_id: str


@dataclass
class PrepareSummary:
    """What :func:`prepare_mission` produced for one mission."""

    mission_dir: str
    bags: list[str] = field(default_factory=list)
    text_files: dict[str, int] = field(default_factory=dict)  # path -> line count
    sqlite_tables: dict[str, int] = field(default_factory=dict)  # table -> rows
    sqlite_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "mission_dir": self.mission_dir,
            "bags": self.bags,
            "text_files": self.text_files,
            "sqlite_tables": self.sqlite_tables,
            "sqlite_path": self.sqlite_path,
        }


def parse_bag_dirname(name: str) -> tuple[str, str] | None:
    """Parse ``bag_<vendor>_<source_id>`` -> ``(vendor, source_id)``.

    Returns ``None`` if ``name`` is not a recognised bag directory name.
    """
    if not name.startswith("bag_"):
        return None
    rest = name[len("bag_") :]
    for vendor in KNOWN_VENDORS:
        prefix = f"{vendor}_"
        if rest.startswith(prefix):
            source_id = rest[len(prefix) :]
            if source_id:
                return vendor, source_id
    return None


def find_bags(mission_dir: Path) -> list[BagRef]:
    """Locate recorded bag directories inside a mission directory."""
    bags: list[BagRef] = []
    for child in sorted(mission_dir.iterdir()):
        if not child.is_dir():
            continue
        parsed = parse_bag_dirname(child.name)
        if parsed is None:
            continue
        try:
            find_db3(str(child))
        except FileNotFoundError:
            log.warning("bag dir %s has no .db3; skipping", child)
            continue
        vendor, source_id = parsed
        bags.append(BagRef(path=child, vendor=vendor, source_id=source_id))
    return bags


def prepare_mission(
    mission_dir: str | os.PathLike[str], *, max_hz: float | None = None
) -> PrepareSummary:
    """Produce Condition A/B artifacts for one mission directory.

    ``max_hz`` decimates every topic to at most that rate (shared with the UDM
    ingest) so Conditions A/B can be regenerated at the same resolution the UDM
    conditions use, for a fair cross-condition comparison.
    """
    mdir = Path(mission_dir)
    summary = PrepareSummary(mission_dir=str(mdir))
    if not mdir.is_dir():
        raise FileNotFoundError(mdir)

    bags = find_bags(mdir)
    if not bags:
        log.info("no recorded bags under %s; nothing to prepare", mdir)
        return summary

    db_path = mdir / "telemetry.sqlite"
    # Rebuild from scratch so re-runs never accumulate stale tables.
    if db_path.exists():
        db_path.unlink()
    summary.sqlite_path = str(db_path)

    for bag in bags:
        summary.bags.append(bag.path.name)
        txt_path = mdir / f"bag_{bag.vendor}_{bag.source_id}.txt"
        lines = bag_to_text(
            str(bag.path),
            str(txt_path),
            vendor=bag.vendor,
            source_id=bag.source_id,
            max_hz=max_hz,
        )
        summary.text_files[txt_path.name] = lines

        tables = bag_to_sqlite(
            str(bag.path),
            str(db_path),
            vendor=bag.vendor,
            source_id=bag.source_id,
            max_hz=max_hz,
        )
        summary.sqlite_tables.update(tables)
        log.info(
            "prepared %s: %d text lines, %d tables",
            bag.path.name,
            lines,
            len(tables),
        )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare baseline artifacts for a mission")
    parser.add_argument("mission_dir", type=Path, help="path to a runs/<mission_id>/ directory")
    parser.add_argument(
        "--max-hz",
        type=float,
        default=None,
        help="decimate every topic to at most this rate (match the UDM ingest).",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s | %(message)s"
    )
    summary = prepare_mission(args.mission_dir, max_hz=args.max_hz)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
