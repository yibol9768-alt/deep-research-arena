"""Offline tests for the ``sql_query`` provider (src/rl/tools_sql.py).

Everything runs on system ``python3`` with NO MySQL / PostgreSQL: the connection
seam is fed an in-memory ``sqlite3`` connection seeded with a tiny products +
submissions schema, exercised through the SAME guard layer the production path
uses (the guards are dialect-agnostic string validation + a wrapping LIMIT). No
``sqlalchemy`` / ``psycopg2`` / ``mysql`` import anywhere in this test.

Coverage map:
  * provide_tools() yields a tool named ``sql_query`` importable without drivers.
  * GUARD ALLOWS a whitelisted SELECT: a top-N-by-price query returns rows and
    lands snippets keyed to the supplied page_url.
  * GUARD BLOCKS (distinct error codes, NO mutation):
      - a non-SELECT (DELETE)            -> sql_forbidden_keyword
      - a multi-statement injection      -> sql_multi_statement
      - a comment-hidden second stmt     -> sql_multi_statement
      - an off-allowlist table           -> sql_table_not_allowed
  * row_cap is honoured (more matching rows than the cap -> capped output).
  * ok=False sql_no_source_url when no page_url / page_urls resolvable.
  * the env folds the rendered rows so retrieved_snippets[canon(page_url)] set.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from src.rl.env import CallTool, MockSandboxBackend, ResearchEnv
from src.rl.tools import ToolContext, ToolResult, build_default_registry
from src.rl.tools_sql import (
    SqlGuardError,
    SqlQueryTool,
    provide_tools,
    render_rows,
    validate_select,
    wrap_with_row_cap,
)
from src.verifiers.citation_format import canonicalize_url


# --------------------------------------------------------------------------- #
# Fixtures: a magento-shaped product table + a postmill-shaped submissions table
# seeded into an in-memory sqlite connection. The page URLs are real sandbox
# PDP / forum URLs so grounding is honest and modality-agnostic.
# --------------------------------------------------------------------------- #
PDP_URL = "http://localhost:7770/novamax-pro.html"
FORUM_URL = "http://localhost:9999/f/headphones/novamax-thread"


def _seed_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    # Magento-shaped product table (a subset of catalog_product_entity columns).
    cur.execute(
        "CREATE TABLE catalog_product_entity ("
        " entity_id INTEGER PRIMARY KEY, sku TEXT, name TEXT, price REAL)"
    )
    cur.executemany(
        "INSERT INTO catalog_product_entity (entity_id, sku, name, price) VALUES (?,?,?,?)",
        [
            (1, "NMX-PRO", "NovaMax Pro", 299.0),
            (2, "NMX-LITE", "NovaMax Lite", 149.0),
            (3, "ACME-X", "Acme X", 89.0),
            (4, "ZED-1", "Zed One", 410.0),
            (5, "ORB-9", "Orb Nine", 199.0),
        ],
    )
    # Postmill-shaped submissions table.
    cur.execute(
        "CREATE TABLE submissions ("
        " id INTEGER PRIMARY KEY, title TEXT, forum TEXT, score INTEGER)"
    )
    cur.executemany(
        "INSERT INTO submissions (id, title, forum, score) VALUES (?,?,?,?)",
        [
            (1, "NovaMax Pro long-term review", "headphones", 342),
            (2, "Heat buildup on NovaMax Pro?", "headphones", 88),
        ],
    )
    # An off-allowlist secrets table to prove the table guard blocks it even when
    # the data physically exists.
    cur.execute("CREATE TABLE secrets (id INTEGER PRIMARY KEY, token TEXT)")
    cur.execute("INSERT INTO secrets (id, token) VALUES (1, 'topsecret')")
    conn.commit()
    return conn


def _ctx(conn: sqlite3.Connection, *, extras: dict[str, Any] | None = None) -> ToolContext:
    base = {"sql_engines": {"magento": conn, "postmill": conn}}
    if extras:
        base.update(extras)
    return ToolContext(
        backend=None,
        task_config={"task_id": "sql_test"},
        extras=base,
    )


# =========================================================================== #
# Provider-discovery contract.
# =========================================================================== #
def test_provide_tools_yields_sql_query_without_drivers() -> None:
    tools = provide_tools()
    assert len(tools) == 1
    assert tools[0].name == "sql_query"
    # And it is discovered into the full registry.
    assert build_default_registry().has("sql_query")


# =========================================================================== #
# GUARD ALLOWS a whitelisted SELECT; lands snippets keyed to the page_url.
# =========================================================================== #
def test_allows_whitelisted_select_and_lands_snippet() -> None:
    conn = _seed_sqlite()
    ctx = _ctx(conn)
    result = SqlQueryTool().run(
        ctx,
        {
            "sql": "SELECT name, price FROM catalog_product_entity ORDER BY price DESC",
            "db": "magento",
            "page_url": PDP_URL,
        },
    )
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.n_results == 5
    # Rendered rows landed keyed to the supplied PDP url -> Cite(PDP_URL) resolves.
    assert set(result.snippets.keys()) == {PDP_URL}
    assert result.fetched_urls == [PDP_URL]
    rendered = result.snippets[PDP_URL]
    assert "columns: name, price" in rendered
    # Highest price first (ORDER BY price DESC).
    assert "name: Zed One | price: 410.0" in rendered
    assert "NovaMax Pro" in rendered


def test_select_with_explicit_page_urls_list_lands_all() -> None:
    conn = _seed_sqlite()
    ctx = _ctx(conn)
    result = SqlQueryTool().run(
        ctx,
        {
            "sql": "SELECT title, score FROM submissions WHERE forum = 'headphones'",
            "db": "postmill",
            "page_urls": [FORUM_URL, PDP_URL],
        },
    )
    assert result.ok is True
    # Rendered rows landed against EVERY supplied source page.
    assert set(result.snippets.keys()) == {FORUM_URL, PDP_URL}
    assert result.snippets[FORUM_URL] == result.snippets[PDP_URL]
    assert "NovaMax Pro long-term review" in result.snippets[FORUM_URL]


# =========================================================================== #
# GUARD BLOCKS: distinct error codes, NO mutation.
# =========================================================================== #
def test_blocks_non_select_delete() -> None:
    conn = _seed_sqlite()
    result = SqlQueryTool().run(
        _ctx(conn),
        {"sql": "DELETE FROM catalog_product_entity", "db": "magento", "page_url": PDP_URL},
    )
    assert result.ok is False
    # A DELETE does not lead with SELECT/WITH, so the leading-keyword guard fires
    # first (the forbidden-keyword scan is the backstop for DML hidden INSIDE a
    # SELECT-leading query).
    assert result.error in {"sql_not_select", "sql_forbidden_keyword"}
    # NO mutation: the row is still there.
    n = conn.execute("SELECT COUNT(*) FROM catalog_product_entity").fetchone()[0]
    assert n == 5


def test_blocks_forbidden_keyword_inside_select_leading_query() -> None:
    # DML smuggled INSIDE a SELECT-leading statement is caught by the
    # forbidden-keyword scan, not the leading-keyword check.
    conn = _seed_sqlite()
    result = SqlQueryTool().run(
        _ctx(conn),
        {
            "sql": "SELECT name FROM catalog_product_entity WHERE 1=1 INTO OUTFILE '/tmp/x'",
            "db": "magento",
            "page_url": PDP_URL,
        },
    )
    assert result.ok is False
    assert result.error == "sql_forbidden_keyword"


def test_blocks_non_select_update() -> None:
    conn = _seed_sqlite()
    result = SqlQueryTool().run(
        _ctx(conn),
        {"sql": "UPDATE catalog_product_entity SET price = 0", "db": "magento", "page_url": PDP_URL},
    )
    assert result.ok is False
    assert result.error in {"sql_not_select", "sql_forbidden_keyword"}
    # NO mutation.
    prices = [r[0] for r in conn.execute("SELECT price FROM catalog_product_entity").fetchall()]
    assert 0 not in prices


def test_blocks_multi_statement() -> None:
    conn = _seed_sqlite()
    result = SqlQueryTool().run(
        _ctx(conn),
        {
            "sql": "SELECT 1 FROM catalog_product_entity; DROP TABLE catalog_product_entity",
            "db": "magento",
            "page_url": PDP_URL,
        },
    )
    assert result.ok is False
    assert result.error == "sql_multi_statement"
    # NO mutation: table survives.
    n = conn.execute("SELECT COUNT(*) FROM catalog_product_entity").fetchone()[0]
    assert n == 5


def test_blocks_comment_hidden_second_statement() -> None:
    conn = _seed_sqlite()
    # A classic injection: a line comment trying to smuggle a second statement.
    result = SqlQueryTool().run(
        _ctx(conn),
        {
            "sql": "SELECT name FROM catalog_product_entity -- harmless\n; DROP TABLE secrets",
            "db": "magento",
            "page_url": PDP_URL,
        },
    )
    assert result.ok is False
    assert result.error == "sql_multi_statement"
    assert conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0] == 1


def test_blocks_off_allowlist_table() -> None:
    conn = _seed_sqlite()
    result = SqlQueryTool().run(
        _ctx(conn),
        {"sql": "SELECT token FROM secrets", "db": "magento", "page_url": PDP_URL},
    )
    assert result.ok is False
    assert result.error == "sql_table_not_allowed"
    assert result.snippets == {}
    assert result.fetched_urls == []


def test_blocks_off_allowlist_column_on_restricted_table() -> None:
    # ``users`` is allow-listed but only for {id, username, created_at}; a
    # password_hash column is rejected by the column gate (postmill db).
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)"
    )
    conn.execute("INSERT INTO users VALUES (1, 'jane', 'deadbeef')")
    conn.commit()
    ctx = _ctx(conn)
    result = SqlQueryTool().run(
        ctx,
        {"sql": "SELECT users.password_hash FROM users", "db": "postmill", "page_url": FORUM_URL},
    )
    assert result.ok is False
    assert result.error == "sql_column_not_allowed"
    # And SELECT * on a restricted table is also blocked.
    result_star = SqlQueryTool().run(
        ctx,
        {"sql": "SELECT * FROM users", "db": "postmill", "page_url": FORUM_URL},
    )
    assert result_star.ok is False
    assert result_star.error == "sql_column_not_allowed"


# =========================================================================== #
# row_cap honoured.
# =========================================================================== #
def test_row_cap_honoured() -> None:
    conn = _seed_sqlite()
    ctx = _ctx(conn, extras={"sql_row_cap": 2})
    result = SqlQueryTool().run(
        ctx,
        {"sql": "SELECT name FROM catalog_product_entity ORDER BY price DESC", "db": "magento", "page_url": PDP_URL},
    )
    assert result.ok is True
    # Five rows match but the cap is 2 -> exactly two data rows landed.
    assert result.n_results == 2
    body_lines = [ln for ln in result.snippets[PDP_URL].splitlines() if ln.startswith("name:")]
    assert len(body_lines) == 2


# =========================================================================== #
# No source url -> refuse to land orphan evidence.
# =========================================================================== #
def test_no_source_url_is_refused() -> None:
    conn = _seed_sqlite()
    result = SqlQueryTool().run(
        _ctx(conn),
        {"sql": "SELECT name FROM catalog_product_entity", "db": "magento"},
    )
    assert result.ok is False
    assert result.error == "sql_no_source_url"
    assert result.snippets == {}


def test_per_table_fallback_page_url_map() -> None:
    # When the agent omits page_url, a configured per-table map resolves it.
    conn = _seed_sqlite()
    ctx = _ctx(conn, extras={"sql_page_urls": {"catalog_product_entity": PDP_URL}})
    result = SqlQueryTool().run(
        ctx,
        {"sql": "SELECT name FROM catalog_product_entity", "db": "magento"},
    )
    assert result.ok is True
    assert PDP_URL in result.snippets


def test_empty_sql_is_graceful() -> None:
    conn = _seed_sqlite()
    result = SqlQueryTool().run(_ctx(conn), {"sql": "   ", "page_url": PDP_URL})
    assert result.ok is False
    assert result.error == "sql_empty"


def test_db_unavailable_is_graceful() -> None:
    # No engine configured for the requested db -> graceful ok=False, no crash.
    ctx = ToolContext(backend=None, task_config={}, extras={"sql_engines": {}})
    result = SqlQueryTool().run(
        ctx, {"sql": "SELECT name FROM catalog_product_entity", "db": "magento", "page_url": PDP_URL}
    )
    assert result.ok is False
    assert result.error == "sql_db_unavailable"


# =========================================================================== #
# Unit-level guard assertions (the pure validation layer).
# =========================================================================== #
def test_validate_select_accepts_cte() -> None:
    meta = validate_select(
        "WITH t AS (SELECT price FROM catalog_product_entity) SELECT price FROM t",
        db="magento",
    )
    assert meta["leading"] == "WITH"


def test_validate_select_rejects_codes() -> None:
    cases = {
        "": "sql_empty",
        # Non-SELECT-leading statements are caught by the leading-keyword guard.
        "DROP TABLE catalog_product_entity": "sql_not_select",
        "INSERT INTO catalog_product_entity VALUES (9)": "sql_not_select",
        # DML smuggled inside a SELECT-leading query -> forbidden-keyword scan.
        "SELECT name FROM catalog_product_entity INTO OUTFILE '/tmp/x'": "sql_forbidden_keyword",
        "SELECT 1; SELECT 2": "sql_multi_statement",
        "SELECT * FROM secrets": "sql_table_not_allowed",
    }
    for sql, code in cases.items():
        try:
            validate_select(sql, db="magento")
        except SqlGuardError as exc:
            assert exc.code == code, f"{sql!r} -> {exc.code} (expected {code})"
        else:
            raise AssertionError(f"{sql!r} should have raised {code}")


def test_wrap_with_row_cap_clamps_to_hard_ceiling() -> None:
    wrapped = wrap_with_row_cap("SELECT 1 FROM catalog_product_entity", 10_000)
    assert "LIMIT 500" in wrapped  # hard ceiling
    assert "_sql_guard_t" in wrapped


def test_render_rows_is_deterministic() -> None:
    txt = render_rows(["a", "b"], [(1, None), (2, "x")], row_cap=50)
    assert txt == "columns: a, b\na: 1 | b: NULL\na: 2 | b: x"


# =========================================================================== #
# The env folds the rendered rows into retrieved_snippets (modality parity).
# =========================================================================== #
def test_env_folds_sql_rows_into_grounding() -> None:
    conn = _seed_sqlite()
    cfg = {
        "task_id": "sql_env_test",
        "intent": "top product by price",
        "acquisition": {"tools_allowed": ["search", "fetch", "sql_query"]},
        "sandbox_hosts": ["localhost:7770", "localhost:9999"],
    }
    env = ResearchEnv(cfg, MockSandboxBackend({}, {}), max_tool_calls=10)

    # Inject the sqlite engine into the env's tool context via the extras seam.
    base_tool_ctx = env._tool_ctx

    def _patched_ctx() -> ToolContext:
        ctx = base_tool_ctx()
        ctx.extras["sql_engines"] = {"magento": conn, "postmill": conn}
        return ctx

    env._tool_ctx = _patched_ctx  # type: ignore[method-assign]
    env.reset()
    env._tool_ctx = _patched_ctx  # type: ignore[method-assign]

    obs, done, info = env.step(
        CallTool(
            "sql_query",
            {
                "sql": "SELECT name, price FROM catalog_product_entity ORDER BY price DESC",
                "db": "magento",
                "page_url": PDP_URL,
            },
        )
    )
    assert done is False
    assert info["ok"] is True
    assert info["tool"] == "sql_query"
    # Folded into the SAME grounding store a fetch writes -> reward-creditable.
    assert PDP_URL in obs["fetched_urls"]
    assert canonicalize_url(PDP_URL) in obs["retrieved_snippets"]
    assert "NovaMax Pro" in obs["retrieved_snippets"][canonicalize_url(PDP_URL)]
