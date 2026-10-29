"""Scenario manifest loader/validator tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from orchestrator import scenario

SCENARIOS_DIR = Path(__file__).parents[2] / "scenarios"


def test_load_all_repo_scenarios():
    scenarios = scenario.load_directory(SCENARIOS_DIR)
    assert len(scenarios) >= 7  # 3 TB3 + 2 PX4 + 2 multi
    by_id = {s.id: s for s in scenarios}
    assert "single_tb3_warehouse_nav" in by_id
    assert "multi_warehouse_inspection" in by_id

    multi = by_id["multi_warehouse_inspection"]
    assert multi.is_multi_vendor
    assert set(multi.vendors) == {"tb3", "px4"}
    assert abs(sum(multi.fault_mix.vendor_weights.values()) - 1.0) < 1e-6


def test_main_validates_directory(capsys):
    rc = scenario.main(["--validate", str(SCENARIOS_DIR)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "scenario validation OK" in out


def test_main_validates_single_file(capsys):
    rc = scenario.main(["--validate", str(SCENARIOS_DIR / "single_tb3_warehouse_nav.yaml")])
    assert rc == 0


def test_main_fails_on_missing_target(capsys):
    rc = scenario.main(["--validate", str(SCENARIOS_DIR / "does_not_exist.yaml")])
    assert rc == 1


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "s.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_validate_rejects_non_mapping(tmp_path):
    p = _write(tmp_path, "- not a mapping\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        scenario.load_scenario(p)


def test_validate_rejects_missing_keys(tmp_path):
    p = _write(tmp_path, "id: foo\n")
    with pytest.raises(ValueError, match="missing keys"):
        scenario.load_scenario(p)


def test_validate_rejects_bad_composition(tmp_path):
    p = _write(
        tmp_path,
        """
        id: x
        composition: triple-vendor
        vendors: [tb3, px4]
        world: w
        description: d
        mission_template: {}
        fault_mix:
          fault_probability: 0.5
          eligible_fault_ids: [tb3_lidar_dropout]
        """,
    )
    with pytest.raises(ValueError, match="composition must be"):
        scenario.load_scenario(p)


def test_validate_rejects_unknown_vendor(tmp_path):
    p = _write(
        tmp_path,
        """
        id: x
        composition: single-vendor
        vendors: [martian]
        world: w
        description: d
        mission_template: {}
        fault_mix:
          fault_probability: 0.5
          eligible_fault_ids: [tb3_lidar_dropout]
        """,
    )
    with pytest.raises(ValueError, match="unknown vendors"):
        scenario.load_scenario(p)


def test_validate_rejects_single_vendor_with_two(tmp_path):
    p = _write(
        tmp_path,
        """
        id: x
        composition: single-vendor
        vendors: [tb3, px4]
        world: w
        description: d
        mission_template: {}
        fault_mix:
          fault_probability: 0.5
          eligible_fault_ids: [tb3_lidar_dropout]
        """,
    )
    with pytest.raises(ValueError, match="exactly one vendor"):
        scenario.load_scenario(p)


def test_validate_rejects_multi_vendor_without_weights(tmp_path):
    p = _write(
        tmp_path,
        """
        id: x
        composition: multi-vendor
        vendors: [tb3, px4]
        world: w
        description: d
        mission_template: {}
        fault_mix:
          fault_probability: 0.5
          eligible_fault_ids: [tb3_lidar_dropout, px4_gps_dropout]
        """,
    )
    with pytest.raises(ValueError, match="vendor_weights"):
        scenario.load_scenario(p)


def test_validate_rejects_weight_sum_not_one(tmp_path):
    p = _write(
        tmp_path,
        """
        id: x
        composition: multi-vendor
        vendors: [tb3, px4]
        world: w
        description: d
        mission_template: {}
        fault_mix:
          fault_probability: 0.5
          vendor_weights:
            tb3: 0.7
            px4: 0.7
          eligible_fault_ids: [tb3_lidar_dropout]
        """,
    )
    with pytest.raises(ValueError, match="sum to 1"):
        scenario.load_scenario(p)


def test_validate_rejects_bad_probability(tmp_path):
    p = _write(
        tmp_path,
        """
        id: x
        composition: single-vendor
        vendors: [tb3]
        world: w
        description: d
        mission_template: {}
        fault_mix:
          fault_probability: 2.0
          eligible_fault_ids: [tb3_lidar_dropout]
        """,
    )
    with pytest.raises(ValueError, match="fault_probability"):
        scenario.load_scenario(p)


def test_validate_rejects_empty_eligible(tmp_path):
    p = _write(
        tmp_path,
        """
        id: x
        composition: single-vendor
        vendors: [tb3]
        world: w
        description: d
        mission_template: {}
        fault_mix:
          fault_probability: 0.5
          eligible_fault_ids: []
        """,
    )
    with pytest.raises(ValueError, match="eligible_fault_ids must be non-empty"):
        scenario.load_scenario(p)


def test_load_scenario_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        scenario.load_scenario(tmp_path / "does_not_exist.yaml")
