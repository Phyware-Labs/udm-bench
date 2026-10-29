# Phase 4 results analysis

Analysis of the 470 scored runs behind the paper draft: 47 missions (23 faulty: 10
single-vendor, 13 multi-vendor; 24 clean) × conditions A, B, G, C at `gpt-5` and
`gpt-5-mini`, plus the D and E ablations at `gpt-5-mini`. Every number below comes
from [`out/tables.md`](out/tables.md), which `python -m analysis.results` generates.
Section numbers in brackets (§n) point to that file.

Companion documents:

- [`multi_vendor_delta.md`](multi_vendor_delta.md): the headline multi-vendor delta
  question.
- [`negative_findings.md`](negative_findings.md): every place the UDM conditions lose
  or a claim does not hold.

Figures (standalone TikZ source + PDF, in `out/`): `fig_per_fault` (detection by
fault, with evidence) and `fig_paired_recall` (paired recall differences).

## Reproduce

```bash
python -m analysis.extract   # one-time: needs runs_live/ and the results_* trace dirs
python -m analysis.results   # from the committed snapshot in analysis/data/ only
```

`analysis/data/` is a compact snapshot of the git-ignored raw inputs: ground truth,
evidence statistics, and per-run scorecard fields plus the submitted fault and vendor.
The cell sources match `paper/gen_tables.py`.

## What this adds to the draft

The draft reports a separate bootstrap interval for each rate. Every condition runs on
the same missions, so the comparisons are **paired**, and two analyses that cost nothing
change how the results read:

1. **Evidence ceiling (§1).** A fault-aware oracle checks whether each injected fault
   moves the telemetry statistic its mechanism should move, beyond anything seen on a
   clean mission. **16 of 23 faulty missions carry a visible signal and 7 do not.** The 7
   are all three `tb3_odometry_drift`, all three `tb3_motor_stall`, and the one
   `tb3_map_mismatch`; one of the motor stalls is on a mission where the TurtleBot3
   recorded no telemetry at all. **No condition at either model scale found any of
   those 7 (0 of 56 runs)**, which corroborates the oracle independently. All 9 PX4
   faults are visible. Only 4 of the 10 single-vendor faulty missions are.
2. **Paired tests (§4).** Exact McNemar tests on discordant missions, Holm-adjusted within
   each (model, metric) family, plus paired-bootstrap CIs and Cohen's h.

## The eight required analyses

### 1. Full matrix (§2)

Every (model × condition × composition) cell, with found/faulty, false alarms, recall,
specificity and balanced accuracy (all with bootstrap CIs), vendor attribution,
hallucinations per run, $/run, $/fault found and tools per run. The `all` rows match
Tables I–II of the draft exactly.

### 2. Multi-vendor delta (§6)

See [`multi_vendor_delta.md`](multi_vendor_delta.md). In short, C's recall is higher on
multi-vendor missions (+0.42 at gpt-5, +0.49 at mini; both CIs exclude 0), which is the
opposite of the "heterogeneity penalty" the epic hypothesised. But the effect comes from
the fault mix, not the composition. On TurtleBot3 faults only, or on evidence-bearing
faults only, no condition's delta and no difference-in-delta excludes 0. **This mission
set cannot test the hypothesis.**

### 3. Cross-vendor attribution (§2, §4)

| | gpt-5 | gpt-5-mini |
|---|---|---|
| A raw bag | 7/13 | 7/13 |
| B SQL | 2/13 | 0/13 |
| G UDM−health_scan | 10/13 | 6/13 |
| C UDM+health_scan | 10/13 | 11/13 |

Paired: C beats B at gpt-5-mini (11–0 discordant, Holm p = 0.005); at gpt-5 the split is
9–1 (raw p = 0.021, Holm 0.107). C vs A is 6–3 and 5–1 (not significant). Vendor
attribution is the clearest cross-vendor signal in the study, and it is strong against
SQL and only directional against raw logs.

### 4. Ablation attribution (§7)

At gpt-5-mini (same v4 batch), removing `correlate_events` (D) or `compliance_audit` (E)
changes almost nothing. C vs D on faults found is 2–2 discordant, and C vs E is 4–2.
Removing `health_scan` (G) is the only ablation that matters: 7–0 on faults found
(Holm p = 0.047), 5–0 on attribution, and in the other direction 0–7 on correct
abstention. F is excluded because it only exists from an earlier harness version.

### 5. Hallucination delta (§8)

Hallucinations per run are near zero on single-vendor missions everywhere and rise on
multi-vendor missions, most for the baselines. At gpt-5: A 0.32, B 0.27, G and C 0.09.
Wrong-vendor attributions on multi-vendor faulty missions are A 6/13 (both scales) and
B 6/13 at gpt-5, against C 2/13 (both scales).

### 6. Cost and efficiency (§2)

Cost per fault found, all missions: at gpt-5, C $1.31, G $2.69, B $3.84, A $4.60. At
gpt-5-mini, C $0.13, G $0.36, A $1.33, and B found nothing. C's cost per fault found is
much lower on multi-vendor missions ($0.70 at gpt-5) than on single-vendor ones ($3.74).
That is the same fault-mix effect as in the delta. C also uses the fewest tool calls of
any detecting condition (about 9.5 per run, against 17–24 for G and B).

### 7. Failure taxonomy (§9)

This is rule-based, from the submitted diagnosis on every missed faulty run, split by
whether the fault left evidence. No trace reading was involved.

- **Raw logs (A) fail by blaming the wrong robot.** On multi-vendor missions with
  evidence, 6 of A's 9 misses at gpt-5 (and 6 of 11 at mini) name the wrong vendor.
- **SQL (B) fails by never answering.** At gpt-5-mini, 10 of its 12 multi-vendor misses
  with evidence submitted no diagnosis, so the agent exhausts its budget exploring
  per-vendor tables. The figure at gpt-5 is 5 of 11.
- **UDM (C) misses few faults that leave evidence**: 4 multi-vendor and 2 single-vendor
  at gpt-5.
- **On faults with no evidence, the UDM conditions at gpt-5 mostly abstain.** G said
  `no_fault` on 6/6 single-vendor misses and C on 4/6. At gpt-5-mini, raw logs never
  abstain and always guess a fault.
- **False alarms (§9) have recognisable sources.** Raw logs at gpt-5 claim
  `tb3_lidar_dropout` on 9 clean missions: healthy scans routinely contain 25–33%
  non-finite (out-of-range) rays, which read as a dropout in plain text. C at gpt-5-mini
  claims `tb3_lidar_noise` on 11 clean missions, which suggests `health_scan`'s lidar
  summary invites over-reading at the smaller scale.

### 8. Negative findings

See [`negative_findings.md`](negative_findings.md).

## Statistical summary: what survives

| Claim | gpt-5 | gpt-5-mini |
|---|---|---|
| C finds more faults than B | 8–0, Holm p = 0.039 ✔ | 11–0, Holm p = 0.005 ✔ |
| C finds more faults than A | 7–1, Holm 0.25; paired recall CI +0.26 [+0.04, +0.48] | 9–1, Holm 0.064; +0.35 [+0.13, +0.57] |
| C finds more than G (health_scan matters) | 5–0, Holm 0.25; +0.22 [+0.09, +0.39] | 7–0, Holm 0.062; +0.30 [+0.13, +0.48] |
| G finds more than A (structure alone helps detection) | 2–1 ✘ | 3–2 ✘ |
| UDM is better calibrated than raw logs | C 16–4 (Holm 0.047), G 13–1 (Holm 0.009) ✔ | G 8–0 (Holm 0.030); C 2–1 ✘ |
| C balanced accuracy above A | +0.38 [+0.19, +0.57] ✔ | +0.19 [+0.07, +0.33] ✔ |
| C balanced accuracy above chance | 0.59 [0.46, 0.72]; **0.69 [0.54, 0.82]** on evidence-bearing faults | ✘ |
| C attributes vendor better than B | 9–1, Holm 0.107 | 11–0, Holm 0.005 ✔ |

✔ = Holm-adjusted p < 0.05 or a paired CI that excludes 0 (as stated). Pooled across
scales, C vs G on faults found is 12–0: every mission where the two disagree goes to C.
The McNemar tests are underpowered at these sample sizes, but the direction is
unambiguous.

## Implications for the paper draft

All four are applied in `paper/main.tex`. The baselines deliberately get no
equivalent triage tool: the paper presents C as the UDM surface with the tooling the
schema makes write-once, and G as the schema alone.

1. **Revise the structural claim.** Contribution 3 says the detection and attribution
   advantages "survive removing our triage tool". On detection they do not: G finds 5
   faults vs A's 4 (gpt-5) and 4 vs 3 (mini). What survives without `health_scan` is
   calibration against raw logs and attribution against SQL. The honest framing is that
   the uniform schema enables a generic triage tool (`health_scan`, which works over
   arbitrary fields across vendors), and that tool supplies most of the detection
   gain.
2. **Add the evidence ceiling.** It turns the "evidence ceiling" limitation bullet into
   a measured result (16/23). It also moves C's gpt-5 balanced accuracy to an interval
   that excludes chance.
3. **Replace "directional, not significant" with the paired results.** C > B on
   detection is significant at both scales. C > A on calibration (gpt-5) and on balanced
   accuracy (both scales) is supported by paired CIs.
4. **Drop or reframe Table IV (composition delta).** It is confounded by fault mix, as
   §6 shows quantitatively.
