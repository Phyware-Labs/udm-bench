"""Scenario manifest loader + validator.

Run as a module to validate every manifest in a directory::

    python -m orchestrator.scenario --validate scenarios/
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

VALID_COMPOSITIONS = {"single-vendor", "multi-vendor"}
VALID_VENDORS = {"tb3", "px4"}

# Vendor key in scenario manifests is the short form (tb3/px4); the
# catalogue uses the long form (turtlebot3/px4). Mapping here keeps the
# manifests terse without losing the canonical name elsewhere.
SCENARIO_TO_CATALOGUE_VENDOR = {"tb3": "turtlebot3", "px4": "px4"}

_REQUIRED_KEYS = {
    "id",
    "composition",
    "vendors",
    "world",
    "description",
    "mission_template",
    "fault_mix",
}


@dataclass(frozen=True)
class FaultMix:
    """Fraction of missions in the scenario that get a fault injection."""

    fault_probability: float  # 0.0–1.0
    eligible_fault_ids: tuple[str, ...]
    # Multi-vendor only: probability that the fault hits each vendor.
    # Must sum to 1.0; ignored for single-vendor scenarios.
    vendor_weights: dict[str, float]


@dataclass(frozen=True)
class Scenario:
    id: str
    composition: str  # "single-vendor" | "multi-vendor"
    vendors: tuple[str, ...]  # subset of {"tb3", "px4"}
    world: str
    description: str
    mission_template: dict[str, Any]
    fault_mix: FaultMix
    source_path: Path
    # Optional (low, high) mission-relative seconds in which a fault may be
    # injected. PX4's GPS/EKF warmup means its telemetry only starts flowing
    # ~25-40 s after sim boot, so multi-vendor scenarios push this window later
    # than the default so PX4 faults land in actual telemetry. ``None`` ->
    # ``mission._DEFAULT_INJECTION_WINDOW``.
    injection_window_s: tuple[float, float] | None = None

    @property
    def is_multi_vendor(self) -> bool:
        return self.composition == "multi-vendor"


def load_scenario(path: str | Path) -> Scenario:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _validate(raw, p)


def load_directory(directory: str | Path) -> list[Scenario]:
    """Load and validate every ``*.yaml`` in ``directory``."""
    d = Path(directory)
    if not d.is_dir():
        raise NotADirectoryError(d)
    out: list[Scenario] = []
    for p in sorted(d.glob("*.yaml")):
        out.append(load_scenario(p))
    return out


def _validate(raw: Any, source_path: Path) -> Scenario:
    if not isinstance(raw, dict):
        raise ValueError(f"{source_path}: scenario manifest must be a mapping")
    missing = _REQUIRED_KEYS - raw.keys()
    if missing:
        raise ValueError(f"{source_path}: missing keys: {sorted(missing)}")

    composition = str(raw["composition"])
    if composition not in VALID_COMPOSITIONS:
        raise ValueError(f"{source_path}: composition must be one of {sorted(VALID_COMPOSITIONS)}")

    vendors_raw = raw["vendors"]
    if not isinstance(vendors_raw, list) or not vendors_raw:
        raise ValueError(f"{source_path}: vendors must be a non-empty list")
    vendors = tuple(str(v) for v in vendors_raw)
    bad = set(vendors) - VALID_VENDORS
    if bad:
        raise ValueError(f"{source_path}: unknown vendors: {sorted(bad)}")

    if composition == "single-vendor" and len(vendors) != 1:
        raise ValueError(f"{source_path}: single-vendor scenario must have exactly one vendor")
    if composition == "multi-vendor" and len(vendors) < 2:
        raise ValueError(f"{source_path}: multi-vendor scenario must have ≥2 vendors")

    fault_mix_raw = raw["fault_mix"]
    if not isinstance(fault_mix_raw, dict):
        raise ValueError(f"{source_path}: fault_mix must be a mapping")
    prob = float(fault_mix_raw.get("fault_probability", 0.5))
    if not 0.0 <= prob <= 1.0:
        raise ValueError(f"{source_path}: fault_mix.fault_probability must be in [0, 1]")
    eligible = tuple(str(x) for x in fault_mix_raw.get("eligible_fault_ids", []))
    if not eligible:
        raise ValueError(f"{source_path}: fault_mix.eligible_fault_ids must be non-empty")

    weights_raw: dict[str, float] = {}
    if composition == "multi-vendor":
        w = fault_mix_raw.get("vendor_weights")
        if not isinstance(w, dict):
            raise ValueError(
                f"{source_path}: multi-vendor scenario must define fault_mix.vendor_weights"
            )
        weights_raw = {str(k): float(v) for k, v in w.items()}
        bad_w = set(weights_raw) - VALID_VENDORS
        if bad_w:
            raise ValueError(f"{source_path}: vendor_weights unknown vendors: {sorted(bad_w)}")
        if set(weights_raw) != set(vendors):
            raise ValueError(f"{source_path}: vendor_weights keys must match vendors list")
        total = sum(weights_raw.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"{source_path}: vendor_weights must sum to 1.0 (got {total})")
    fault_mix = FaultMix(
        fault_probability=prob,
        eligible_fault_ids=eligible,
        vendor_weights=weights_raw,
    )

    mission_template = raw["mission_template"]
    if not isinstance(mission_template, dict):
        raise ValueError(f"{source_path}: mission_template must be a mapping")

    injection_window = _parse_injection_window(raw.get("injection_window_s"), source_path)

    return Scenario(
        id=str(raw["id"]),
        composition=composition,
        vendors=vendors,
        world=str(raw["world"]),
        description=str(raw["description"]),
        mission_template=mission_template,
        fault_mix=fault_mix,
        source_path=source_path,
        injection_window_s=injection_window,
    )


def _parse_injection_window(raw: Any, source_path: Path) -> tuple[float, float] | None:
    """Validate an optional ``injection_window_s: [low, high]`` manifest entry."""
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{source_path}: injection_window_s must be a [low, high] pair")
    low, high = float(raw[0]), float(raw[1])
    if low < 0 or high <= low:
        raise ValueError(
            f"{source_path}: injection_window_s must be 0 <= low < high (got {low}, {high})"
        )
    return (low, high)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate udm-bench scenario manifests")
    parser.add_argument(
        "--validate", required=True, help="path to scenarios directory OR a single .yaml"
    )
    args = parser.parse_args(argv)
    target = Path(args.validate)
    try:
        scenarios = load_directory(target) if target.is_dir() else [load_scenario(target)]
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"scenario validation FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"scenario validation OK: {len(scenarios)} manifest(s)")
    for s in scenarios:
        print(
            f"  - {s.id}  composition={s.composition}  vendors={list(s.vendors)}  world={s.world}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
