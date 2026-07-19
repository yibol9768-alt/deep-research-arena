# DRA v3.3 single-task vertical slice

Task: `dra_v3_dev_audio_0002`

This directory is a development-only, replayable example of the sandbox-native
scoring design. It contains the frozen source graph, a compiled light World
Index, a Task World Model, a 5-facet / 8-unit / 25-check Research Test Suite,
controlled adversarial fixtures, and one projected real run.

Run from the repository root:

```bash
PYTHONPATH=. python3 scripts/run_audio_0002_sandbox_native_slice.py
PYTHONPATH=. python3 -m pytest -q tests/test_sandbox_native_audio_0002.py
```

Replay any sealed fixture directly:

```bash
PYTHONPATH=. python3 scripts/score_sandbox_native_grc.py \
  --suite data/pilot_v33/dra_v3_dev_audio_0002/research-test-suite.json \
  --world data/pilot_v33/dra_v3_dev_audio_0002/world-index.json \
  --report data/pilot_v33/dra_v3_dev_audio_0002/controlled/reports/oracle_alternative.md \
  --ledger data/pilot_v33/dra_v3_dev_audio_0002/controlled/ledgers/oracle_alternative.json \
  --judgment data/pilot_v33/dra_v3_dev_audio_0002/controlled/judgments/oracle_alternative.json \
  --pretty
```

The controlled judgments are construction-known test labels. The real-run
judgment is manual and has `formal_eligible=false`; it demonstrates replay, not
leaderboard validity.
