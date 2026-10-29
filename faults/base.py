"""Abstract base class shared by all platform-specific fault injectors.

A fault injector is a callable that, when triggered at a known mission time,
mutates the running simulation in a deterministic way (modulo RNG seed) and
emits a :class:`InjectionRecord` describing exactly what was done. The record
is forwarded to :class:`faults.ground_truth.GroundTruthLogger` so the scoring
harness has an unambiguous answer key per mission.

Concrete injectors live under ``faults/turtlebot3/`` and ``faults/px4/``.
"""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InjectionRecord:
    """Ground-truth record emitted by an injector.

    The record MUST include ``vendor`` and ``source_id`` so
    multi-vendor missions are scorable for cross-vendor attribution accuracy.
    """

    vendor: str  # "turtlebot3" | "px4"
    fault_id: str  # matches ``faults/catalogue.yaml::faults[].id``
    source_id: str  # e.g. "tb3_0", "px4_0"
    injection_time: float  # ROS time (seconds since mission start)
    mission_id: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FaultInjector(abc.ABC):
    """Abstract base class for a platform-specific fault injector.

    Subclasses set ``vendor`` and ``fault_id`` (matching the catalogue entry)
    and implement :meth:`_apply` to perform the actual simulation-side
    mutation. The framework wraps ``_apply`` so a single :meth:`inject` call
    handles ground-truth recording uniformly.
    """

    #: Vendor key — must match ``faults/catalogue.yaml::faults[].vendor``.
    vendor: str = ""
    #: Fault id — must match ``faults/catalogue.yaml::faults[].id``.
    fault_id: str = ""

    def __init__(
        self, *, source_id: str, mission_id: str, parameters: dict[str, Any] | None = None
    ) -> None:
        if not self.vendor or not self.fault_id:
            raise TypeError(
                f"{type(self).__name__} must set class attributes 'vendor' and 'fault_id'"
            )
        self.source_id = source_id
        self.mission_id = mission_id
        self.parameters: dict[str, Any] = dict(parameters or {})

    @abc.abstractmethod
    def _apply(self) -> None:
        """Mutate the running simulation. Must be deterministic given inputs + seed."""

    def inject(self, *, injection_time: float) -> InjectionRecord:
        """Trigger the fault and produce its ground-truth record.

        ``injection_time`` is the mission-relative ROS time at which the
        fault becomes active. Callers (the orchestrator) are responsible for
        scheduling the call at the desired moment.
        """
        self._apply()
        return InjectionRecord(
            vendor=self.vendor,
            fault_id=self.fault_id,
            source_id=self.source_id,
            injection_time=injection_time,
            mission_id=self.mission_id,
            parameters=dict(self.parameters),
        )
