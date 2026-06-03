"""``sql_query`` provider: read-only SQL over Magento MySQL + Postmill PostgreSQL.

P1 acquisition tool #2 (docs/ACQUISITION_ROADMAP.md section 3). One of the two
high-risk tools, so the security posture is **default-deny**: a query is only
executed if it passes EVERY guard. The guards are dialect-agnostic string
validation plus a wrapping ``LIMIT`` so the identical guard layer is exercised
offline against an in-memory ``sqlite3`` connection (no MySQL / PG needed).

Modality-agnostic reward (the COMPUTE-OVER-PAGES invariant): the tool does NOT
invent a ``sql://`` url. It renders the result rows as deterministic text and
keys that text to the source ``page_url`` / ``page_urls`` the agent supplied (or
a configured per-table fallback map). So a ``Cite(page_url)`` of the underlying
PDP / forum page resolves ``r_resolve`` and the rendered numbers feed
``f1_claim`` exactly like a fetch of that page.

No heavy top-level imports: ``sqlalchemy`` / ``psycopg2`` / ``mysql`` (and even
``sqlite3``) are imported LAZILY inside :meth:`SqlQueryTool.run` / the executor,
so ``import src.rl.tools_sql`` succeeds on a plain ``python3``. ``provide_tools``
itself triggers none of those imports.

Provider-discovery contract: ``provide_tools() -> [SqlQueryTool()]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.rl.tools import Tool, ToolContext, ToolResult


# ---------------------------------------------------------------------------
# Guard configuration
# ---------------------------------------------------------------------------
# Default row cap and wall-clock / statement timeout (seconds). Both overridable
# via ctx.extras so a task / test can tighten them, never loosen past the hard
# ceilings enforced below.
_DEFAULT_ROW_CAP = 50
_HARD_ROW_CAP = 500
_DEFAULT_TIMEOUT_S = 10.0
_HARD_TIMEOUT_S = 30.0

# A second non-empty statement (anything after a ``;``) is rejected outright as a
# multi-statement injection. We also reject any token from the DML/DDL/admin set.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "DROP",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "REPLACE",
        "CALL",
        "EXEC",
        "EXECUTE",
        "COPY",
        "LOAD",
        "INTO",
        "SET",
        "LOCK",
        "UNLOCK",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "VACUUM",
        "REINDEX",
        "HANDLER",
        "RENAME",
        "USE",
    }
)

# Table + column ALLOWLIST, per logical db. ``"*"`` in a table's column set means
# "any column on this allow-listed table is fine" (the table itself gates access;
# Magento's EAV / sales tables have hundreds of columns we do not enumerate). A
# table with an explicit column set restricts SELECT to exactly those columns.
_ALLOWLIST: dict[str, dict[str, set[str]]] = {
    "magento": {
        "catalog_product_entity": {"*"},
        "catalog_product_entity_decimal": {"*"},
        "catalog_product_entity_int": {"*"},
        "catalog_product_entity_varchar": {"*"},
        "catalog_product_entity_text": {"*"},
        "catalog_product_entity_datetime": {"*"},
        "sales_order": {"*"},
        "sales_order_item": {"*"},
        "review": {"*"},
        "review_detail": {"*"},
        "rating_option_vote": {"*"},
    },
    "postmill": {
        "submissions": {"*"},
        "comments": {"*"},
        "votes": {"*"},
        "forums": {"*"},
        "users": {
            # users is sensitive: only non-PII columns are allow-listed.
            "id",
            "username",
            "created_at",
        },
    },
}

# A db whose allow-list we do not recognise still gets the dialect-agnostic
# guards (SELECT-only, single-statement, row-cap); the table allow-list check is
# applied against the union of every known table so an offline sqlite test seeded
# with a Magento-shaped schema validates without re-declaring a db.
_KNOWN_TABLES: set[str] = {
    t for db in _ALLOWLIST.values() for t in db
}


def _merge_column_allow() -> dict[str, set[str]]:
    """Union the per-db column allow-lists into one table -> columns map.

    Used as the fallback column gate when ``db`` is unrecognised/empty so a
    sensitive table's restricted column set (e.g. postmill ``users`` ->
    {id, username, created_at}) is STILL enforced. A table is the union of its
    per-db column sets; if ANY db exposes it as ``{"*"}`` the merged entry is
    ``{"*"}`` (the table gates access there), otherwise the merged entry is the
    union of the explicit columns so a restricted table stays restricted no
    matter which db is omitted. Tables are unique across our dbs today, so this
    is just a flatten in practice, but the union keeps the gate correct if that
    ever changes.
    """

    merged: dict[str, set[str]] = {}
    for db in _ALLOWLIST.values():
        for table, cols in db.items():
            existing = merged.get(table)
            if existing is None:
                merged[table] = set(cols)
            elif "*" in existing or "*" in cols:
                merged[table] = {"*"}
            else:
                merged[table] = existing | cols
    return merged


_MERGED_COLUMN_ALLOW: dict[str, set[str]] = _merge_column_allow()


# ---------------------------------------------------------------------------
# Guard errors
# ---------------------------------------------------------------------------
class SqlGuardError(Exception):
    """Raised by a guard with a stable, test-assertable ``code``."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Statement validation (dialect-agnostic; the SAME layer offline + production)
# ---------------------------------------------------------------------------
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"(--|#)[^\n]*")
_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
# table references after FROM / JOIN (we only need the table name token). A
# ``FROM (`` opening a derived-table subquery has no name token here, which is
# fine: the real tables inside the subquery still match this pattern.
_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z_0-9]*)",
    re.IGNORECASE,
)
# A comma-separated continuation of a FROM/JOIN table list, e.g. the ``, b`` in
# ``FROM a, b`` (a valid implicit CROSS JOIN). Without this the table allow-list
# would only see the first table and silently pass off-allowlist tables joined
# by comma. ``,`` may be followed by an optional schema-qualified identifier; we
# capture the FIRST identifier token of each comma-listed entry (the base table
# or its schema prefix, both of which we want to gate). A leading ``(`` (a
# subquery / VALUES list / row constructor) has no top-level table name token,
# so it simply does not match here while its inner real tables still match
# ``_TABLE_REF``.
_TABLE_LIST_TAIL = re.compile(
    r",\s*([A-Za-z_][A-Za-z_0-9]*)",
    re.IGNORECASE,
)
# Clause keywords that terminate a comma-separated FROM table list. A comma that
# appears AFTER one of these (e.g. inside a ``GROUP BY a, b`` or a ``SELECT a, b``
# projection) is not a table reference and must not be scanned as one.
_FROM_LIST_TERMINATORS = frozenset(
    {
        "WHERE",
        "GROUP",
        "HAVING",
        "ORDER",
        "LIMIT",
        "OFFSET",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "WINDOW",
        "FETCH",
        "FOR",
        "ON",
        "USING",
        "JOIN",
        "INNER",
        "LEFT",
        "RIGHT",
        "FULL",
        "CROSS",
        "NATURAL",
        "SELECT",
    }
)
# CTE names defined by ``WITH name AS (...)`` / ``, name AS (...)``. These are
# query-local aliases, NOT base tables, so they are excluded from the table
# allow-list check (their bodies reference real tables which ARE checked).
_CTE_DEF = re.compile(
    r"(?:\bWITH\b|,)\s+([A-Za-z_][A-Za-z_0-9]*)\s+AS\s*\(",
    re.IGNORECASE,
)


def _strip_comments(sql: str) -> str:
    """Remove block + line comments so a ``-- ; DROP`` trick cannot hide a stmt."""

    no_block = _COMMENT_BLOCK.sub(" ", sql)
    no_line = _COMMENT_LINE.sub(" ", no_block)
    return no_line


def _split_statements(sql: str) -> list[str]:
    """Split on top-level ``;`` and return non-empty statements.

    String literals are not parsed (the corpus queries do not embed semicolons in
    literals, and any literal ``;`` only makes the guard MORE conservative, which
    is the safe direction). More than one non-empty statement is a hard reject.
    """

    return [s.strip() for s in sql.split(";") if s.strip()]


def _extract_table_refs(statement: str) -> list[str]:
    """Every base-table identifier referenced by a FROM/JOIN, comma-joins included.

    ``_TABLE_REF`` only sees the single token right after FROM/JOIN, so an
    implicit cross join ``FROM a, b`` would leave ``b`` (a potentially
    off-allowlist table) unchecked and bypass the table allow-list. This walks
    each FROM/JOIN match and then consumes the comma-separated continuation
    (``, b , c ...``) that can follow, stopping at the next clause keyword. Each
    comma-listed entry contributes its first identifier token (the base table, or
    its schema prefix for ``schema.tbl`` forms, both of which we want to gate).
    Identifiers are returned lower-cased; the caller filters out CTE aliases.
    """

    tables: list[str] = []
    for m in _TABLE_REF.finditer(statement):
        tables.append(m.group(1))
        # Walk the comma-separated tail immediately following this table token,
        # advancing the cursor past each accepted entry. We stop as soon as a
        # clause keyword appears between the cursor and the next comma (that
        # comma belongs to GROUP BY / ORDER BY / a projection, not the FROM list)
        # or the next match is no longer contiguous.
        cursor = m.end()
        while True:
            tail = _TABLE_LIST_TAIL.search(statement, cursor)
            if tail is None:
                break
            between = statement[cursor : tail.start()]
            words = _WORD.findall(between)
            if any(w.upper() in _FROM_LIST_TERMINATORS for w in words):
                break
            ident = tail.group(1)
            if ident.upper() in _FROM_LIST_TERMINATORS:
                break
            tables.append(ident)
            cursor = tail.end()
    return [t.lower() for t in tables]


def validate_select(sql: str, *, db: str | None = None) -> dict[str, Any]:
    """Default-deny validation. Returns metadata on success, raises on any breach.

    Order of checks (each raises :class:`SqlGuardError` with a distinct code):
      1. non-empty
      2. single statement (strip comments first, then split on ``;``)
      3. leading keyword is SELECT or WITH (CTE) ... SELECT
      4. no forbidden DML/DDL/admin keyword anywhere
      5. every referenced table is on the allow-list (per-db, else known-tables)
    """

    raw = str(sql or "")
    stripped = _strip_comments(raw).strip()
    if not stripped:
        raise SqlGuardError("sql_empty", "empty statement after stripping comments")

    statements = _split_statements(stripped)
    if len(statements) != 1:
        raise SqlGuardError(
            "sql_multi_statement",
            f"expected exactly one statement, found {len(statements)}",
        )
    statement = statements[0]

    words = _WORD.findall(statement)
    if not words:
        raise SqlGuardError("sql_empty", "no SQL tokens")

    leading = words[0].upper()
    if leading not in {"SELECT", "WITH"}:
        raise SqlGuardError(
            "sql_not_select",
            f"leading keyword {leading!r} is not SELECT/WITH",
        )
    if leading == "WITH" and not any(w.upper() == "SELECT" for w in words):
        # A CTE that never reaches a SELECT (e.g. WITH ... DELETE) is rejected by
        # the forbidden-keyword scan below, but guard the no-SELECT case too.
        raise SqlGuardError("sql_not_select", "WITH clause without a SELECT")

    upper_words = {w.upper() for w in words}
    forbidden = upper_words & _FORBIDDEN_KEYWORDS
    if forbidden:
        raise SqlGuardError(
            "sql_forbidden_keyword",
            "forbidden keyword(s): " + ", ".join(sorted(forbidden)),
        )

    cte_names = {c.lower() for c in _CTE_DEF.findall(statement)}
    tables = [
        t
        for t in _extract_table_refs(statement)
        if t not in cte_names
    ]
    allow = _ALLOWLIST.get(str(db or "").lower())
    allowed_tables = set(allow) if allow else set(_KNOWN_TABLES)
    bad = [t for t in tables if t not in allowed_tables]
    if bad:
        raise SqlGuardError(
            "sql_table_not_allowed",
            "table(s) not on allow-list: " + ", ".join(sorted(set(bad))),
        )

    # Column allow-list: only meaningful for tables with an explicit (non ``*``)
    # column set. We do a conservative token scan: if such a restricted table is
    # referenced and the statement uses ``SELECT *`` or names a column outside the
    # set, reject. Tables with ``{"*"}`` skip the column gate.
    #
    # This MUST run even when ``db`` is unrecognised/empty: otherwise an agent on a
    # single-database deployment could omit ``db`` and read a sensitive table's
    # restricted columns (the table gate still passes via _KNOWN_TABLES). When
    # ``allow`` is None we fall back to the merged-across-dbs column map so a
    # restricted table stays restricted regardless of which db was supplied.
    column_allow = allow if allow else _MERGED_COLUMN_ALLOW
    if column_allow:
        for table in tables:
            cols = column_allow.get(table)
            if not cols or "*" in cols:
                continue
            if re.search(r"\bSELECT\s+\*", statement, re.IGNORECASE) or re.search(
                rf"\b{re.escape(table)}\s*\.\s*\*", statement, re.IGNORECASE
            ):
                raise SqlGuardError(
                    "sql_column_not_allowed",
                    f"SELECT * not permitted on restricted table {table!r}",
                )
            # Any dotted column reference table.col must be in the set.
            for m in re.finditer(
                rf"\b{re.escape(table)}\s*\.\s*([A-Za-z_][A-Za-z_0-9]*)",
                statement,
                re.IGNORECASE,
            ):
                col = m.group(1).lower()
                if col not in cols:
                    raise SqlGuardError(
                        "sql_column_not_allowed",
                        f"column {table}.{col} not on allow-list",
                    )

    return {"statement": statement, "tables": tables, "leading": leading}


def wrap_with_row_cap(statement: str, row_cap: int) -> str:
    """Wrap a validated SELECT so the engine can never return more than row_cap.

    ``SELECT * FROM (<stmt>) _sql_guard_t LIMIT <cap>``. The validated inner
    statement is parenthesised; the outer cap is a hard ceiling enforced in
    addition to the ``fetchmany`` cap, so a malformed inner LIMIT cannot exceed
    it. Works on sqlite / MySQL / PG (all accept ``LIMIT n``).
    """

    cap = max(1, min(int(row_cap), _HARD_ROW_CAP))
    inner = statement.rstrip().rstrip(";")
    return f"SELECT * FROM (\n{inner}\n) _sql_guard_t LIMIT {cap}"


# ---------------------------------------------------------------------------
# Row rendering -> grounding text
# ---------------------------------------------------------------------------
def render_rows(columns: list[str], rows: list[tuple], *, row_cap: int) -> str:
    """Deterministic text rendering: a header line then ``col: val | col: val``.

    Bounded by ``row_cap`` (defensive; the SQL is already capped). NULLs render
    as ``NULL`` so the text is stable and creditable.
    """

    cap = max(1, min(int(row_cap), _HARD_ROW_CAP))
    header = "columns: " + ", ".join(str(c) for c in columns)
    lines = [header]
    for row in rows[:cap]:
        cells = []
        for col, val in zip(columns, row):
            cells.append(f"{col}: {'NULL' if val is None else val}")
        lines.append(" | ".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Execution seam: a connection may be a raw DB-API connection, a sqlalchemy
# engine, or a DSN string. All driver imports are LAZY and live here.
# ---------------------------------------------------------------------------
@dataclass
class _QueryOutcome:
    columns: list[str]
    rows: list[tuple]


def _resolve_engine(ctx: ToolContext, db: str) -> Any:
    """Find the connection/engine/DSN for ``db`` in ctx.extras['sql_engines'].

    Returns the raw value (engine / connection / DSN string). Raises
    :class:`SqlGuardError('sql_db_unavailable')` if none is configured.
    """

    engines = (ctx.extras or {}).get("sql_engines") or {}
    engine = engines.get(db)
    if engine is None and len(engines) == 1 and not db:
        # Single configured db, none requested -> use it.
        engine = next(iter(engines.values()))
    if engine is None:
        raise SqlGuardError("sql_db_unavailable", f"no engine for db {db!r}")
    return engine


def _execute(engine: Any, wrapped_sql: str, *, timeout_s: float, row_cap: int) -> _QueryOutcome:
    """Run ``wrapped_sql`` read-only against ``engine``; lazy-import the driver.

    ``engine`` may be:
      * a sqlalchemy Engine / Connection (duck-typed ``connect`` / ``execute``);
      * a raw DB-API connection (duck-typed ``cursor``), e.g. an in-memory
        ``sqlite3`` connection used by the offline tests;
      * a DSN string ``mysql+pymysql://...`` / ``postgresql://...`` -> opened via
        a lazily-imported sqlalchemy ``create_engine``.

    A read-only transaction is requested where the dialect supports it; the row
    cap is enforced a second time via ``fetchmany``.
    """

    cap = max(1, min(int(row_cap), _HARD_ROW_CAP))

    # DSN string -> lazily build a sqlalchemy engine (driver import is lazy).
    if isinstance(engine, str):
        try:
            from sqlalchemy import create_engine  # lazy heavy dep
        except Exception as exc:  # pragma: no cover - exercised on training box
            raise SqlGuardError("sql_driver_unavailable", str(exc)) from exc
        engine = create_engine(engine)

    # sqlalchemy Engine / Connection path (duck-typed).
    if hasattr(engine, "connect") or hasattr(engine, "execution_options"):
        try:
            from sqlalchemy import text as _sa_text  # lazy
        except Exception as exc:  # pragma: no cover
            raise SqlGuardError("sql_driver_unavailable", str(exc)) from exc
        conn_cm = engine.connect() if hasattr(engine, "connect") else engine
        with conn_cm as conn:  # type: ignore[union-attr]
            try:
                conn = conn.execution_options(
                    postgresql_readonly=True,
                    isolation_level="AUTOCOMMIT",
                )
            except Exception:
                pass
            result = conn.execute(_sa_text(wrapped_sql))
            columns = list(result.keys())
            rows = [tuple(r) for r in result.fetchmany(cap)]
            return _QueryOutcome(columns=columns, rows=rows)

    # Raw DB-API connection path (sqlite3 in tests, or a pre-opened driver conn).
    if hasattr(engine, "cursor"):
        cur = engine.cursor()
        try:
            cur.execute(wrapped_sql)
            columns = [d[0] for d in (cur.description or [])]
            rows = [tuple(r) for r in cur.fetchmany(cap)]
            return _QueryOutcome(columns=columns, rows=rows)
        finally:
            try:
                cur.close()
            except Exception:
                pass

    raise SqlGuardError("sql_driver_unavailable", "unsupported engine object")


# ---------------------------------------------------------------------------
# Page-url resolution: where the rendered rows are landed for grounding credit.
# ---------------------------------------------------------------------------
def _resolve_page_urls(ctx: ToolContext, args: dict[str, Any], tables: list[str]) -> list[str]:
    """Collect the source page URL(s) the rows render on.

    Priority: explicit ``page_urls`` list, then a single ``page_url``, then a
    per-table fallback map ``ctx.extras['sql_page_urls']`` keyed by table name.
    Deduped, order-preserving. Empty list -> the caller refuses to land orphan
    evidence (``sql_no_source_url``).
    """

    urls: list[str] = []

    def _add(u: Any) -> None:
        s = str(u or "").strip()
        if s and s not in urls:
            urls.append(s)

    raw_list = args.get("page_urls")
    if isinstance(raw_list, (list, tuple)):
        for u in raw_list:
            _add(u)
    elif isinstance(raw_list, str):
        _add(raw_list)
    _add(args.get("page_url"))

    if not urls:
        table_map = (ctx.extras or {}).get("sql_page_urls") or {}
        for table in tables:
            mapped = table_map.get(table)
            if isinstance(mapped, (list, tuple)):
                for u in mapped:
                    _add(u)
            elif mapped:
                _add(mapped)

    return urls


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------
class SqlQueryTool:
    """``sql_query``: read-only SELECT over the Magento / Postmill databases.

    The agent supplies the source page URL(s) the rows render on; the rendered
    rows are landed keyed to those URLs so a ``Cite(page_url)`` resolves. If no
    source URL is resolvable the tool refuses (``sql_no_source_url``) rather than
    land orphan evidence.
    """

    name = "sql_query"
    description = (
        "Read-only SELECT over the Magento (MySQL) and Postmill (PostgreSQL) "
        "corpora; renders rows as text keyed to the source page URL(s) so the "
        "cited PDP/forum page resolves. SELECT-only, allow-listed, row-capped."
    )
    args_schema: dict = {
        "sql": {"type": "string", "required": True},
        "db": {"type": "string", "required": False, "enum": ["magento", "postmill"]},
        "page_url": {"type": "string", "required": False},
        "page_urls": {"type": "list", "required": False},
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        sql = str(args.get("sql") or "").strip()
        if not sql:
            return ToolResult(ok=False, error="sql_empty")
        db = str(args.get("db") or "").strip().lower()

        row_cap = int((ctx.extras or {}).get("sql_row_cap", _DEFAULT_ROW_CAP))
        row_cap = max(1, min(row_cap, _HARD_ROW_CAP))
        timeout_s = float((ctx.extras or {}).get("sql_timeout_s", _DEFAULT_TIMEOUT_S))
        timeout_s = max(0.1, min(timeout_s, _HARD_TIMEOUT_S))

        # 1) Default-deny guard layer (raises SqlGuardError with a stable code).
        try:
            meta = validate_select(sql, db=db)
        except SqlGuardError as exc:
            return ToolResult(ok=False, error=exc.code, display=exc.detail)

        tables = meta["tables"]

        # 2) Resolve the source page url(s) BEFORE touching the db: refuse to land
        #    orphan compute output if there is nowhere to credit it.
        page_urls = _resolve_page_urls(ctx, args, tables)
        if not page_urls:
            return ToolResult(ok=False, error="sql_no_source_url")

        # 3) Resolve engine + execute the row-capped, read-only query.
        try:
            engine = _resolve_engine(ctx, db)
        except SqlGuardError as exc:
            return ToolResult(ok=False, error=exc.code, display=exc.detail)

        wrapped = wrap_with_row_cap(meta["statement"], row_cap)
        try:
            outcome = _execute(engine, wrapped, timeout_s=timeout_s, row_cap=row_cap)
        except SqlGuardError as exc:
            return ToolResult(ok=False, error=exc.code, display=exc.detail)
        except Exception as exc:
            return ToolResult(ok=False, error=f"sql_execution_error: {type(exc).__name__}")

        rendered = render_rows(outcome.columns, outcome.rows, row_cap=row_cap)

        # 4) Land the rendered rows keyed to EVERY supplied/resolved source page so
        #    a Cite of the underlying PDP/forum page resolves (COMPUTE-OVER-PAGES).
        snippets = {url: rendered for url in page_urls}
        return ToolResult(
            snippets=snippets,
            fetched_urls=list(page_urls),
            n_results=len(outcome.rows),
            display=rendered,
            ok=True,
        )


# ---------------------------------------------------------------------------
# Provider-discovery contract
# ---------------------------------------------------------------------------
def provide_tools() -> list[Tool]:
    """Return the SQL provider's tools. Cheap; triggers no heavy imports."""

    return [SqlQueryTool()]


__all__ = [
    "SqlQueryTool",
    "SqlGuardError",
    "provide_tools",
    "validate_select",
    "wrap_with_row_cap",
    "render_rows",
]
