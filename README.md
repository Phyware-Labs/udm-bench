# UDM-Bench

A benchmark of whether an open, vendor-neutral unified data model (UDM), served to
an LLM agent over the [Model Context Protocol](https://modelcontextprotocol.io),
helps the agent diagnose robot faults better than raw logs or per-vendor SQL.

This repository is the artifact for the paper *Does a Vendor-Neutral Data Model
Help LLMs Diagnose Robot Faults? A Paired Benchmark of Unified Telemetry over the
Model Context Protocol* ([`paper/`](paper/)). The data model under test is
[PhyUDM](https://github.com/Phyware-Labs/PhyUDM).

## The benchmark in one paragraph

An agent is given one finished, simulated mission (a TurtleBot3, or a TurtleBot3
and a PX4 drone in one world) and must decide whether a fault occurred, name it
from a fixed taxonomy, and on mixed-vendor missions say which robot failed. Every
condition sees the same recording and answers through the same tool; only the
interface to the telemetry changes. 47 missions (23 faulty, 24 clean), two model
scales (`gpt-5`, `gpt-5-mini`), and these conditions:

| Code | Interface | In this repo |
| --- | --- | --- |
| A | Raw bag, decoded to paginated text | Yes |
| B | Generic SQL: one SQLite table per vendor topic, native column names | Yes |
| C | UDM over MCP, full tool surface including the `health_scan` triage tool | Scored results only |
| D, E | C without cross-source correlation / without the compliance audit | Scored results only |
| G | C without `health_scan` | Scored results only |

## What is included

| Path | What it is |
| --- | --- |
| [`paper/`](paper/) | The paper source. `paper/build.sh` regenerates every table from the committed data and builds the PDF. |
| [`scoring_results_*/`](scoring_results_phase4/) | The scored record of every run in the paper (scorecards, leaderboard, detection breakdown). |
| [`analysis/`](analysis/) | Paired tests, the evidence-ceiling oracle and the per-fault breakdown, with a compact data snapshot in `analysis/data/` and written results in `analysis/*.md`. |
| [`scoring/`](scoring/) | The full scoring suite: metrics, the hallucination detector, composition deltas, bootstrap CIs, and the hand-labelled hallucination corpus that validates the detector. |
| [`harness/`](harness/) | The agent loop, the backend interface with a deterministic mock backend, and Conditions A and B with their prompts. |
| [`baselines/`](baselines/) | Converters from rosbag2 to the Condition A text and Condition B SQLite inputs. |
| [`faults/`](faults/) | The fault taxonomy the agent classifies into, and the ground-truth record format scoring reads. |
| [`scenarios/`](scenarios/), [`orchestrator/scenario.py`](orchestrator/scenario.py) | Scenario manifests and their validator. |
| [`sim/`](sim/) | The Docker Compose ROS 2 / Gazebo / PX4 SITL environment the missions were recorded in. |
| [`leaderboard/`](leaderboard/) | Static HTML leaderboard renderer. |

## What is not included

Some components are not part of this release:

- **The UDM-over-MCP conditions (C–G)** and their prompts. `--condition C`
  raises an error that says so.
- **The fault injectors** and the mission planner and runner that recorded the
  faulted missions. The public sim records clean missions.
- **The UDM ingest pipeline** that normalised the recordings into UDM events.
- **Hosted-model backends.** The harness ships a mock backend and a small
  `Backend` interface; see [`harness/README.md`](harness/README.md).
- **Raw run traces and mission recordings** (full tool-call transcripts and
  rosbags).

None of these is needed to check the paper. Every number in it is computed by
the code in this repository from the committed scored results, so you can
recompute every table, re-run every statistical test and inspect every run's
outcome. What you cannot do with this repository alone is re-run conditions C–G
or record new faulted missions.

## Reproduce the paper

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,bag]"

python paper/gen_tables.py       # regenerate paper/tables/*.tex from scoring_results_*
python -m analysis.results       # regenerate analysis/out/ (paired tests, evidence ceiling)
paper/build.sh                   # tables + PDF (needs tectonic, latexmk or pdflatex)
```

## Run the baselines

```bash
pytest -m smoke --no-cov         # synthetic missions → A and B (mock model) → scoring → leaderboard
```

To run a real model, implement the `Backend` interface for your provider
([`harness/README.md`](harness/README.md)), record or supply a mission, and:

```bash
python -m baselines.prepare runs/<mission_id>
python -m harness.run --mission runs/<mission_id> --condition A --model <your-model>
python -m scoring.score --runs runs/ --results results/ --out scoring_out/
```

## Repository layout

```
udm-bench/
├── paper/              Paper source, table generator, build script
├── analysis/           Paired statistics, evidence ceiling, written results
├── scoring/            Metrics + hallucination detector + composition deltas
├── scoring_results_*/  Scored results of every run in the paper
├── harness/            Agent loop, backend interface, Conditions A and B
├── baselines/          rosbag2 → text (A) and → SQLite (B) converters
├── faults/             Fault taxonomy + ground-truth record format
├── scenarios/          Scenario manifests
├── orchestrator/       Scenario manifest loader/validator
├── sim/                Docker Compose simulation environment
├── leaderboard/        Static-site renderer
└── tests/
```

## Cloud spend

The 470 scored runs in the paper cost about **$65** at list price ($52.65 for
`gpt-5`, $12.24 for `gpt-5-mini`), excluding development and pilot runs. All of
it was covered by cloud credits, so the out-of-pocket cost was $0.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
and [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
