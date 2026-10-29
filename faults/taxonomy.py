"""Loader + validator for the fault taxonomy (``faults/taxonomy.yaml``).

The taxonomy is the answer label space: the fault ids an agent may submit, with
the platform and short description shown in the ``submit_diagnosis`` tool. Run
as a module to validate it::

    python -m faults.taxonomy --validate faults/taxonomy.yaml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_VALID_VENDORS = {"turtlebot3", "px4"}
_REQUIRED_KEYS = {"id", "vendor", "platform", "name", "description"}

DEFAULT_PATH = Path(__file__).resolve().parent / "taxonomy.yaml"


@dataclass(frozen=True)
class FaultLabel:
    id: str
    vendor: str
    platform: str
    name: str
    description: str


@dataclass(frozen=True)
class Taxonomy:
    version: int
    entries: tuple[FaultLabel, ...]

    def ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.entries)


class TaxonomyError(ValueError):
    """Raised when ``taxonomy.yaml`` is malformed."""


def _validate(raw: Any) -> Taxonomy:
    if not isinstance(raw, dict) or "faults" not in raw:
        raise TaxonomyError("taxonomy must be a mapping with a 'faults' list")
    entries: list[FaultLabel] = []
    seen: set[str] = set()
    for i, item in enumerate(raw["faults"]):
        if not isinstance(item, dict):
            raise TaxonomyError(f"faults[{i}] is not a mapping")
        missing = _REQUIRED_KEYS - item.keys()
        if missing:
            raise TaxonomyError(f"faults[{i}] missing keys: {sorted(missing)}")
        if item["vendor"] not in _VALID_VENDORS:
            raise TaxonomyError(f"faults[{i}] has unknown vendor {item['vendor']!r}")
        if item["id"] in seen:
            raise TaxonomyError(f"duplicate fault id {item['id']!r}")
        seen.add(item["id"])
        entries.append(FaultLabel(**{k: str(item[k]).strip() for k in _REQUIRED_KEYS}))
    return Taxonomy(version=int(raw.get("version", 1)), entries=tuple(entries))


def load(path: str | Path = DEFAULT_PATH) -> Taxonomy:
    with Path(path).open(encoding="utf-8") as fh:
        return _validate(yaml.safe_load(fh))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the udm-bench fault taxonomy.")
    parser.add_argument("--validate", default=str(DEFAULT_PATH), metavar="PATH")
    args = parser.parse_args(argv)
    try:
        tax = load(args.validate)
    except (OSError, TaxonomyError, yaml.YAMLError) as exc:
        print(f"invalid taxonomy: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {len(tax.entries)} faults")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
