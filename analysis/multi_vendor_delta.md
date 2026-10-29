# The multi-vendor delta

**Hypothesis:** UDM-MCP loses less accuracy than the baselines when
moving from single-vendor to multi-vendor fleets, i.e. its multi − single delta is
smaller.

**Verdict:** this mission set cannot test the hypothesis. The raw delta points the
*other* way (C is better on multi-vendor missions), but it is explained by
differences in fault mix and evidence between the two mission sets, not by
composition. Numbers from [`out/tables.md`](out/tables.md) §6.

## Raw delta (all faults)

Recall on multi-vendor minus single-vendor faulty missions (10 single, 13 multi):

| condition | gpt-5 | gpt-5-mini |
|---|---|---|
| A raw bag | +0.13 [−0.15, +0.42] | −0.12 [−0.42, +0.15] |
| B SQL | −0.02 [−0.30, +0.23] | +0.00 |
| G UDM−health_scan | +0.21 [−0.12, +0.54] | +0.31 [+0.08, +0.54] |
| C UDM+health_scan | **+0.42 [+0.04, +0.77]**, h = 0.88 | **+0.49 [+0.12, +0.82]**, h = 1.04 |

Difference in delta, with missions resampled in pairs within each composition so both
conditions see the same draw: C − B = +0.44 [+0.11, +0.77] at gpt-5. C − A = +0.62
[+0.23, +0.99] and C − B = +0.49 [+0.12, +0.82] at gpt-5-mini. Read at face value, UDM
gains on heterogeneous fleets while the baselines do not.

## Why that reading does not hold

The two mission sets do not contain the same faults (§1, §3):

| | single-vendor faulty | multi-vendor faulty |
|---|---|---|
| PX4 faults | 0 | 9 (5 GPS dropout, 4 IMU saturation) |
| TurtleBot3 faults | 10 | 4 |
| Faults with visible evidence | **4 / 10** | **12 / 13** |

Single-vendor missions hold 6 of the 7 faults that leave no trace in the recording (all
odometry drift, two motor stalls, the map mismatch). No condition finds any of them. The
multi-vendor set is dominated by PX4 faults with strong signals: GPS gaps 13× longer
than any clean mission, and around 300 NaN attitude samples. `health_scan` surfaces
both directly, and C finds 7 of those 9 at both scales.

Control for this and the effect goes away:

| fault set | C delta, gpt-5 | C delta, mini | any difference-in-delta excluding 0? |
|---|---|---|---|
| all faults | +0.42* | +0.49* | yes (C−B gpt-5; C−A, C−B mini) |
| TurtleBot3 faults only (10 vs 4) | +0.05 [−0.40, +0.55] | +0.30 [−0.25, +0.80] | no |
| evidence-bearing only (4 vs 12) | +0.17 [−0.42, +0.75] | +0.25 [−0.33, +0.83] | no |

With only 4 TurtleBot3 faults or 4 evidence-bearing faults on one side, these intervals
are too wide to say anything either way.

## What the data does say about heterogeneity

The clean cross-vendor signal is **vendor attribution** on multi-vendor faulty missions
(paired, same missions). C names the right robot on 10/13 (gpt-5) and 11/13 (mini).
Raw logs manage 7/13 at both scales and SQL 2/13 and 0/13. Most of A's multi-vendor
misses are wrong-vendor answers, and most of B's are no answer at all
([`results.md`](results.md), failure taxonomy). That supports the vendor-neutral
argument without relying on the confounded delta.

## What would test the hypothesis

A matched design, where every fault type appears on both single- and multi-vendor
missions in equal numbers and only faults with a recordable signal are used. That is
experiment 4 in the follow-up plan, and it needs new simulation runs.
