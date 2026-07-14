#!/usr/bin/env python3
"""Pin the exact code + environment a scored run executed under, so a leaderboard
number can always be traced back to the bytes that produced it.

WHY THIS EXISTS

The 13-task subset shipped a results TSV with 16 columns and not one code
version field. `grep -r` over the whole run product finds zero 40-char shas.
That made two real accidents unresolvable after the fact:

  - gpt-researcher's retriever-fix commit 8377cd8d landed 2026-07-07 04:25 PDT,
    16 minutes before the subset started at 04:41 PDT. Whether the box actually
    had that commit checked out when it ran is now unknowable: nothing recorded
    the commit.
  - the claude-code lane once labelled qwen3-8b outputs as deepseek. Nothing
    recorded which endpoint each lane really talked to.

A manifest fixes both by recording, at run time on the executing host, the git
commit, whether the tree was dirty, the content hash of every file that can
change a score, an allow-listed env snapshot, the corpus fingerprints, and a
per-lane model-identity probe. `verify()` lets the scorer refuse to score a
report set whose manifest is missing, dishonest, or generated somewhere else.

HONESTY

A manifest is only meaningful if it was generated on the SAME host that ran the
agents. Generate it on the workstation, run the agents on the box, and the
commit/env/hashes describe the wrong machine. The manifest therefore records its
own generation hostname, and `verify()` refuses (a listed violation) when that
does not match the host now doing the scoring. There is no way to make a
workstation-generated manifest look box-native; that is the point.

    python3 scripts/run_manifest.py --out manifest.json
    python3 scripts/run_manifest.py --verify manifest.json --reports-dir data/results/deep_v3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files whose bytes can move either the report or its score.  A hand-maintained
# list repeatedly missed transitive imports (URL identity, citation extraction,
# report-stub classification, sampling policy).  Hash the complete local code
# closure instead: every Python file below the three executable source roots,
# plus the protocol configuration.  This is deliberately a conservative
# superset of the import graph; changing unrelated local runtime code may force
# a rerun, while omitting a real dependency can silently compare different
# systems.
_KEY_FILE_PATHS = [
    "src/eval/decidable_scorer.py",
    "scripts/run_deep_task.py",
    "integrations/search_shim/app.py",
    "integrations/search_shim/evidence.py",
    "integrations/ds_proxy/app.py",
    "integrations/llm_gateway/app.py",
    "config/lane_protocol.yaml",
]
_KEY_FILE_GLOBS = ["src/**/*.py", "scripts/**/*.py", "integrations/**/*.py"]

# Corpus fingerprints. url_registry.json decides which cited URLs count as real
# (provenance / fabrication), and the answer_keys are the golden the scorer
# grades reach + completeness against. If either drifts between run and score,
# the number is being computed against a different ground truth than the agent
# faced.
_URL_REGISTRY = "data/golden/url_registry.json"
_WIKI_BLOOM = "data/golden/wiki_bloom.bin"
_ANSWER_KEYS_DIR = "data/golden/answer_keys"
_TASKS_DIR = "data/tasks/deep_research/cross_site_deep"

_SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")


# --- env allow-list --------------------------------------------------------
#
# The four budget suffixes MUST equal check_parity.ENV_BUDGET_SUFFIXES. The
# parity checker REQUIRES each such knob to be DECLARED in lane_protocol.yaml;
# the manifest must RECORD the VALUE each run used, or the two instruments
# disagree: parity says "this is a scored budget you must disclose" while the
# manifest cannot show which value a given board actually ran under (an operator
# overriding SMOLAGENTS_SEARCH_MAX_RESULTS=12 would be undetectable after the
# fact). The equality is enforced by test_budget_suffixes_match_check_parity so
# the two lists cannot drift.
_BUDGET_SUFFIXES = ("MAX_STEPS", "SEARCH_MAX_RESULTS", "TOKEN_LIMIT", "CONTEXT_LIMIT")

# The LLM transports (ds_proxy, llm_gateway) read every behaviour knob under one
# of these prefixes, NOT under DS_PROXY_. The old `DS_PROXY_` rule matched only
# the endpoint URL and none of the knobs that change what the model produces:
# thinking on/off (OPENAI_PROXY_THINKING_DISABLED), the answer-token floor
# (OPENAI_PROXY_MIN_MAX_TOKENS), the thinking strip (OPENAI_PROXY_STRIP_THINKING),
# the per-backbone thinking-off list (OPENAI_PROXY_THINKING_OFF_PREFIXES), the
# model rewrite (OPENAI_PROXY_REWRITE_MODEL), and the whole llm_gateway config
# (LLM_GATEWAY_CONFIG). A run with thinking left ON, or a 131072-token floor,
# produces different reports and used to move no manifest byte (Y3 finding).
_TRANSPORT_ENV_PREFIXES = ("OPENAI_PROXY_", "DSPROXY_", "DS_PROXY_",
                           "LLMGW_", "LLM_GATEWAY_")


def _is_secret(name: str) -> bool:
    """A credential must never enter the manifest, whatever else it matches.

    Catches OPENAI_PROXY_KEY / OPENAI_PROXY_EMB_KEY / OPENAI_API_KEY /
    DASHSCOPE_API_KEY etc. `TOKEN_LIMIT` is a budget (ends `_LIMIT`), not a token,
    so it is deliberately not caught by the TOKEN check."""
    return (name.endswith("_KEY") or "API_KEY" in name
            or "SECRET" in name or "PASSWORD" in name)


def _env_var_in_scope(name: str) -> bool:
    """Which process env vars are recorded. Kept to knobs that change a run's
    behaviour; secrets (API keys) are deliberately never in scope."""
    # Credentials first: a secret is out of scope no matter what else it matches
    # (OPENAI_PROXY_KEY starts with a transport prefix but is a key).
    if _is_secret(name):
        return False
    if name.endswith("_TIMEOUT_S"):
        return True
    if name == "MAX_STEPS":  # the bare knob the harness also reads
        return True
    # Every guarded per-lane budget: step cap, results-per-search, token/context
    # window. check_parity requires these declared; the manifest records them.
    if any(name.endswith("_" + s) for s in _BUDGET_SUFFIXES):
        return True
    if name.startswith("SHIM_"):
        return True
    if any(name.startswith(p) for p in _TRANSPORT_ENV_PREFIXES):
        return True
    if name.startswith("DRA_"):
        return True
    # Lane switches that silently change WHICH writer/route/text-budget ran and
    # so change the report without touching the prompt:
    #   *_INTENT_MASK        url-laundering round trip (was hardcoded LDR-only,
    #                        while LCDR_INTENT_MASK and DEEPAGENTS_INTENT_MASK
    #                        did the same thing unrecorded)
    #   *_FORCE_FALLBACK     diverts a lane to the degraded evidence writer, so a
    #                        run is scored as the framework while it was the stub
    #   EVIDENCE_FALLBACK_*  the fallback writer's own knobs (SKIP_LLM etc.)
    #   *_SNIPPET_CHARS      per-result text budget; moves completeness like
    #                        results-per-search does
    #   *_MIN_REPORT_CHARS / *_SHORT_RETRY_MIN_CHARS  length thresholds that gate
    #                        a stub or a re-invoke, i.e. change what is scored
    if (name.endswith("_INTENT_MASK") or name.endswith("_FORCE_FALLBACK")
            or name.startswith("EVIDENCE_FALLBACK_")
            or name.endswith("_SNIPPET_CHARS")
            or name.endswith("_MIN_REPORT_CHARS")
            or name.endswith("_SHORT_RETRY_MIN_CHARS")):
        return True
    if name in {"FLOWSEARCHER_MEMORY"}:
        return True
    return False


def _env_snapshot(env: dict[str, str]) -> dict[str, str]:
    return {k: env[k] for k in sorted(env) if _env_var_in_scope(k)}


# --- hashing helpers -------------------------------------------------------
def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None


def _valid_sha256(value) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _formula_version() -> str:
    """The scoring identity, imported rather than re-declared.

    An earlier draft scraped it out of `decidable_scorer.py` with a regex over
    constant names that do not exist there (the real ones are `GAMMA_DEFAULT`,
    `QUALITY_WEIGHTS`, `POF_THRESHOLD_DEFAULT`), so it silently recorded nothing.
    A manifest that quietly omits the formula is worse than no manifest: it looks
    like provenance.
    """
    try:
        from scripts.build_truth_board import FORMULA_VERSION
        return FORMULA_VERSION
    except Exception as exc:  # noqa: BLE001
        return f"UNRESOLVED: {type(exc).__name__}"


def _framework_hashes(root: Path) -> dict:
    """sha256 over each framework's installed source tree, plus its interpreter.

    Every lane runs the framework from its own venv. Hashing only our adapter
    answers "which glue did we use", never "which framework did we test". Each
    entry is a digest over the sorted (relpath, filedigest) pairs of the tree, so
    a single upgraded file changes it.
    """
    out: dict[str, dict] = {}
    for venv in sorted(root.glob(".venv-*")):
        if not venv.is_dir():
            continue
        site = next(iter(sorted(venv.glob("lib/python*/site-packages"))), None)
        entry: dict = {
            "venv": venv.name,
            "python": None,
            "python_sha256": None,
            "site_packages_sha256": None,
            "n_files": 0,
        }
        py = venv / "bin" / "python"
        if py.exists():
            entry["python"] = str(py)
            entry["python_sha256"] = _sha256_file(py)
        if site and site.is_dir():
            h = hashlib.sha256()
            n = 0
            for f in sorted(site.rglob("*.py")):
                try:
                    h.update(str(f.relative_to(site)).encode())
                    h.update(hashlib.sha256(f.read_bytes()).digest())
                    n += 1
                except OSError:
                    continue
            entry["site_packages_sha256"] = h.hexdigest()
            entry["n_files"] = n
        out[venv.name] = entry
    return out


def _key_file_hashes(root: Path) -> dict[str, str | None]:
    """{relative_path: sha256 or None-if-missing}. A missing key file is kept as
    an explicit null rather than dropped, so verify() can see it was absent."""
    rels: list[str] = list(_KEY_FILE_PATHS)
    for pattern in _KEY_FILE_GLOBS:
        for p in sorted(root.glob(pattern)):
            if not p.is_file():
                continue
            rels.append(str(p.relative_to(root)))
    out: dict[str, str | None] = {}
    for rel in sorted(set(rels)):
        out[rel] = _sha256_file(root / rel)
    return out


def _dir_content_hash(directory: Path, suffix: str = ".json") -> str | None:
    """sha256 over the SORTED list of (name, raw_bytes) of every matching file.
    Sorting by name makes the digest independent of filesystem walk order;
    hashing raw bytes catches any change a re-pretty-print would hide."""
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*" + suffix), key=lambda q: q.name)
    if not files:
        return None
    h = hashlib.sha256()
    for p in files:
        h.update(p.name.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def task_set_hash(root: Path = ROOT) -> str | None:
    """Fingerprint both the scoring goldens and the task bytes shown to agents.

    Hashing answer keys alone pins the scorer but not the measured task.  A
    prompt/intent edit can change every report while the old manifest still
    verifies.  Both directories are required and path-prefixed in one digest so
    moving a byte on either side changes the run identity.
    """
    paths: list[tuple[str, Path]] = []
    for rel_dir in (_ANSWER_KEYS_DIR, _TASKS_DIR):
        directory = root / rel_dir
        if not directory.is_dir():
            return None
        files = sorted(directory.glob("*.json"), key=lambda p: p.name)
        if not files:
            return None
        paths.extend((f"{rel_dir}/{p.name}", p) for p in files)
    h = hashlib.sha256()
    for rel, path in sorted(paths):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


# --- git -------------------------------------------------------------------
def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True)
    except FileNotFoundError:
        return 127, ""
    return proc.returncode, proc.stdout


def _git_state(root: Path) -> dict:
    rc_head, head = _git(root, "rev-parse", "HEAD")
    commit = head.strip() if rc_head == 0 else None

    rc_branch, branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    # Raw reports/manifests are runtime products and may be untracked beneath
    # the checkout after a clean run.  They must not make verification
    # impossible.  Track all modifications to versioned files, then add back
    # only untracked files that can affect the harness, scoring, or corpus.
    rc_status, porcelain = _git(
        root, "status", "--porcelain", "--untracked-files=no")
    rc_untracked, untracked = _git(
        root, "ls-files", "--others", "--exclude-standard")
    if rc_status == 0 and rc_untracked == 0:
        relevant_untracked = []
        for rel in untracked.splitlines():
            if (rel in _KEY_FILE_PATHS
                    or (rel.endswith(".py") and rel.startswith(
                        ("src/", "scripts/", "integrations/")))
                    or rel == _URL_REGISTRY or rel == _WIKI_BLOOM
                    or rel.startswith(_ANSWER_KEYS_DIR + "/")
                    or rel.startswith(_TASKS_DIR + "/")):
                relevant_untracked.append(f"?? {rel}")
        if relevant_untracked:
            porcelain = "\n".join(
                [x for x in porcelain.splitlines() if x.strip()] + relevant_untracked)

    state: dict = {
        "commit": commit,
        "branch": branch.strip() if rc_branch == 0 else None,
        "is_git_repo": rc_head == 0,
    }
    if rc_status != 0:
        # Not a git repo, or git unavailable: cannot vouch for cleanliness.
        state["clean"] = None
        return state

    dirty_lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    clean = len(dirty_lines) == 0
    state["clean"] = clean
    if not clean:
        # A dirty tree means the recorded commit does NOT describe what ran.
        # We cannot embed the whole diff, so we fingerprint it: the porcelain
        # status (which lists untracked files too) plus the tracked diff.
        _, diff = _git(root, "diff", "HEAD")
        blob = porcelain + "\n--DIFF--\n" + diff
        state["dirty_digest"] = _sha256_bytes(blob.encode("utf-8"))
        state["dirty_files"] = [ln[3:] if len(ln) > 3 else ln for ln in dirty_lines]
    return state


def _gateway_fingerprint(env: dict[str, str],
                         gateway_policy: dict | None) -> dict:
    cfg = (env.get("LLM_GATEWAY_CONFIG") or "").strip()
    return {
        "config_path": cfg or None,
        "config_sha256": _sha256_file(Path(cfg)) if cfg else None,
        "live_policy": gateway_policy,
    }


# --- generate --------------------------------------------------------------
def generate(root: Path | str = ROOT, *, env: dict[str, str] | None = None,
             now: datetime | None = None,
             model_identity: list[dict] | None = None,
             gateway_policy: dict | None = None) -> dict:
    """Build the manifest for a run executing on THIS host, right now.

    `env`, `now`, `model_identity` are injectable so the manifest is fully
    deterministic under test. `model_identity` is a list of already-run
    probe_model_identity() results (this function never opens a socket)."""
    root = Path(root)
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)

    return {
        "manifest_version": 2,
        "generated_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "git": _git_state(root),
        "key_files": _key_file_hashes(root),
        # The harness shell is not the system under test. `8377cd8d` routed
        # gpt-researcher's retriever through the shim by rewriting code that
        # lives in `.venv-gptr/lib/*/site-packages/gpt_researcher/`, and nothing
        # in this manifest would have noticed if the box had never installed it.
        # Hash each framework's installed tree, not just our adapter.
        "frameworks": _framework_hashes(root),
        # The scoring formula is part of a run's identity: the same reports under
        # different weights are different numbers. Read from the single source of
        # truth rather than re-declared here, so the two cannot drift.
        "formula_version": _formula_version(),
        "env": _env_snapshot(dict(env)),
        "corpus": {
            "url_registry_sha256": _sha256_file(root / _URL_REGISTRY),
            "answer_keys_sha256": _dir_content_hash(root / _ANSWER_KEYS_DIR),
            "task_inputs_sha256": _dir_content_hash(root / _TASKS_DIR),
            "answer_keys_task_set_hash": task_set_hash(root),
            # Wiki membership for ~19M articles lives in the bloom filter, not in
            # url_registry.json (which lists ~1k explicit titles). An absent or
            # rebuilt bloom silently changes `reach` for every wiki citation, and
            # truth = reach^1.5 * quality, so it changes truth. Hashing only the
            # JSON let two non-comparable boards verify clean.
            "wiki_bloom_sha256": _sha256_file(root / _WIKI_BLOOM),
        },
        "model_identity": list(model_identity or []),
        # The gateway door's policy is part of a run's identity too: the same
        # request leaves it with a different budget/thinking under a different
        # registry. `config_sha256` pins the file the NEXT restart would load;
        # `live_policy` (capture_gateway_policy) pins what the serving process
        # says it is running NOW. Recording both lets drift between them fail
        # a comparison loudly instead of changing scores silently.
        "gateway": _gateway_fingerprint(env, gateway_policy),
    }


# --- model identity probe --------------------------------------------------
def probe_model_identity(endpoint: str, api_key: str, declared: str, *,
                         transport=None, model_for_request: str | None = None,
                         timeout_s: float | None = None) -> dict:
    """Ask an OpenAI-compatible endpoint what model it actually is and assert it
    equals `declared`. Catches the claude-code-lane accident where qwen3-8b
    output was filed under deepseek.

    Network is behind an injectable `transport(url, headers, json_body) -> dict`
    so this is unit-testable and NEVER hits the wire in tests or preflight. When
    `transport` is None a real requests-based call is built lazily, so importing
    this module costs nothing and needs no `requests`."""
    if timeout_s is None:
        timeout_s = float(os.environ.get("DRA_MODEL_PROBE_TIMEOUT_S", "20"))
    if timeout_s <= 0:
        raise ValueError("model identity probe timeout must be positive")
    if transport is None:
        transport = _requests_transport(timeout_s)

    url = endpoint.rstrip("/") + "/chat/completions"
    body = {
        "model": model_for_request or declared,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result: dict = {"endpoint": endpoint, "declared": declared,
                    "actual": None, "ok": False, "error": None}
    try:
        resp = transport(url, headers, body)
    except Exception as exc:  # noqa: BLE001 - the probe records any failure, never raises
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    actual = None
    if isinstance(resp, dict):
        actual = resp.get("model")
    result["actual"] = actual
    if actual is None:
        result["error"] = "endpoint response carried no `model` field"
        return result

    # Exact match, after case/whitespace normalisation. Prefix matching used to
    # be allowed here "because endpoints return a fuller id". It also lets
    #     deepseek-v4-flash-awq-int4  .startswith(  deepseek-v4-flash  )
    # pass as the full-precision model, and glm-4.5-air pass as glm-4.5. A
    # quantised or distilled checkpoint is a different system under test. If an
    # endpoint really does report a longer id, declare that id in
    # `config/lane_protocol.yaml` and pass it here; do not widen the predicate.
    a, d = actual.strip().lower(), declared.strip().lower()
    result["ok"] = a == d
    if not result["ok"]:
        result["error"] = (f"endpoint reports {actual!r}, lane declares {declared!r}. "
                           "Declare the exact id the endpoint returns rather than "
                           "loosening this check.")

    # What this probe can and cannot prove. It asks an endpoint for its name and
    # believes the answer. vLLM's `--served-model-name` is a free-text flag, and
    # a hosted API returns whatever id it likes. So this catches a misrouted lane
    # (the claude-code accident: qwen3-8b output filed under deepseek) and does
    # NOT establish which weights ran. Boards must not claim otherwise.
    result["identity_scope"] = "endpoint-self-reported"
    return result


def _requests_transport(timeout_s: float):
    def _call(url: str, headers: dict, body: dict) -> dict:
        import requests  # lazy: keeps the module import-light and test-isolated
        r = requests.post(url, headers=headers, json=body, timeout=timeout_s)
        r.raise_for_status()
        return r.json()
    return _call


def capture_gateway_policy(url: str, *, transport=None,
                           timeout_s: float = 10.0) -> dict:
    """Snapshot the IN-SERVICE gateway's live policy from its /healthz.

    The manifest used to record only the launcher process's env and disk
    hashes; the gateway's ACTIVE registry (per-prefix context_window /
    fit_to_window / max_tokens cap+floor / thinking_off) lived in a long-running
    process, so a server-side policy edit -- or an edited config the server had
    not reloaded -- changed scores under a byte-identical manifest
    (SPEC_ISSUES §2, manifest entry). This captures what the serving process
    SAYS it is running, next to the config-file hash generate() records, so the
    two can disagree loudly instead of silently.

    `transport(url) -> dict` is injectable like probe_model_identity's; the
    default is a lazy requests GET. Never raises: a failed capture is recorded
    as ok=False for the caller to treat as fatal or not.
    """
    if transport is None:
        def transport(u: str) -> dict:  # pragma: no cover - thin wire adapter
            import requests  # lazy: keeps the module import-light
            r = requests.get(u, timeout=timeout_s)
            r.raise_for_status()
            return r.json()
    healthz = url.rstrip("/")
    if not healthz.endswith("/healthz"):
        healthz += "/healthz"
    out: dict = {"url": healthz, "ok": False, "models": None, "error": None}
    try:
        doc = transport(healthz)
    except Exception as exc:  # noqa: BLE001 - the capture records, never raises
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    if not isinstance(doc, dict) or "models" not in doc:
        out["error"] = "healthz response carried no `models` registry"
        return out
    out["ok"] = True
    out["models"] = doc.get("models")
    return out


# --- verify ----------------------------------------------------------------
def verify(manifest: dict, reports_dir: Path | str, *,
           hostname: str | None = None, root: Path | str = ROOT) -> list[str]:
    """Return a list of reasons this report set must NOT be scored. Empty list
    means the manifest vouches for the run. The scorer calls this and refuses on
    any non-empty result.

    `hostname` is injectable for tests; None means "the host doing the scoring
    now", which is the honesty check: a manifest generated on another machine
    cannot vouch for what ran here."""
    root = Path(root)
    reports_dir = Path(reports_dir)
    violations: list[str] = []

    if not isinstance(manifest, dict) or not manifest:
        return ["manifest is empty or not an object; nothing vouches for this run"]

    required = (
        "manifest_version", "generated_utc", "host", "git", "key_files",
        "frameworks", "formula_version", "env", "corpus", "model_identity",
    )
    for key in required:
        if key not in manifest:
            violations.append(f"manifest missing required section {key!r}")
    if violations:
        return violations  # a malformed manifest cannot be trusted further

    if manifest.get("manifest_version") != 2:
        violations.append(
            f"manifest_version must be 2, got {manifest.get('manifest_version')!r}; "
            "older manifests do not pin the full code/task/framework closure")

    # The scoring formula is part of a run's identity, exactly like the corpus
    # hashes verify() already re-derives. Without these two checks a manifest
    # whose formula probe broke (recorded as `UNRESOLVED: ImportError`) still
    # vouched for the run, and reports scored under one formula could be ranked
    # against reports scored under another.
    fv = manifest.get("formula_version") or ""
    if not fv or fv.startswith("UNRESOLVED"):
        violations.append(
            f"manifest formula_version is {fv!r}: the run does not record which "
            "scoring formula produced it")
    else:
        try:
            from scripts.build_truth_board import FORMULA_VERSION as _now
            if fv != _now:
                violations.append(
                    f"manifest formula_version {fv!r} != scorer {_now!r}: these "
                    "reports were produced under a different formula and are not "
                    "comparable to boards built now")
        except Exception as e:  # noqa: BLE001
            violations.append(f"cannot read the current formula_version: {e}")

    # Honesty: the manifest must describe the host now scoring. Generated on the
    # workstation, run on the box, scored on the box -> this fires.
    current = hostname if hostname is not None else socket.gethostname()
    recorded = (manifest.get("host") or {}).get("hostname")
    if recorded != current:
        violations.append(
            f"manifest was generated on host {recorded!r} but scoring runs on "
            f"{current!r}; a manifest only vouches for the host that produced it")

    git = manifest.get("git") if isinstance(manifest.get("git"), dict) else {}
    rec_commit = git.get("commit")
    if not (isinstance(rec_commit, str) and len(rec_commit) == 40
            and all(c in "0123456789abcdef" for c in rec_commit.lower())):
        violations.append("manifest records no git commit; the run's code version "
                          "is unknown (the exact defect this manifest exists to fix)")
    if git.get("clean") is not True:
        if git.get("clean") is False:
            violations.append(
                f"run executed on a DIRTY tree (dirty_digest="
                f"{git.get('dirty_digest')}); the recorded commit "
                f"{git.get('commit')} does not describe what actually ran")
        else:
            violations.append("manifest could not determine tree cleanliness "
                              "(not a git checkout at generation time)")

    # Verification is about the bytes used NOW, not only what the manifest said
    # at generation.  The original check trusted a recorded clean HEAD while the
    # scorer could be running at another commit or on a newly dirty tree.
    cur_git = _git_state(root)
    if cur_git.get("commit") != rec_commit:
        violations.append(
            f"current HEAD {cur_git.get('commit')!r} != manifest HEAD "
            f"{rec_commit!r}; the scorer is not running the pinned code")
    if cur_git.get("clean") is not True:
        violations.append(
            "current scoring checkout is not clean; its HEAD does not describe "
            "the code that verify() is inspecting")

    probes = manifest.get("model_identity")
    if not isinstance(probes, list) or not probes:
        violations.append(
            "manifest model_identity must contain at least one successful "
            "per-backbone endpoint probe")
    else:
        for i, probe in enumerate(probes):
            if not isinstance(probe, dict):
                violations.append(f"model identity probe #{i} is not an object")
                continue
            for field in ("endpoint", "declared", "actual"):
                if not isinstance(probe.get(field), str) or not probe[field].strip():
                    violations.append(
                        f"model identity probe #{i} has no non-empty {field}")
            if probe.get("ok") is not True:
                violations.append(
                    f"model identity mismatch on {probe.get('endpoint')}: "
                    f"{probe.get('error') or 'declared != actual'}")

    env = manifest.get("env")
    if not isinstance(env, dict) or not env:
        violations.append(
            "manifest env must be a non-empty snapshot of run-affecting knobs")
    elif not all(isinstance(k, str) and k and isinstance(v, str)
                 for k, v in env.items()):
        violations.append("manifest env contains a non-string or empty entry")

    frameworks = manifest.get("frameworks")
    frameworks_valid = isinstance(frameworks, dict) and bool(frameworks)
    if not frameworks_valid:
        violations.append(
            "manifest frameworks is empty; no installed framework source is pinned")
    else:
        for name, entry in frameworks.items():
            if not isinstance(name, str) or not name or not isinstance(entry, dict):
                frameworks_valid = False
                violations.append(f"framework entry {name!r} is malformed")
                continue
            if not _valid_sha256(entry.get("site_packages_sha256")):
                frameworks_valid = False
                violations.append(
                    f"framework {name!r} has no valid site_packages_sha256")
            if not isinstance(entry.get("n_files"), int) or entry.get("n_files", 0) <= 0:
                frameworks_valid = False
                violations.append(f"framework {name!r} contains no hashed source files")
            if not _valid_sha256(entry.get("python_sha256")):
                frameworks_valid = False
                violations.append(f"framework {name!r} has no valid python_sha256")
        current_frameworks = _framework_hashes(root)
        if not current_frameworks:
            violations.append(
                "current checkout has no .venv-* framework trees to compare")
        elif current_frameworks != frameworks:
            violations.append(
                "installed framework source/interpreter hashes changed since the run")

    # Corpus reproducibility: the golden the scorer will grade against must be
    # byte-identical to what the manifest pinned at run time.
    corpus = manifest.get("corpus") if isinstance(manifest.get("corpus"), dict) else {}
    corpus_checks = {
        "url_registry_sha256": _sha256_file(root / _URL_REGISTRY),
        "answer_keys_sha256": _dir_content_hash(root / _ANSWER_KEYS_DIR),
        "task_inputs_sha256": _dir_content_hash(root / _TASKS_DIR),
        "answer_keys_task_set_hash": task_set_hash(root),
        "wiki_bloom_sha256": _sha256_file(root / _WIKI_BLOOM),
    }
    for field, current_hash in corpus_checks.items():
        recorded_hash = corpus.get(field)
        if not _valid_sha256(recorded_hash):
            violations.append(
                f"manifest corpus {field} is missing or not a valid sha256")
            continue
        if not _valid_sha256(current_hash):
            violations.append(
                f"current corpus input for {field} is missing or unreadable")
            continue
        if current_hash != recorded_hash:
            label = {
                "answer_keys_sha256": "answer_keys changed",
                "task_inputs_sha256": "task inputs changed",
                "answer_keys_task_set_hash": "answer_keys/task set changed",
                "wiki_bloom_sha256": "wiki_bloom.bin changed",
                "url_registry_sha256": "url_registry.json changed",
            }.get(field, f"corpus {field} changed")
            violations.append(
                f"{label} since the run "
                f"(manifest={recorded_hash}, now={current_hash})")

    # The manifest RECORDS the scoring/harness file hashes and, until now, never
    # compared them. An edit to `decidable_scorer.py` that does not bump
    # FORMULA_VERSION changed the numbers while every recorded field stayed
    # equal, so two boards built from different scorers verified as comparable.
    rec_files = manifest.get("key_files")
    cur_files = _key_file_hashes(root)
    if not isinstance(rec_files, dict) or not rec_files:
        violations.append(
            "manifest key_files is empty; scoring/harness code is not pinned")
        rec_files = {}
    invalid_rec_files = sorted(f for f, h in rec_files.items()
                               if not isinstance(f, str) or not _valid_sha256(h))
    if invalid_rec_files:
        violations.append(
            f"manifest key_files contains missing/invalid hashes: "
            f"{invalid_rec_files[:6]}")
    invalid_cur_files = sorted(f for f, h in cur_files.items()
                               if not _valid_sha256(h))
    if invalid_cur_files:
        violations.append(
            f"current scoring/harness closure has missing files: "
            f"{invalid_cur_files[:6]}")
    missing_now = sorted(set(rec_files) - set(cur_files))
    added_now = sorted(set(cur_files) - set(rec_files))
    drifted = sorted(f for f in set(rec_files) & set(cur_files)
                     if cur_files[f] != rec_files[f])
    if missing_now or added_now:
        violations.append(
            "scoring/harness dependency closure changed since the run: "
            f"missing_now={missing_now[:4]}, added_now={added_now[:4]}")
    if drifted:
        violations.append(
            "scoring/harness code changed since the run without a "
            f"FORMULA_VERSION bump: {drifted[:6]}"
            + (f" (+{len(drifted) - 6} more)" if len(drifted) > 6 else "")
            + ". These reports were produced by different code than the scorer "
              "about to grade them.")

    if not reports_dir.is_dir():
        violations.append(f"reports dir {reports_dir} does not exist; nothing to score")
    elif not any(reports_dir.iterdir()):
        violations.append(f"reports dir {reports_dir} is empty; nothing to score")

    return violations


# --- CLI -------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="write a manifest for this host to PATH")
    ap.add_argument("--verify", type=Path, metavar="MANIFEST",
                    help="verify MANIFEST against --reports-dir; nonzero exit on any violation")
    ap.add_argument("--reports-dir", type=Path, help="report set to verify")
    ap.add_argument(
        "--model-probe", action="append", default=[],
        metavar="ENDPOINT,DECLARED,API_KEY_ENV[,REQUEST_MODEL]",
        help=("probe one OpenAI-compatible endpoint and pin its self-reported "
              "model identity. Repeat once per scored backbone. API_KEY_ENV is "
              "the name of an environment variable; its secret value is never "
              "written to the manifest."),
    )
    ap.add_argument(
        "--gateway", metavar="URL", default=None,
        help=("capture the in-service gateway's live policy from URL/healthz "
              "into the manifest. A failed capture refuses to write, like a "
              "failed model probe: asking for the fingerprint and shipping "
              "without it would be the silent gap this flag exists to close."),
    )
    args = ap.parse_args(argv)

    if args.verify:
        manifest = json.loads(Path(args.verify).read_text())
        if not args.reports_dir:
            print("--verify requires --reports-dir", file=sys.stderr)
            return 2
        violations = verify(manifest, args.reports_dir)
        if violations:
            print(f"REFUSE TO SCORE: {len(violations)} manifest violation(s):",
                  file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            return 1
        print("manifest OK: the run is vouched for and reproducible")
        return 0

    if not args.model_probe:
        print(
            "refusing to generate an unverifiable manifest: provide at least "
            "one --model-probe ENDPOINT,DECLARED,API_KEY_ENV[,REQUEST_MODEL]",
            file=sys.stderr,
        )
        return 2

    probes: list[dict] = []
    for raw in args.model_probe:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) not in (3, 4) or not all(parts[:3]):
            print(
                f"invalid --model-probe {raw!r}; expected "
                "ENDPOINT,DECLARED,API_KEY_ENV[,REQUEST_MODEL]",
                file=sys.stderr,
            )
            return 2
        endpoint, declared, key_env = parts[:3]
        request_model = parts[3] if len(parts) == 4 and parts[3] else None
        api_key = os.environ.get(key_env, "")
        if not api_key:
            print(
                f"--model-probe names {key_env!r}, but that environment variable "
                "is unset or empty",
                file=sys.stderr,
            )
            return 2
        probe = probe_model_identity(
            endpoint, api_key, declared, model_for_request=request_model)
        probes.append(probe)
        if not probe.get("ok"):
            print(
                f"model identity probe failed for {endpoint}: {probe.get('error')}",
                file=sys.stderr,
            )
            return 3

    gateway_policy = None
    if args.gateway:
        gateway_policy = capture_gateway_policy(args.gateway)
        if not gateway_policy.get("ok"):
            print(
                f"gateway policy capture failed for {args.gateway}: "
                f"{gateway_policy.get('error')}",
                file=sys.stderr,
            )
            return 3

    manifest = generate(model_identity=probes, gateway_policy=gateway_policy)
    generation_errors: list[str] = []
    if manifest.get("git", {}).get("clean") is not True:
        generation_errors.append("the run checkout is not clean")
    if not manifest.get("env"):
        generation_errors.append("no run-affecting environment variables were captured")
    if not manifest.get("frameworks"):
        generation_errors.append("no .venv-* framework source trees were found")
    if any(not _valid_sha256(v) for v in manifest.get("key_files", {}).values()):
        generation_errors.append("the scoring/harness dependency closure has missing files")
    for field, value in (manifest.get("corpus") or {}).items():
        if not _valid_sha256(value):
            generation_errors.append(f"corpus fingerprint {field} is missing or invalid")
    if generation_errors:
        print("refusing to write an incomplete manifest:", file=sys.stderr)
        for reason in generation_errors:
            print(f"  - {reason}", file=sys.stderr)
        return 2

    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
