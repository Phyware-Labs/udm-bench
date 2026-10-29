# `harness/` — controlled experimental harness

Runs one `(mission, condition, model)` triple to completion and emits a canonical
per-run JSON record.

## Layout

```
harness/
├── run.py                # entrypoint + agent loop
├── backends/
│   ├── base.py           # Backend / ToolCall / Usage / ModelOutput protocol
│   ├── registry.py       # model_id → factory
│   └── mock.py           # deterministic in-process backend (tests, smoke)
├── conditions/
│   ├── base.py           # Condition interface
│   ├── registry.py
│   ├── _diagnosis.py     # shared submit_diagnosis tool + fault label space
│   ├── a_raw_bag.py      # Condition A: decoded bag text
│   ├── b_sql.py          # Condition B: per-topic SQLite tables
│   └── unavailable.py    # placeholders for C–G (not included)
└── prompts/v1, v2/       # versioned A/B system prompts
```

Conditions C–G (the UDM-over-MCP conditions) are not included in this release;
`--condition C` raises an error that says so. Their scored outputs are committed
under `scoring_results_*/`. See the top-level README.

## Usage

```bash
# Smoke-test against the mock backend (no API keys needed)
python -m harness.run \
    --mission runs/<mission_id> \
    --condition A \
    --model mock \
    --results-root results/
```

## Running a hosted model

Hosted-model backends are not included. Implement
`harness.backends.base.Backend` for your provider and register it:

```python
from harness.backends import register_backend

register_backend("my-model", lambda **kw: MyBackend(**kw))
```

`Backend.generate` receives the system prompt, the message history and the tool
specs, and returns a `ModelOutput` with any tool calls and a `Usage` (tokens and
USD cost). See `backends/mock.py` for a complete, minimal implementation.

## Per-run record

`results/<run_id>.jsonl` — one JSON record per `(mission, condition, model)`
tuple, containing:

| Field                       | Purpose                                |
| --------------------------- | -------------------------------------- |
| `run_id`                    | Globally unique id                     |
| `mission_id`, `composition`, `vendors` | Joinable to `runs/<mission_id>/` |
| `condition_code`, `model_id`, `seed`, `prompt_template_version` | Reproducibility |
| `tool_calls[]`              | Full trace (step, tool, args, result)  |
| `final_diagnosis`           | The agent's `submit_diagnosis` payload |
| `final_content`             | Final natural-language reply           |
| `usage`                     | Prompt + completion tokens + USD cost  |
| `latency_ms`                | Wall-clock end-to-end                  |
| `error`                     | Set if the run failed                  |

## Determinism

Given `(mission_id, condition, model, seed, prompt_template_version)` at
temperature 0, re-runs produce identical outputs modulo backend nondeterminism.
The mock backend is fully deterministic and is used in CI.

## Rate-limit handling

Backend calls are wrapped with `tenacity` exponential back-off
(`stop_after_attempt(5)`, `wait_exponential(min=1, max=30)`). Recoverable
`BackendError` instances are retried automatically.
