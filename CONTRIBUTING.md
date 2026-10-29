# Contributing to UDM-Bench

Thanks for your interest. UDM-Bench is the artifact for a paper, so its first job
is to keep the published numbers reproducible. Contributions that are most useful:

- Running the baselines (Conditions A and B) with other model families and
  reporting the results
- Bug reports against the scoring suite, the hallucination detector or the
  analysis, especially anything that changes a number in the paper
- New scenario manifests and fault taxonomy entries, with an explanation of the
  signal the fault should leave in the recording
- Documentation and reproducibility fixes

## How to contribute

1. **Open an issue first** for anything non-trivial, in particular any change to
   a metric definition or the scorecard format. Those are a compatibility
   surface: a metric that changes meaning breaks comparisons with published
   results.
2. **Small fixes** (typos, broken links, clarifications) are welcome as direct
   pull requests against `main`.

## Pull request checklist

- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] `pytest` passes, with coverage at or above the configured gate.
- [ ] If the change touches `scoring/`, `analysis/` or `paper/gen_tables.py`,
      `python paper/gen_tables.py` still reproduces the committed `paper/tables/`
      (or the PR explains why a number changed).

## Developer Certificate of Origin

By contributing you agree to the
[Developer Certificate of Origin](https://developercertificate.org/). Sign your
commits with `git commit -s`.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).

## License

Contributions are licensed under the [Apache License 2.0](LICENSE).
