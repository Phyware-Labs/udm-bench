# Abstract (150 words)

Mixed robot fleets expose telemetry in vendor-specific formats, so every diagnostic
tool must be rebuilt per vendor. We test whether an open, vendor-neutral unified data
model (UDM), served to an LLM agent over the Model Context Protocol, improves fault
diagnosis over raw logs and per-vendor SQL. UDM-Bench fixes task, data and answer
channel across 47 simulated single- and multi-vendor missions and varies only the
telemetry interface. A fault-aware oracle shows 7 of 23 faults leave no trace; no
condition finds them. Paired across two model scales, the full UDM surface finds more
faults than SQL (Holm p = 0.039, 0.005) and raw logs (paired recall CIs exclude
zero), and names the faulty vendor on 10–11 of 13 mixed missions. Ablation shows the
schema alone improves calibration, while detection comes from one generic triage tool
written once against the schema and run unchanged on every vendor: portable tooling
is the data model's practical value.
