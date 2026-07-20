"""Sandbox-native World Index construction utilities.

The package deliberately contains no task semantics.  It compiles frozen
documents, blocks, links, deterministic structured fields, and retrieval
indexes.  Task-local assertion extraction belongs to the later TWM phase.
"""

from .e1 import (
    E1_SCHEMA_VERSION,
    SHARD_ALGORITHM,
    WorldIndexWriter,
    canonical_json,
    parse_html_document,
    stable_bucket,
    stable_rank64,
)

__all__ = [
    "E1_SCHEMA_VERSION",
    "SHARD_ALGORITHM",
    "WorldIndexWriter",
    "canonical_json",
    "parse_html_document",
    "stable_bucket",
    "stable_rank64",
]
