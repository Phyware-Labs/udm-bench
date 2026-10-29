"""Mission-scoped ground-truth event logger.

Every injection produces a JSON record with
``vendor`` and ``source_id`` fields. Multi-vendor missions must be able to
join cross-vendor attribution against this log.

The on-disk layout is::

    bench/runs/<mission_id>/ground_truth.json

…which under this repo (no ``bench/`` prefix) becomes::

    runs/<mission_id>/ground_truth.json
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from faults.base import InjectionRecord


class GroundTruthLogger:
    """Append-only JSON-array writer for a single mission's injection records.

    The file is written atomically (write-temp + rename) on every append so a
    crashed mission still leaves a parseable answer-key on disk.
    """

    def __init__(self, runs_root: str | Path, mission_id: str) -> None:
        self.runs_root = Path(runs_root)
        self.mission_id = mission_id
        self._records: list[InjectionRecord] = []
        self.mission_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    @property
    def mission_dir(self) -> Path:
        return self.runs_root / self.mission_id

    @property
    def ground_truth_path(self) -> Path:
        return self.mission_dir / "ground_truth.json"

    # ------------------------------------------------------------------ writes

    def log(self, record: InjectionRecord) -> None:
        """Append one injection record and flush to disk atomically."""
        self._validate(record)
        self._records.append(record)
        self._flush()

    def log_many(self, records: Iterable[InjectionRecord]) -> None:
        for r in records:
            self._validate(r)
            self._records.append(r)
        self._flush()

    def records(self) -> tuple[InjectionRecord, ...]:
        return tuple(self._records)

    # ------------------------------------------------------------------ internal

    def _validate(self, record: InjectionRecord) -> None:
        if record.mission_id != self.mission_id:
            raise ValueError(
                f"record.mission_id={record.mission_id!r} does not match "
                f"logger.mission_id={self.mission_id!r}"
            )
        if record.vendor not in {"turtlebot3", "px4"}:
            raise ValueError(f"unsupported vendor: {record.vendor!r}")
        if not record.source_id:
            raise ValueError("source_id is required (multi-vendor attribution scoring)")
        if not record.fault_id:
            raise ValueError("fault_id is required")
        if record.injection_time < 0:
            raise ValueError("injection_time must be >= 0")

    def _flush(self) -> None:
        payload: dict[str, Any] = {
            "mission_id": self.mission_id,
            "schema_version": 1,
            "injections": [r.to_dict() for r in self._records],
        }
        # Atomic write: tmp file in the same dir, then rename.
        fd, tmp_path = tempfile.mkstemp(
            prefix=".ground_truth.", suffix=".json", dir=str(self.mission_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp_path, self.ground_truth_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


def load_ground_truth(path: str | Path) -> list[InjectionRecord]:
    """Re-hydrate ground-truth records from disk (used by the scoring harness)."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported ground_truth schema_version: {data.get('schema_version')!r}")
    out: list[InjectionRecord] = []
    for raw in data.get("injections", []):
        out.append(
            InjectionRecord(
                vendor=raw["vendor"],
                fault_id=raw["fault_id"],
                source_id=raw["source_id"],
                injection_time=float(raw["injection_time"]),
                mission_id=raw["mission_id"],
                parameters=dict(raw.get("parameters", {})),
            )
        )
    return out
