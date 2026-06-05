#!/usr/bin/env python3
"""Seed the Postmill sandbox forum with the curated non-tech topic threads.

The WebArena Postmill corpus is tech-heavy, so non-tech DR tasks (finance,
health, environment, education, policy, travel, music-business...) had no
on-topic forum content and were quarantined (docs/EVAL_SET_REMEDIATION.md).
This inserts the review-vetted threads in data/corpus_seed/forum_threads.json
so those tasks regain a real forum third.

Runs ON the box (needs the sandbox up). Idempotent: creates a forum only if its
normalized_name is absent; inserts a thread only if (forum, title) is absent, so
it is safe to re-run and to re-apply after `reset.sh` wipes the DB. Postmill's
BEFORE INSERT trigger fills search_doc, so the new threads are immediately
searchable (which is how scripts/build_deep_golden.py re-crawls them).

  python3 scripts/seed_forum_corpus.py            # seed
  python3 scripts/seed_forum_corpus.py --dry-run  # show what would change

Container defaults to dr_sandbox_reddit (unified compose); override with
--container.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "corpus_seed" / "forum_threads.json"

# An existing Postmill user to author the seeded threads (WebArena seed users).
AUTHOR_CANDIDATES = ["MarvelsGrantMan136", "Don_Gato1"]


def _psql(container: str, sql: str, rows: bool = True) -> str:
    cmd = ["docker", "exec", "-i", container, "psql", "-U", "postmill",
           "-d", "postmill", "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t", "-c", sql]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"psql failed: {p.stderr.strip()}\nSQL: {sql[:200]}")
    return p.stdout.strip()


def _q(s: str) -> str:
    return "'" + (s or "").replace("'", "''") + "'"


def _notnull_cols(container: str, table: str) -> dict[str, str | None]:
    """{column: default} for NOT NULL columns of `table` (default None if none)."""
    out = _psql(container,
                f"SELECT column_name, column_default FROM information_schema.columns "
                f"WHERE table_name='{table}' AND is_nullable='NO'")
    cols: dict[str, str | None] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0]
        default = parts[1] if len(parts) > 1 and parts[1] != "" else None
        cols[name] = default
    return cols


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--container", default="dr_sandbox_reddit")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    data = json.loads(SEED.read_text(encoding="utf-8"))
    threads = data["threads"]
    forums = sorted({t["forum"] for t in threads})
    c = args.container

    # author user id
    author_id = None
    for u in AUTHOR_CANDIDATES:
        r = _psql(c, f"SELECT id FROM users WHERE username={_q(u)} LIMIT 1")
        if r.strip():
            author_id = int(r.strip()); break
    if author_id is None:
        author_id = int(_psql(c, "SELECT id FROM users ORDER BY id LIMIT 1").strip())

    existing_forums = {x.lower() for x in _psql(
        c, "SELECT normalized_name FROM forums").splitlines() if x.strip()}
    max_fid = int(_psql(c, "SELECT COALESCE(max(id),0) FROM forums").strip())
    max_sid = int(_psql(c, "SELECT COALESCE(max(id),0) FROM submissions").strip())
    f_cols = _notnull_cols(c, "forums")
    s_cols = _notnull_cols(c, "submissions")

    # ---- create missing forums ----
    new_forums = [f for f in forums if f.lower() not in existing_forums]
    print(f"forums: {len(forums)} total, {len(new_forums)} new; author_id={author_id} "
          f"max_fid={max_fid} max_sid={max_sid}")
    fid_of: dict[str, int] = {}
    sql_stmts: list[str] = []
    for f in new_forums:
        max_fid += 1
        fid_of[f] = max_fid
        cols = {"id": str(max_fid), "name": _q(f), "title": _q(f),
                "normalized_name": _q(f.lower()), "created": "now()",
                "featured": "false"}
        # fill any other NOT NULL col w/o default we did not set
        for col, dflt in f_cols.items():
            if col not in cols and dflt is None:
                cols[col] = "0" if col.endswith(("_count", "id")) else "''"
        keys = ",".join(cols); vals = ",".join(cols[k] for k in cols)
        sql_stmts.append(f"INSERT INTO forums ({keys}) VALUES ({vals});")
    # resolve fids for pre-existing forums
    for f in forums:
        if f not in fid_of:
            r = _psql(c, f"SELECT id FROM forums WHERE normalized_name={_q(f.lower())} LIMIT 1")
            if r.strip():
                fid_of[f] = int(r.strip())

    # ---- insert threads (skip existing by forum+title) ----
    inserted = 0
    for t in threads:
        f = t["forum"]; fid = fid_of.get(f)
        if fid is None:
            continue
        dup = _psql(c, f"SELECT 1 FROM submissions WHERE forum_id={fid} AND title={_q(t['title'])} LIMIT 1")
        if dup.strip():
            continue
        max_sid += 1
        cols = {"id": str(max_sid), "forum_id": str(fid), "user_id": str(author_id),
                "title": _q(t["title"]), "body": _q(t["body"]), "timestamp": "now()",
                "last_active": "now()", "url": "NULL", "media_type": _q("url"),
                "sticky": "false", "comment_count": "0", "net_score": "0",
                "ranking": "0", "user_flag": "0", "visibility": _q("visible")}
        for col, dflt in s_cols.items():
            if col not in cols and dflt is None:
                cols[col] = "0" if col.endswith(("_count", "_score", "id", "ranking", "user_flag")) else "''"
        keys = ",".join(cols); vals = ",".join(cols[k] for k in cols)
        sql_stmts.append(f"INSERT INTO submissions ({keys}) VALUES ({vals});")
        inserted += 1

    print(f"threads: {inserted} to insert (of {len(threads)})")
    if args.dry_run:
        print("--- dry-run; first 3 statements ---")
        for s in sql_stmts[:3]:
            print(s[:300])
        return 0
    if not sql_stmts:
        print("nothing to do."); return 0

    script = "BEGIN;\n" + "\n".join(sql_stmts) + "\nCOMMIT;\n"
    p = subprocess.run(["docker", "exec", "-i", c, "psql", "-U", "postmill",
                        "-d", "postmill", "-v", "ON_ERROR_STOP=1"],
                       input=script, capture_output=True, text=True)
    if p.returncode != 0:
        print("SEED FAILED:\n" + p.stderr[-1500:], file=sys.stderr)
        return 1
    print(f"seeded OK: {len(new_forums)} forums + {inserted} threads")
    # verify a couple are searchable
    sample = threads[0]
    kw = sample["title"].split()[0]
    cnt = _psql(c, f"SELECT count(*) FROM submissions WHERE title ILIKE {_q('%'+kw+'%')}").strip()
    print(f"verify: submissions with title like '{kw}': {cnt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
