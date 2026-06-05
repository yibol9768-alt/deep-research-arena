# Handoff: Phase B (corpus expansion) + Phase C (reproducibility)

For whoever picks these up (Codex). The scripts are written and tested; this is
the run-book. Both need the my5090 box with the sandbox up.

## Box access
- `ssh my5090` lands in Windows cmd; real env is WSL Ubuntu. Run bash via:
  `ssh my5090 "wsl -d Ubuntu -- bash -s" <<'EOF' ... EOF` (heredoc avoids
  cmd->wsl->bash quoting hell).
- Repo on box: `/opt/deep_reserch` (a plain copy, NOT git). Sync changed files by
  scp to `C:\Users\liuyibo\` (= WSL `/mnt/c/Users/liuyibo/`) then copy into the repo.
- Sandbox up (unified compose, restart:unless-stopped): `dr_sandbox_shopping`:7770,
  `dr_sandbox_reddit`:9999, `dr_sandbox_wiki`:8090. Keep a `tmux new -d -s keepalive
  "sleep infinity"` running so WSL2 does not idle-shutdown.
- Judge env: `set -a; . /root/.config/dra/judge.env; set +a` (deepseek-v4-flash).
- Wiki note: the compose was patched on-box to mount /opt/corpus/wiki +
  `wikipedia_en_all_nopic.zim` (the .zim the goldens cite). Keep that.

## Phase B: expand forum corpus -> re-crawl -> un-quarantine 25 tasks
Goal: the 25 quarantined non-tech tasks (finance/health/environment/education/
policy/travel...) regain a real forum third so they become scorable. 254
review-vetted threads are ready in `data/corpus_seed/forum_threads.json`.

1. Seed the forum (idempotent; safe to re-run; re-apply after any `reset.sh`):
   `python3 scripts/seed_forum_corpus.py --container dr_sandbox_reddit`
   (verify with `--dry-run` first; it creates the 38 forums + inserts threads,
   Postmill's trigger makes them searchable immediately).
2. Re-crawl goldens for the 25 quarantined task_ids (list = manifest entries with
   verdict=="quarantine" in `data/golden/deep_clean/_manifest.json`):
   for each, `SHOPPING_URL=http://localhost:7770 REDDIT_URL=http://localhost:9999
   WIKI_URL=http://localhost:8090 python3 scripts/build_deep_golden.py
   --task-id <T> --out data/golden/deep/<T>.json` with a `--topic-config` whose
   `reddit_forums` includes the seeded forums for that task (see
   `forum_threads.json` task_forums map) + topic `reddit_keywords`.
3. Re-clean + re-audit: re-run the relevance clean into `data/golden/deep_clean/`,
   then `python3 scripts/build_clean_benchmark_manifest.py` is NOT enough alone
   (it parses the doc) -- update `docs/EVAL_SET_REMEDIATION.md` Section 2 verdicts
   for promoted tasks, then regenerate `_manifest.json`. Target: scorable 75 -> ~95+.
4. Re-score the promoted tasks (cheap, judge-free, from cache):
   `DRA_SANDBOX_CACHE=data/results/sandbox_cache.json python3
   scripts/score_grounding_from_cache.py` (rebuild the cache first for any new
   URLs: `python3 scripts/build_sandbox_cache.py`).

## Phase C: reproducibility
1. Commit the sandbox cache so the benchmark is offline-reproducible:
   `data/results/sandbox_cache.json` is ~410MB (gitignored). Gzip it
   (`gzip -k`) and commit `sandbox_cache.json.gz` (or split), and have
   `src/verifiers/sandbox_http_cache.py` read the .gz if the .json is absent.
2. Broaden the contamination probe from 5 -> all tasks:
   `python3 scripts/contamination_probe.py --num-tasks 100` and refresh
   `docs/CONTAMINATION_REPORT.md` (currently only dr_cross_deep_0001..0005 probed;
   disclose coverage honestly).
3. Regenerate `data/results/benchmark_manifest.json` (content hashes) after B.

## Done criteria
- B: `_manifest.json` scorable >= ~95; promoted tasks have non-empty on-topic
  forum must_cite; seed SQL committed + folded into the sandbox bring-up so it
  survives reset.
- C: cache committed (offline re-score works without live Magento); contamination
  report covers the full set; manifest hashes regenerated.

NOTE: the canonical scoring is now the judge-Elo (everyone scored, no exclusion)
+ a grounding column -- see the leaderboard build. Do not re-introduce the
agent-exclusion gate.
