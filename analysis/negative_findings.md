# Negative findings

Every place where a UDM condition loses to a baseline, a claim in the draft is not
supported, or the benchmark itself limits what can be concluded. Numbers are from
[`out/tables.md`](out/tables.md) (§n). These belong in the paper.

## Claims that do not hold

**N1. Without `health_scan`, the UDM surface does not find more faults than raw logs.**
G finds 5/23 vs A's 4/23 at gpt-5 (discordant 2–1) and 4/23 vs 3/23 at mini (3–2).
The draft's claim that the detection advantage "survives removing our triage tool, so
[it is] attributable to structure" is not supported (§4). What survives tool removal is
calibration against raw logs (gpt-5: G 18/24 correct abstentions vs A 6/24, Holm
p = 0.009) and attribution against SQL.

**N2. The detection gain comes from the triage tool.** C vs G on faults found is 5–0
(gpt-5) and 7–0 (mini) discordant, 12–0 pooled. Of the ablations, only removing
`health_scan` changes outcomes; removing `correlate_events` (D) or `compliance_audit`
(E) does not (§7). Defensible framing: the uniform schema is what lets one generic tool
summarise every vendor's fields; that tool, not the schema alone, finds the faults.

**N3. The multi-vendor-delta hypothesis cannot be tested with this mission set**, and the
raw delta points the opposite way (C better on multi-vendor). See
[`multi_vendor_delta.md`](multi_vendor_delta.md).

**N4. C vs raw logs on detection is not significant after correction.** Discordant 7–1
(gpt-5) and 9–1 (mini); Holm p = 0.25 and 0.064. The paired-bootstrap recall CIs
exclude 0 at both scales, so the direction is well supported, but a strict
multiple-comparison reading does not reach significance (§4).

## Where a baseline beats UDM

**N5. At gpt-5-mini, `health_scan` makes the model over-alarm.** C abstains correctly on
2/24 clean missions vs G's 9/24 (0–7 discordant, Holm p = 0.031) and SQL's 20/24.
C's mini specificity is 0.08 and its balanced accuracy, 0.28, is below SQL's 0.42.
The mini C − B balanced difference is −0.14 [−0.28, +0.01] (§2, §4).

**N6. SQL is the best-calibrated condition.** B has the most correct abstentions at both
scales (21/24, 20/24). At gpt-5 it beats C 6–3 on clean missions (not significant), and
its balanced accuracy ties G's. Its calibration comes from rarely answering, but on
clean missions it is still the condition to beat.

**N7. Raw logs win on some subtle TurtleBot3 faults.** The only `tb3_imu_bias` found at
gpt-5 was by A (1/2; C and G 0/2). The only `tb3_costmap_inflation_drift` found at all was
by A at mini (§3). C finds 2/10 single-vendor faults at both scales, no better than
2/10 for A at mini.

**N8. False alarms from `health_scan`'s lidar summary.** C at gpt-5-mini claims
`tb3_lidar_noise` on 11 of 24 clean missions (§9). At gpt-5, 4 of C's 6 false alarms
are the same claim.

## Limits of the benchmark itself

**N9. 7 of 23 faults (30%) leave no recorded evidence** under the oracle (§1). These are
odometry drift ×3, motor stall ×3 and map mismatch ×1. No condition found any of them
(0/56 runs). Their discriminating signals (true pose, wheel commands before relaying,
the world model) are not recorded. Every recall figure in the draft has a ceiling of
16/23 = 0.70.

**N10. Missing telemetry.** 3 of the 22 multi-vendor missions recorded no TurtleBot3
messages at all: 1 clean, plus 2 faulty (a `tb3_motor_stall`, which therefore cannot
be answered, and a `px4_gps_dropout`). A 48th mission
(`single_tb3_warehouse_nav-49c20a7b8acb`, `tb3_lidar_noise`) recorded nothing and is
already excluded from the 47.

**N11. The oracle has thin margins on some faults.** `tb3_imu_bias` clears the clean
maximum by only 1.29× and 1.36×. The local-costmap occupancy used for
`tb3_costmap_inflation_drift` also rises on lidar-noise missions (0.59–0.91), so it is
not specific. "Detectable" is an upper bound from a fault-aware check, not a fair
detector.

**N12. The fault mix is unbalanced across compositions.** No PX4 fault appears on a
single-vendor mission, and only 4 TurtleBot3 faults appear on multi-vendor missions.
This confounds every single-vs-multi comparison (N3).

**N13. Scope.** One model family, one run per mission (decoding variance is not
separated from mission variance), one simulator, and F excluded (only available from an
older harness). D and E are only available at gpt-5-mini.
