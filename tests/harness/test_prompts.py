"""Tests for versioned prompt loading."""

from __future__ import annotations

import pytest

from harness.conditions import get_condition
from harness.prompts import CURRENT_VERSION, load_system_prompt


@pytest.mark.parametrize("code", ["A", "B"])
def test_every_condition_has_versioned_prompt(code):
    prompt = load_system_prompt(code)
    assert prompt
    # The condition surfaces exactly the versioned text.
    assert get_condition(code).system_prompt() == prompt


def test_current_version_is_v2():
    assert CURRENT_VERSION == "v2"


def test_v1_prompts_still_load_for_reproducibility():
    # Old runs recorded prompt_template_version=v1; those templates must remain.
    for code in ["A", "B"]:
        assert load_system_prompt(code, version="v1")


def test_v2_ab_prompts_match_v1_verbatim():
    # A/B are unchanged across the bump so their prior results stay comparable.
    for code in ["A", "B"]:
        assert load_system_prompt(code, version="v2") == load_system_prompt(code, version="v1")


def test_missing_prompt_raises():
    with pytest.raises(FileNotFoundError):
        load_system_prompt("Z")


def test_missing_version_raises():
    with pytest.raises(FileNotFoundError):
        load_system_prompt("A", version="v999")
