"""Automated hallucination detector.

The detector must achieve precision ≥ 0.85 on
a hand-labelled set of ≥30 known-hallucinated agent outputs. The
hand-labelled corpus lives under ``tests/scoring/data/hallucination_corpus.jsonl``
and is exercised by ``tests/scoring/test_hallucination_corpus.py``.

Detected hallucination types:

1. ``event_id``  — cited an event id that does not appear in the run's
   tool-call results.
2. ``field_path`` — cited a JSON field path that is not present in the
   declared UDM schema.
3. ``standard``  — cited a standard that was never queried via
   compliance_audit.
4. ``vendor_misattribution`` — multi-vendor only — attributed the fault
   to the wrong vendor.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from faults.base import InjectionRecord

# Heuristic: event ids are typically uuid-like or sha-prefixed identifiers.
# Matches the UDM event-id forms seen in tool results.
_EVENT_ID_PATTERN = re.compile(r"\bevt_[a-f0-9]{8,}\b|\bevent[_-]?id[\":= ]+[a-zA-Z0-9_-]{8,}\b")

# UDM event ids in the real store are bare UUIDs (e.g. ``06a4acf9-482b-7f6d-...``).
# The store returns them inside JSON (``"event_id": "<uuid>"``) but also inside
# compact-row / truncated-preview *strings* the JSON harvester can't descend
# into, so we additionally scan raw result text for this shape to ground
# citations that would otherwise look invented.
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# Real UDM envelope roots (schemas/v0.0.3). A dotted citation whose first
# segment is one of these is treated as a real field path; the deep leaf is not
# validated here (that would need the full JSON Schema).
_UDM_FIELD_ROOTS: set[str] = {
    "event_id",
    "event_type",
    "source_id",
    "source_type",
    "captured_at",
    "received_at",
    "session_id",
    "sequence_num",
    "identity",
    "location",
    "motion",
    "power",
    "safety",
    "perception",
    "simulation",
    "provenance",
    "extensions",
    "payload",
}

# Pattern matching field-path style citations, e.g. ``extensions.lidar.valid_fraction``.
# Segments must be >= 2 chars so prose like ``e.g`` / ``i.e`` is not mis-flagged.
_FIELD_PATH_PATTERN = re.compile(r"\b([a-z_]{2,}(?:\.[a-z_]{2,})+)\b")

# Compliance standards the agent might cite.
_KNOWN_STANDARDS = {"ISO 21448", "ISO 26262", "IEC 61508", "DO-178C"}


@dataclass(frozen=True)
class HallucinationReport:
    event_ids: tuple[str, ...] = field(default_factory=tuple)
    field_paths: tuple[str, ...] = field(default_factory=tuple)
    standards: tuple[str, ...] = field(default_factory=tuple)
    vendor_misattribution: bool = False

    @property
    def total(self) -> int:
        return (
            len(self.event_ids)
            + len(self.field_paths)
            + len(self.standards)
            + (1 if self.vendor_misattribution else 0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "total": self.total}


def detect_hallucinations(
    *,
    run_record: dict[str, Any],
    ground_truth: list[InjectionRecord],
) -> HallucinationReport:
    diagnosis: dict[str, Any] = dict(run_record.get("final_diagnosis") or {})
    final_text = str(run_record.get("final_content", ""))
    explanation = str(diagnosis.get("explanation", ""))
    blob = f"{final_text}\n{explanation}"

    # Build sets of legitimate event ids / standards from the tool-call trace.
    real_event_ids, queried_standards = _gather_evidence(run_record.get("tool_calls", []))

    # Event-id hallucinations
    cited_ids = set(diagnosis.get("cited_event_ids") or [])
    for m in _EVENT_ID_PATTERN.finditer(blob):
        cited_ids.add(_extract_event_id(m.group(0)))
    cited_ids.discard("")
    bogus_ids = tuple(sorted(cid for cid in cited_ids if cid not in real_event_ids))
    # Field-path hallucinations
    cited_fields = {m.group(1) for m in _FIELD_PATH_PATTERN.finditer(blob)}
    bogus_fields = tuple(sorted(p for p in cited_fields if not _is_allowed_field(p)))

    # Standard-citation hallucinations
    cited_standards: set[str] = set(diagnosis.get("cited_standards") or [])
    for s in _KNOWN_STANDARDS:
        if s in blob:
            cited_standards.add(s)
    bogus_standards = tuple(sorted(s for s in cited_standards if s not in queried_standards))

    # Vendor misattribution (multi-vendor only — caller filters via ground_truth)
    vendor_mis = False
    if ground_truth and run_record.get("composition") == "multi-vendor":
        truth_vendors = {gt.vendor for gt in ground_truth}
        claimed_vendor = str(diagnosis.get("vendor", ""))
        if claimed_vendor and claimed_vendor not in truth_vendors:
            vendor_mis = True

    return HallucinationReport(
        event_ids=bogus_ids,
        field_paths=bogus_fields,
        standards=bogus_standards,
        vendor_misattribution=vendor_mis,
    )


def _gather_evidence(tool_calls: Iterable[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """Walk the tool-call trace, returning (legitimate event ids, queried standards)."""
    event_ids: set[str] = set()
    standards: set[str] = set()
    for tc in tool_calls:
        # Tool result payloads — content is a JSON-encoded string.
        result = tc.get("tool_result", {})
        content = result.get("content")
        if isinstance(content, str):
            # Pull event ids from the result payload — handles both
            # `"event_id": "evt_..."` and uuid-style ids in lists.
            for m in _EVENT_ID_PATTERN.finditer(content):
                event_ids.add(_extract_event_id(m.group(0)))
            # Bare-UUID ids appear inside compact rows and truncated previews
            # that the JSON walk below cannot descend into.
            for m in _UUID_PATTERN.finditer(content):
                event_ids.add(m.group(0))
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                _harvest_event_ids(parsed, event_ids)
        # Tool calls that queried compliance count as "queried standards".
        call = tc.get("tool_call", {})
        if call.get("name") == "compliance_audit":
            std = (call.get("arguments") or {}).get("standard")
            if std:
                standards.add(str(std))
    event_ids.discard("")
    return event_ids, standards


def _harvest_event_ids(obj: Any, sink: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "event_id" and isinstance(v, str):
                sink.add(v)
            else:
                _harvest_event_ids(v, sink)
    elif isinstance(obj, list):
        for x in obj:
            _harvest_event_ids(x, sink)


def _extract_event_id(blob: str) -> str:
    # ``blob`` matches one of:
    #   - ``evt_abc12345...``                          (return as-is)
    #   - ``"event_id": "abc-12345"`` (etc.)           (extract the value)
    if blob.startswith("evt_"):
        return blob
    m = re.search(r'event[_-]?id[":= ]+([a-zA-Z0-9_-]+)', blob)
    return m.group(1) if m else ""


def _is_allowed_field(path: str) -> bool:
    if path in _UDM_FIELD_ROOTS:
        return True
    # A dotted citation is real if its first segment is a UDM envelope root
    # (e.g. ``extensions.lidar.valid_fraction`` -> ``extensions``). The deep
    # leaf is not validated without the full JSON Schema.
    top = path.split(".", 1)[0]
    return top in _UDM_FIELD_ROOTS
