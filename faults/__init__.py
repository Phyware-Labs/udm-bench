"""Fault contracts shared by the harness and the scoring suite.

Public modules:
  - faults.taxonomy     — the fault label space (``taxonomy.yaml``) every condition
                          classifies into
  - faults.base         — ``InjectionRecord`` and the ``FaultInjector`` interface
  - faults.ground_truth — ``GroundTruthLogger`` / ``load_ground_truth``, the
                          per-mission answer key read by ``scoring``

The fault injectors that produced the benchmark's missions are not part of this
repository; see the README.
"""

from faults.base import FaultInjector, InjectionRecord
from faults.ground_truth import GroundTruthLogger

__all__ = ["FaultInjector", "InjectionRecord", "GroundTruthLogger"]
