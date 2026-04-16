"""Subprocess wrapper for running SQL against the sandbox DBs.

The MySQL and PostgreSQL ports on westd are NOT exposed — both DBs live inside
their respective Docker containers (webarena_shopping / webarena_reddit) and
only listen on the container-internal 3306 / 5432. We avoid SSH tunnels and
instead invoke `ssh westd wsl -- docker exec <container> <client> ...`,
which is slower per query but zero-config.

A single query round-trip is ~1-2 seconds. Each verifier call typically checks
10-40 triples, so total verification is ~20-80 s/task — acceptable for batch
scoring. If we need speed later, swap in a persistent tunnel.

Results come back as TSV/pipe-delimited rows. Parsing is handled here so
callers get `list[tuple[str, ...]]`.
"""

from __future__ import annotations

import base64
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterable


SSH_HOST = os.environ.get("WESTD_SSH_HOST", "westd")
MAGENTO_CONTAINER = "webarena_shopping"
POSTMILL_CONTAINER = "webarena_reddit"
# Magento credentials pulled from /var/www/magento2/app/etc/env.php.
MAG_USER = "magentouser"
MAG_PASS = "MyPassword"
MAG_DB = "magentodb"
# Postmill uses peer auth via the `postgres` OS user.
PG_DB = "postmill"


@dataclass
class QueryResult:
    rows: list[tuple[str, ...]]
    raw: str
    returncode: int
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def scalar(self) -> str | None:
        if not self.rows:
            return None
        row = self.rows[0]
        if not row:
            return None
        return row[0]


def _run_ssh(remote_cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command on westd via ssh, capturing UTF-8 output.

    `remote_cmd` is passed as the *argument* to ssh — westd runs it in its
    default shell (cmd on Windows, which then dispatches to wsl).
    """
    full = ["ssh", SSH_HOST, remote_cmd]
    return subprocess.run(
        full,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


class DBRunner:
    """Run MySQL or PostgreSQL queries inside the sandbox containers."""

    def mysql(self, sql: str, *, timeout: int = 30) -> QueryResult:
        return self._run("mysql", sql, timeout=timeout, sep="\t")

    def postgres(self, sql: str, *, timeout: int = 30) -> QueryResult:
        return self._run("postgres", sql, timeout=timeout, sep="|")

    def _run(
        self,
        kind: str,
        sql: str,
        *,
        timeout: int,
        sep: str,
        retries: int = 2,
    ) -> QueryResult:
        """Ship SQL to westd via stdin → WSL bash runner script, with retry.

        Transient SSH disconnects on the vicp.fun tunnel are common under
        load; we retry twice with a short backoff. Non-SSH errors (bad SQL,
        etc) bubble up after the first attempt.
        """
        self._ensure_runner()
        full = [
            "ssh", SSH_HOST,
            f"wsl -d Ubuntu -- bash /mnt/c/tools/db_runner.sh {kind}",
        ]
        last: QueryResult | None = None
        for attempt in range(retries + 1):
            p = subprocess.run(
                full,
                input=sql,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            rows = self._parse_rows(p.stdout, sep=sep)
            last = QueryResult(
                rows=rows, raw=p.stdout,
                returncode=p.returncode, stderr=p.stderr,
            )
            # Transient SSH errors retry; everything else returns as-is.
            if last.ok or "Connection closed" not in last.stderr:
                return last
            if attempt < retries:
                import time
                time.sleep(0.8 * (attempt + 1))
        assert last is not None
        return last

    _runner_uploaded: bool = False

    @classmethod
    def _ensure_runner(cls) -> None:
        if cls._runner_uploaded:
            return
        script = (
            '#!/usr/bin/env bash\n'
            'set -e\n'
            'kind="$1"\n'
            'if [ "$kind" = "mysql" ]; then\n'
            f'  exec docker exec -i {MAGENTO_CONTAINER} '
            f'mysql -u {MAG_USER} -p{MAG_PASS} -s -N {MAG_DB}\n'
            'else\n'
            f'  exec docker exec -i {POSTMILL_CONTAINER} '
            f"su - postgres -c \"psql -d {PG_DB} -t -A -F '|'\"\n"
            'fi\n'
        )
        local_tmp = "/tmp/.db_runner_local.sh"
        with open(local_tmp, "w", encoding="utf-8") as f:
            f.write(script)
        # scp to Windows C:/tools/ (known writable from CLAUDE.md notes).
        r = subprocess.run(
            ["scp", local_tmp, f"{SSH_HOST}:C:/tools/db_runner.sh"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"scp of db_runner.sh failed: {r.stderr.strip()}"
            )
        # Strip CRLF (scp on Windows preserves LF already, but belt-and-suspenders).
        subprocess.run(
            ["ssh", SSH_HOST,
             "wsl -d Ubuntu -- bash -lc "
             "\"tr -d '\\r' < /mnt/c/tools/db_runner.sh > /tmp/db_runner.sh.tmp "
             "&& cp /tmp/db_runner.sh.tmp /mnt/c/tools/db_runner.sh\""],
            capture_output=True,
            timeout=30,
        )
        cls._runner_uploaded = True

    @staticmethod
    def _parse_rows(text: str, *, sep: str) -> list[tuple[str, ...]]:
        out: list[tuple[str, ...]] = []
        for line in text.splitlines():
            line = line.rstrip("\r").strip()
            if not line:
                continue
            out.append(tuple(line.split(sep)))
        return out


def probe_connectivity() -> dict[str, bool]:
    """Fast self-test: can we reach both DBs right now? Useful for CI skip."""
    r = DBRunner()
    m = r.mysql("SELECT 1", timeout=15)
    p = r.postgres("SELECT 1", timeout=15)
    return {
        "magento": m.ok and m.scalar() == "1",
        "postmill": p.ok and p.scalar() == "1",
    }
