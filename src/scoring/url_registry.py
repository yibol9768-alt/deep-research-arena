"""Deterministic URL validation against the frozen DRA registry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from src.verifiers.citation_format import canonicalize_url


class FrozenURLRegistry:
    """Memory-efficient lookup wrapper for ``data/golden/url_registry.json``."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.version = payload.get("version")
        self.generated = payload.get("generated")
        self.hosts = payload.get("hosts", {})
        self.products = set(payload.get("products", []))
        self.wiki = {str(x).casefold() for x in payload.get("wiki", [])}
        self.submissions = {
            str(key): str(value).lower()
            for key, value in (payload.get("submissions") or {}).items()
        }
        self.snapshot_hashes = {
            str(key): str(value)
            for key, value in (payload.get("snapshot_hashes") or {}).items()
        }
        self.build_attestation = payload.get("build_attestation") or {}
        self.formal_snapshot_attestation_available = bool(
            self.snapshot_hashes
            and self.build_attestation.get("world_snapshot_id")
            and self.build_attestation.get("manifest_sha256")
        )

    @classmethod
    def load(cls, path: str | Path) -> "FrozenURLRegistry":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def inspect(self, raw_url: str) -> dict[str, Any]:
        try:
            canonical = canonicalize_url(raw_url)
        except Exception:
            canonical = ""
        parsed = urlparse(canonical) if canonical else None
        canonicalized = bool(
            parsed
            and parsed.scheme in {"http", "https"}
            and parsed.netloc
        )
        in_registry = False
        source_type = "unknown"
        registry_key = None

        if canonicalized and parsed is not None:
            host = parsed.netloc.lower()
            path = unquote(parsed.path)
            if host in {str(x).lower() for x in self.hosts.get("shopping", [])}:
                source_type = "product"
                registry_key = path.strip("/")
                if registry_key.endswith(".html"):
                    registry_key = registry_key[:-5]
                in_registry = registry_key in self.products
            elif host in {str(x).lower() for x in self.hosts.get("forums", [])}:
                source_type = "forum"
                match = re.match(r"^/f/([^/]+)/([0-9]+)(?:/|$)", path)
                if match:
                    forum, submission_id = match.groups()
                    registry_key = submission_id
                    in_registry = (
                        submission_id in self.submissions
                        and self.submissions[submission_id] == forum.lower()
                    )
            elif host in {str(x).lower() for x in self.hosts.get("wiki", [])}:
                source_type = "wikipedia"
                marker = "/content/wikipedia_en_all_nopic/"
                if marker in path:
                    registry_key = path.split(marker, 1)[1].strip("/")
                elif path.startswith("/wiki/"):
                    registry_key = path.split("/wiki/", 1)[1].strip("/")
                if registry_key:
                    candidates = {
                        registry_key,
                        registry_key.replace("_", " "),
                    }
                    # Kiwix may insert a one-character shard directory.
                    if re.match(r"^[A-Za-z0-9]/", registry_key):
                        tail = registry_key.split("/", 1)[1]
                        candidates.update({tail, tail.replace("_", " ")})
                    in_registry = any(
                        candidate.casefold() in self.wiki for candidate in candidates
                    )

        # Legacy registries were generated from successful snapshots, so
        # membership is retained as diagnostic snapshot availability. Formal
        # publication additionally requires per-entry hashes and a registry
        # build attestation; the pipeline fails closed when those are absent.
        snapshot_available = in_registry
        snapshot_hash = (
            self.snapshot_hashes.get(str(registry_key))
            if registry_key is not None
            else None
        )
        return {
            "raw_url": raw_url,
            "canonical_url": canonical,
            "canonicalized": canonicalized,
            "in_registry": in_registry,
            "snapshot_available": snapshot_available,
            "snapshot_attested": bool(
                snapshot_available
                and snapshot_hash
                and self.formal_snapshot_attestation_available
            ),
            "snapshot_sha256": snapshot_hash,
            "registry_build_attestation": self.build_attestation,
            "valid": canonicalized and in_registry and snapshot_available,
            "source_type": source_type,
            "registry_key": registry_key,
            "registry_version": self.version,
        }


__all__ = ["FrozenURLRegistry"]
