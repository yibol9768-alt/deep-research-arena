"""Offline tests for the judge-vs-human alignment harness.

No network: the judge callable is mocked, and report / pref data are
synthetic files in a tmp dir. Covers:
  1. full alignment run writes a per-dim kappa markdown without network,
  2. --dry-run lists the correct pair count without calling the judge,
  3. compute_judge_human_kappa on an empty prefs dir exits 0 with the
     clear "no labels" message.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.validate_judge_alignment as vja  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _write_report(d: Path, agent: str, task: str, body: str, suffix=""):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{agent}__{task}{suffix}.md").write_text(body)


def _args(**over):
    ap = vja.build_argparser()
    base = ap.parse_args([])
    for k, v in over.items():
        setattr(base, k, v)
    return base


# ---------------------------------------------------------------------------
# test 1: full alignment run, mocked judge, writes markdown, no network
# ---------------------------------------------------------------------------

def test_alignment_writes_markdown_offline(tmp_path, monkeypatch):
    prefs_dir = tmp_path / "human_prefs"
    report_dir = tmp_path / "deep_reports"
    out_md = tmp_path / "ALIGN_V2.md"

    # Synthetic human labels: agent_x vs agent_y on two tasks.
    _write_jsonl(prefs_dir / "labels.jsonl", [
        {"task_id": "t1", "agent_a": "ax", "agent_b": "ay",
         "winner": "a", "dims": ["depth", "rigor"], "annotator": "h1"},
        {"task_id": "t2", "agent_a": "ax", "agent_b": "ay",
         "winner": "b", "dims_cited": ["depth"], "annotator": "h2"},
    ])
    for t in ("t1", "t2"):
        _write_report(report_dir, "ax", t, "Report AX body for " + t)
        _write_report(report_dir, "ay", t, "Report AY body for " + t)

    monkeypatch.setattr(vja, "PREFS_DIR", prefs_dir)
    monkeypatch.setattr(vja, "REPORT_DIRS", [report_dir])
    monkeypatch.setattr(vja, "OUT_MD", out_md)
    monkeypatch.setattr(vja, "PRIOR_MD", tmp_path / "nope.md")

    calls = {"n": 0}

    def fake_factory():
        def judge(dim, intent, agent_a, ans_a, agent_b, ans_b):
            calls["n"] += 1
            # Deterministic mock: judge always picks "a".
            return "a"
        return judge, "mock-judge"

    monkeypatch.setattr(vja, "make_judge", fake_factory)

    rc = vja.run_alignment(_args(dims=["depth", "rigor"]), judge_factory=fake_factory)
    assert rc == 0
    assert calls["n"] > 0, "judge should have been called"
    assert out_md.exists(), "alignment markdown should be written"

    text = out_md.read_text()
    assert "Judge / Human alignment (V2)" in text
    assert "kappa" in text.lower()
    assert "Weakest dimension" in text
    # depth was cited on both pairs -> two rows for depth.
    assert "| depth |" in text


def test_alignment_dry_run_counts_pairs_no_judge(tmp_path, monkeypatch):
    prefs_dir = tmp_path / "human_prefs"
    report_dir = tmp_path / "deep_reports"

    _write_jsonl(prefs_dir / "labels.jsonl", [
        {"task_id": "t1", "agent_a": "ax", "agent_b": "ay", "winner": "a"},
        {"task_id": "t2", "agent_a": "ax", "agent_b": "ay", "winner": "b"},
        # This one has no report -> should be skipped (missing-reports).
        {"task_id": "t9", "agent_a": "ax", "agent_b": "ay", "winner": "a"},
    ])
    for t in ("t1", "t2"):
        _write_report(report_dir, "ax", t, "ax " + t, suffix="_matrix")
        _write_report(report_dir, "ay", t, "ay " + t)

    monkeypatch.setattr(vja, "PREFS_DIR", prefs_dir)
    monkeypatch.setattr(vja, "REPORT_DIRS", [report_dir])

    def boom_factory():
        raise AssertionError("judge must NOT be constructed in --dry-run")

    rows, missing = vja.build_worklist(
        vja.load_prefs(prefs_dir), ["depth"], [report_dir], 0)
    assert len(rows) == 2
    assert missing == 1

    rc = vja.run_alignment(_args(dims=["depth"], dry_run=True),
                           judge_factory=boom_factory)
    assert rc == 0


def test_dry_run_respects_limit(tmp_path, monkeypatch):
    prefs_dir = tmp_path / "human_prefs"
    report_dir = tmp_path / "deep_reports"
    recs = []
    for i in range(5):
        t = f"t{i}"
        recs.append({"task_id": t, "agent_a": "ax", "agent_b": "ay", "winner": "a"})
        _write_report(report_dir, "ax", t, "ax " + t)
        _write_report(report_dir, "ay", t, "ay " + t)
    _write_jsonl(prefs_dir / "labels.jsonl", recs)

    rows, missing = vja.build_worklist(
        vja.load_prefs(prefs_dir), ["depth"], [report_dir], 2)
    assert len(rows) == 2
    assert missing == 0


# ---------------------------------------------------------------------------
# test 2: report matching suffixes + deterministic pick
# ---------------------------------------------------------------------------

def test_find_report_suffix_priority(tmp_path):
    d1 = tmp_path / "deep_reports"
    d2 = tmp_path / "deep"
    _write_report(d2, "ax", "t1", "matrix body", suffix="_matrix")
    # canonical (no suffix) in the higher-priority dir should win
    _write_report(d1, "ax", "t1", "canonical body")
    p = vja.find_report("ax", "t1", [d1, d2])
    assert p is not None
    assert p.read_text() == "canonical body"

    # only suffixed available
    p2 = vja.find_report("ax", "t1", [d2])
    assert p2 is not None and p2.read_text() == "matrix body"

    # missing
    assert vja.find_report("zz", "t1", [d1, d2]) is None


# ---------------------------------------------------------------------------
# test 3: compute_judge_human_kappa on empty prefs exits 0 with clear message
# ---------------------------------------------------------------------------

def test_compute_kappa_empty_prefs_exits_zero(tmp_path):
    empty = tmp_path / "human_prefs_empty"
    empty.mkdir()
    script = ROOT / "scripts" / "compute_judge_human_kappa.py"
    code = (
        "import runpy, sys, pathlib;"
        f"import scripts.compute_judge_human_kappa as m;"
        f"m.PREFS_DIR = pathlib.Path({str(empty)!r});"
        "m.main()"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "no human labels found" in proc.stdout.lower()


def test_compute_kappa_accepts_new_dims_field(tmp_path, monkeypatch):
    import scripts.compute_judge_human_kappa as m
    rec = {"task_id": "t1", "agent_a": "ax", "agent_b": "ay",
           "winner": "a", "dims": ["depth"]}
    cited = set(rec.get("dims_cited") or []) | set(rec.get("dims") or [])
    assert "depth" in cited


# ---------------------------------------------------------------------------
# proxy mode: runs offline with mocked judge, no human labels
# ---------------------------------------------------------------------------

def test_proxy_mode_offline(tmp_path, monkeypatch, capsys):
    report_dir = tmp_path / "deep_reports"
    for t in ("t1", "t2"):
        _write_report(report_dir, "ax", t, "ax " + t)
        _write_report(report_dir, "ay", t, "ay " + t)
        _write_report(report_dir, "az", t, "az " + t)

    monkeypatch.setattr(vja, "REPORT_DIRS", [report_dir])

    seq = {"i": 0}

    def fake_factory():
        def judge(dim, intent, agent_a, ans_a, agent_b, ans_b):
            seq["i"] += 1
            # alternate to exercise the modal/agreement math
            return "a" if seq["i"] % 2 == 0 else "b"
        return judge, "mock-judge"

    rc = vja.run_proxy(_args(dims=["depth"], samples=3),
                       judge_factory=fake_factory)
    assert rc == 0
    out = capsys.readouterr().out
    assert "offline proxy metrics" in out
    assert "self-consistency" in out
    assert "NECESSARY BUT NOT SUFFICIENT" in out


def test_proxy_dry_run_no_judge(tmp_path, monkeypatch, capsys):
    report_dir = tmp_path / "deep_reports"
    for t in ("t1",):
        _write_report(report_dir, "ax", t, "ax")
        _write_report(report_dir, "ay", t, "ay")
    monkeypatch.setattr(vja, "REPORT_DIRS", [report_dir])

    def boom_factory():
        raise AssertionError("judge must not be built in proxy --dry-run")

    rc = vja.run_proxy(_args(dims=["depth"], dry_run=True, samples=3),
                       judge_factory=boom_factory)
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out


def test_judge_unavailable_clear_error(tmp_path, monkeypatch, capsys):
    prefs_dir = tmp_path / "human_prefs"
    report_dir = tmp_path / "deep_reports"
    _write_jsonl(prefs_dir / "l.jsonl", [
        {"task_id": "t1", "agent_a": "ax", "agent_b": "ay", "winner": "a"},
    ])
    _write_report(report_dir, "ax", "t1", "ax")
    _write_report(report_dir, "ay", "t1", "ay")
    monkeypatch.setattr(vja, "PREFS_DIR", prefs_dir)
    monkeypatch.setattr(vja, "REPORT_DIRS", [report_dir])

    def unavailable():
        raise vja.JudgeUnavailable("no judge here")

    rc = vja.run_alignment(_args(dims=["depth"]), judge_factory=unavailable)
    assert rc == 2
    assert "no judge here" in capsys.readouterr().err


def test_cohen_kappa_basic():
    # perfect agreement
    k, n, agree = vja.cohen_kappa([("a", "a"), ("b", "b"), ("a", "a"), ("b", "b")])
    assert n == 4 and agree == 1.0 and abs(k - 1.0) < 1e-9
    # ties dropped
    k2, n2, _ = vja.cohen_kappa([("tie", "a"), ("a", "a")])
    assert n2 == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
