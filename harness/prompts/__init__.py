"""Versioned prompt templates for the harness conditions.

System prompts are stored as plain-text files under ``harness/prompts/<version>/``
so prompt wording is decoupled from code and every run records exactly which
template version produced it (``RunRecord.prompt_template_version``). Bumping a
prompt = adding a new ``vN`` directory; old runs remain reproducible.
"""

from __future__ import annotations

from importlib.resources import files

CURRENT_VERSION = "v2"


def load_system_prompt(code: str, *, version: str = CURRENT_VERSION) -> str:
    """Return the system prompt for a condition ``code`` (A–F).

    Raises :class:`FileNotFoundError` if the ``(version, code)`` pair has no
    template, which surfaces a missing-prompt regression loudly rather than
    silently sending an empty system prompt to a paid model.
    """
    resource = files(__package__).joinpath(version, f"{code}_system.txt")
    if not resource.is_file():
        raise FileNotFoundError(f"no system prompt for condition {code!r} at version {version!r}")
    return resource.read_text(encoding="utf-8").strip()


__all__ = ["CURRENT_VERSION", "load_system_prompt"]
