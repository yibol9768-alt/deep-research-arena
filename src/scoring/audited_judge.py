"""Audited, JSON-only judge calls for the four-axis scoring pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable

from src.verifiers.judge_client import call_judge, judge_identity


JudgeCall = Callable[
    [str, str, str | None, int, float],
    tuple[str | None, str | None],
]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def parse_json_object(text: str) -> Any:
    """Parse a JSON response without silently interpreting prose."""

    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1)
        stripped = re.sub(r"\s*```$", "", stripped, count=1)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Some compatible endpoints prepend a short label despite the
        # instruction.  Accept only one complete outer object or array.
        starts = [idx for idx in (stripped.find("{"), stripped.find("[")) if idx >= 0]
        if not starts:
            raise
        start = min(starts)
        for end in range(len(stripped), start, -1):
            try:
                return json.loads(stripped[start:end])
            except json.JSONDecodeError:
                continue
        raise


def normalize_expected_top_level(
    value: Any,
    expected_top_key: str | None,
) -> tuple[Any, str | None]:
    """Apply lossless, schema-directed response-shape repairs.

    Small local judges sometimes wrap the requested object in a singleton
    JSON array.  Unwrap only the unambiguous case where that sole object
    already contains the exact required top-level key.  The verdict payload
    itself is never edited, inferred, or regenerated.

    They also sometimes return the requested item array directly.  Wrap a bare
    array only for one of the evaluator's explicit list-envelope schemas and
    only when every element is an object.  This preserves every model item
    verbatim while restoring the envelope explicitly required by the prompt.
    """

    if expected_top_key is None:
        return value, None
    if isinstance(value, dict) and expected_top_key in value:
        return value, None
    if (
        isinstance(value, list)
        and len(value) == 1
        and isinstance(value[0], dict)
        and expected_top_key in value[0]
    ):
        return value[0], "unwrap_singleton_object_array"
    if (
        expected_top_key in {
            "claims",
            "decisions",
            "judgments",
            "verdicts",
        }
        and isinstance(value, list)
        and all(isinstance(item, dict) for item in value)
        and not any(expected_top_key in item for item in value)
    ):
        return (
            {expected_top_key: value},
            f"wrap_bare_{expected_top_key}_array",
        )
    return value, None


@dataclass
class AuditedJudge:
    output_dir: Path
    model: str = "deepseek-v4-flash"
    max_tokens: int = 8192
    temperature: float = 0.0
    judge_call: JudgeCall | None = None

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._cache: dict[str, Path] = {}
        cache_roots = [
            Path(value)
            for value in os.environ.get("DRA_JUDGE_CACHE_DIRS", "").split(os.pathsep)
            if value
        ]
        for root in cache_roots:
            if not root.exists():
                continue
            for metadata_path in root.glob("*/metadata.json"):
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                request_sha = metadata.get("request_sha256")
                parsed_path = metadata_path.parent / "parsed-response.json"
                raw_path = metadata_path.parent / "raw-response.txt"
                if request_sha and parsed_path.exists() and raw_path.exists():
                    self._cache[str(request_sha)] = metadata_path.parent

    def _invoke(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        response_schema: dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        if self.judge_call is not None:
            return self.judge_call(
                system,
                user,
                self.model,
                max_tokens,
                self.temperature,
            )
        return call_judge(
            system,
            user,
            model=self.model,
            max_tokens=max_tokens,
            temperature=self.temperature,
            response_schema=response_schema,
        )

    def call_json(
        self,
        stage: str,
        system: str,
        payload: Any,
        *,
        expected_top_key: str | None = None,
        max_tokens: int | None = None,
        compact_payload: bool = False,
        response_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Call the fixed judge, validate basic shape, and seal the transcript."""

        effective_max_tokens = (
            self.max_tokens if max_tokens is None else int(max_tokens)
        )
        if effective_max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        self._counter += 1
        safe_stage = re.sub(r"[^a-zA-Z0-9_.-]+", "-", stage).strip("-")
        call_dir = self.output_dir / f"{self._counter:04d}-{safe_stage}"
        call_dir.mkdir(parents=True, exist_ok=False)
        user = json.dumps(
            payload,
            ensure_ascii=False,
            indent=None if compact_payload else 2,
            separators=(",", ":") if compact_payload else None,
        )
        payload_serialization = (
            "compact_json" if compact_payload else "pretty_json"
        )
        request = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": effective_max_tokens,
            "system": system,
            "user": user,
        }
        if response_schema is not None:
            request["response_schema"] = response_schema
        (call_dir / "request.json").write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        request_sha = sha256_bytes(canonical_json_bytes(request))
        cached_dir = self._cache.get(request_sha)
        if cached_dir is not None:
            raw = (cached_dir / "raw-response.txt").read_text(encoding="utf-8")
            parsed = json.loads(
                (cached_dir / "parsed-response.json").read_text(encoding="utf-8")
            )
            parsed, response_normalization = normalize_expected_top_level(
                parsed,
                expected_top_key,
            )
            if expected_top_key is not None and (
                not isinstance(parsed, dict) or expected_top_key not in parsed
            ):
                raise RuntimeError(
                    f"cached judge output at {cached_dir} lacks "
                    f"{expected_top_key!r}"
                )
            (call_dir / "raw-response.txt").write_text(raw, encoding="utf-8")
            (call_dir / "parsed-response.json").write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            metadata = {
                "schema": "dra_audited_judge_call_v1",
                "stage": stage,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "provider": judge_identity().get("provider"),
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": effective_max_tokens,
                "system_sha256": sha256_text(system),
                "user_sha256": sha256_text(user),
                "request_sha256": request_sha,
                "raw_response_sha256": sha256_text(raw),
                "error": None,
                "cache_hit": True,
                "cache_source": str(cached_dir.resolve()),
                "response_normalization": response_normalization,
                "payload_serialization": payload_serialization,
                "response_schema_sha256": (
                    sha256_bytes(canonical_json_bytes(response_schema))
                    if response_schema is not None
                    else None
                ),
            }
            (call_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return parsed

        raw, error = self._invoke(
            system,
            user,
            max_tokens=effective_max_tokens,
            response_schema=response_schema,
        )
        (call_dir / "raw-response.txt").write_text(raw or "", encoding="utf-8")
        metadata = {
            "schema": "dra_audited_judge_call_v1",
            "stage": stage,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "provider": judge_identity().get("provider"),
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": effective_max_tokens,
            "system_sha256": sha256_text(system),
            "user_sha256": sha256_text(user),
            "request_sha256": request_sha,
            "raw_response_sha256": sha256_text(raw or ""),
            "error": error,
            "cache_hit": False,
            "payload_serialization": payload_serialization,
            "response_schema_sha256": (
                sha256_bytes(canonical_json_bytes(response_schema))
                if response_schema is not None
                else None
            ),
        }
        (call_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if error or raw is None:
            raise RuntimeError(f"judge call failed at {stage}: {error or 'empty response'}")

        try:
            parsed = parse_json_object(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"judge returned invalid JSON at {stage}; transcript: {call_dir}"
            ) from exc
        parsed, response_normalization = normalize_expected_top_level(
            parsed,
            expected_top_key,
        )
        if response_normalization is not None:
            metadata["response_normalization"] = response_normalization
            (call_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if expected_top_key is not None:
            if not isinstance(parsed, dict) or expected_top_key not in parsed:
                raise RuntimeError(
                    f"judge output at {stage} lacks top-level key "
                    f"{expected_top_key!r}; transcript: {call_dir}"
                )
        (call_dir / "parsed-response.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return parsed


__all__ = [
    "AuditedJudge",
    "JudgeCall",
    "canonical_json_bytes",
    "normalize_expected_top_level",
    "parse_json_object",
    "sha256_bytes",
    "sha256_text",
]
