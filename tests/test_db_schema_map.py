"""Tests for the predicate -> SQL template map (src.golden.db_schema_map).

Focus: _mag_name_match must escape MySQL LIKE metacharacters ('%', '_')
and backslash so a literal product name is matched as a literal prefix and
not as a wildcard pattern. Widening the match set risks resolving the wrong
entity_id under the LIMIT-1 (no ORDER BY) inner query.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.golden.db_schema_map import (
    _mag_name_match,
    _mag_price,
    PREDICATES,
    site_of,
)


def test_underscore_is_escaped_as_literal():
    sql = _mag_name_match("Foo_Bar Product")
    # The underscore must be escaped so it does not match any single char.
    assert "Foo\\_Bar Product%" in sql
    # Raw, unescaped underscore prefix must NOT appear in the pattern.
    assert "'Foo_Bar Product%'" not in sql
    assert "ESCAPE '\\\\'" in sql


def test_percent_is_escaped_as_literal():
    sql = _mag_name_match("50% Cotton Shirt")
    # The percent must be escaped so it does not match an arbitrary substring.
    assert "50\\% Cotton Shirt%" in sql
    assert "'50% Cotton Shirt%'" not in sql
    assert "ESCAPE '\\\\'" in sql


def test_single_quote_still_doubled():
    sql = _mag_name_match("O'Brien Special")
    assert "O''Brien Special%" in sql


def test_backslash_is_escaped():
    sql = _mag_name_match("Back\\Slash Item")
    # A literal backslash in the name becomes a doubled backslash in the
    # pattern so it is treated as data, not as the ESCAPE character.
    assert "Back\\\\Slash Item%" in sql


def test_plain_name_unchanged_prefix():
    sql = _mag_name_match("Normal Product Name")
    assert "LIKE 'Normal Product Name%' ESCAPE '\\\\' LIMIT 1" in sql


def test_prefix_truncated_to_60_chars():
    name = "X" * 100
    sql = _mag_name_match(name)
    assert ("X" * 60 + "%") in sql
    assert ("X" * 61) not in sql


def test_escaping_composes_through_price_builder():
    # The escaped inner query must be embedded verbatim in dependent builders.
    inner = _mag_name_match("Foo_Bar")
    sql = _mag_price("Foo_Bar")
    assert inner in sql


def test_public_api_stable():
    # Sanity: the predicate map and helpers callers depend on still exist.
    assert site_of("price") == "shopping"
    assert site_of("score") == "reddit"
    assert site_of("does_not_exist") is None
    assert PREDICATES["price"].verifiable is True
    assert PREDICATES["category"].sql_builder is None
