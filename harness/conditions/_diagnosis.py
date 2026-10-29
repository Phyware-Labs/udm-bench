"""Shared ``submit_diagnosis`` tool spec with the canonical fault taxonomy.

Every condition must let the agent classify into the *same* answer label space
so scoring is a fair, deterministic exact-match. That label space is the
fault taxonomy (``faults/taxonomy.yaml``) plus a ``no_fault``
sentinel for clean missions. Exposing the candidate labels is the answer space,
not telemetry access, so it does not advantage any condition.
"""

from __future__ import annotations

import functools
from typing import Any

from faults.taxonomy import Taxonomy
from faults.taxonomy import load as load_taxonomy

# Must match scoring.metrics.NO_FAULT_FAULT_ID.
NO_FAULT_FAULT_ID = "no_fault"

_VENDORS = ["turtlebot3", "px4"]


@functools.lru_cache(maxsize=1)
def _catalogue() -> Taxonomy:
    return load_taxonomy()


@functools.lru_cache(maxsize=1)
def fault_id_enum() -> tuple[str, ...]:
    """Canonical fault ids plus the ``no_fault`` sentinel."""
    return (*[e.id for e in _catalogue().entries], NO_FAULT_FAULT_ID)


@functools.lru_cache(maxsize=1)
def _taxonomy_text() -> str:
    lines = [
        "Submit the final fault diagnosis. fault_id MUST be exactly one of the "
        "canonical ids below (use no_fault if the mission was clean):",
    ]
    for e in _catalogue().entries:
        lines.append(f"  - {e.id} [{e.vendor}]: {e.name} — {e.description}")
    lines.append("  - no_fault: no fault occurred during the mission.")
    return "\n".join(lines)


def submit_diagnosis_tool(*, extra_properties: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the ``submit_diagnosis`` tool spec with the fault-id enum.

    ``extra_properties`` lets UDM conditions add their citation fields
    (``cited_event_ids`` / ``cited_standards``) without redefining the schema.
    """
    properties: dict[str, Any] = {
        "fault_id": {
            "type": "string",
            "enum": list(fault_id_enum()),
            "description": "Canonical fault id from the taxonomy, or 'no_fault'.",
        },
        "vendor": {"type": "string", "enum": _VENDORS},
        "source_id": {"type": "string"},
        "claimed_onset_time_s": {
            "type": "number",
            "description": (
                "Estimated fault onset in MISSION-RELATIVE seconds (0.0 = start "
                "of the recording). This is an elapsed offset, NOT a Unix "
                "timestamp or wall-clock time. Typical range 0-300."
            ),
        },
        "explanation": {"type": "string"},
    }
    if extra_properties:
        properties.update(extra_properties)
    return {
        "name": "submit_diagnosis",
        "description": _taxonomy_text(),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": ["fault_id", "vendor", "source_id", "claimed_onset_time_s"],
        },
    }


__all__ = ["NO_FAULT_FAULT_ID", "fault_id_enum", "submit_diagnosis_tool"]
