#!/usr/bin/env python3
"""Build and replay the DRA v3.3 sandbox-native audio_0002 vertical slice.

The script is intentionally self-contained: it compiles a light task World
Index from the frozen graph assets, builds a Task World Model and a hierarchical
Research Test Suite, generates controlled reports, replays their sealed
judgments, and scores one previously captured GPT-Researcher report.

This is a development measurement slice, not a formal leaderboard release.
The controlled fixtures have construction-known semantic labels.  The real
report is judged by a deterministic Task-World-Model-backed mock evaluator and
is stamped ineligible for formal ranking until that evaluator is calibrated.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.observation_ledger import ObservationLedger, load_observation_ledger
from src.eval.sandbox_native_grc import (
    JUDGMENT_SCHEMA,
    SUITE_SCHEMA,
    WORLD_SCHEMA,
    canonical_sha256,
    score_grounded_research_coverage,
    validate_suite,
    validate_world_index,
)
from src.eval.twm_mock_evaluator import evaluate_report_with_twm_mock


TASK_ID = "dra_v3_dev_audio_0002"
BASE = ROOT / "data/pilot_v33" / TASK_ID
SOURCE_GRAPH = (
    ROOT
    / "data/evidence_graph/dra-v3-pilot-audio-speaker-claims-20260715-r1"
)
CASE_PATH = ROOT / "data/golden/cases_v3/development" / f"{TASK_ID}.json"
TASK_PATH = ROOT / "data/tasks/deep_research/v3/development" / f"{TASK_ID}.json"
OLD_RUBRIC_PATH = (
    ROOT
    / "data/golden/route_flexible_rubrics/development"
    / f"{TASK_ID}.json"
)

FLARE_URL = (
    "http://localhost:7770/anker-soundcore-flare-2-bluetooth-speaker-with-"
    "360-sound-partycast-technology-adjustable-eq-12-hour-playtime-ipx7-"
    "waterproof-wireless-speaker-for-outdoor-beach-backyard-party-renewed.html"
)
ORTIZAN_URL = (
    "http://localhost:7770/ortizan-portable-bluetooth-speaker-40w-loud-stereo-"
    "sound-ipx7-waterproof-bluetooth-speakers-with-bluetooth-5-0-dual-pairing-"
    "6600-mah-15h-playtime-power-bank-function-for-party.html"
)
AUDIO_POWER_URL = "http://localhost:8090/content/wikipedia_en_all_nopic/Audio_power"
LOUDSPEAKER_URL = (
    "http://localhost:8090/content/wikipedia_en_all_nopic/Loudspeaker_acoustics"
)
PASSIVE_URL = (
    "http://localhost:8090/content/wikipedia_en_all_nopic/Passive_radiator_(speaker)"
)
IPX7_URL = "http://localhost:8090/content/wikipedia_en_all_nopic/IP_code"
CODEC_FORUM_URL = (
    "http://localhost:9999/f/headphones/126684/"
    "bluetooth-sound-quality-me-trying-to-explore-what-is-the"
)
PREFERENCE_FORUM_URL = (
    "http://localhost:9999/f/headphones/126709/"
    "how-come-my-relatively-cheap-bluetooth-speaker-sounds-better"
)
SEARCH_CAPTURE_URL = (
    "http://localhost:8081/search?capture_run=v3-corpus-audio-speaker-20260715-r1"
    "&request_id=36054a5f-8650-4a58-a509-0b6556a4a16a"
)


TASK_SPAN_SPECS: list[dict[str, Any]] = [
    {
        "span_id": "twm_flare_price",
        "url": FLARE_URL,
        "needle": "In stock SKU B0867KYSRC Rating: 72 % of 100 12 Reviews Add Your Review $53.49",
        "assertion_ids": ["F1"],
    },
    {
        "span_id": "twm_ortizan_price",
        "url": ORTIZAN_URL,
        "needle": "In stock SKU B08KCX841R Rating: 77 % of 100 12 Reviews Add Your Review $57.99",
        "assertion_ids": ["F2"],
    },
    {
        "span_id": "twm_flare_output_thd",
        "url": FLARE_URL,
        "needle": (
            "Audio Output: 20W (10W × 2) Battery Capacity: 5200mAh Charge Time: "
            "3.5 hrs at 5V/2A Bluetooth Frequency Range: 2400 - 2485MHz Sound "
            "Frequency Range: 73Hz ~ 20kHz(-3dB) THD+N: <1%"
        ),
        "assertion_ids": ["F3", "F4"],
    },
    {
        "span_id": "twm_ortizan_output_distortion",
        "url": ORTIZAN_URL,
        "needle": (
            "【40W Powerful Sound and Patented DSP Algorithm Technology】: Built "
            "with 2 x 20W Max speaker, Ortizan bluetooth speaker provides crystal "
            "clear sound and powerful bass without distortion even at maximum "
            "volume. 20Hz-16000Hz Frequency range to provide excellent stereo "
            "sound. And the dual passive radiators provide premium deep bass."
        ),
        "assertion_ids": ["F5"],
    },
    {
        "span_id": "twm_flare_design",
        "url": FLARE_URL,
        "needle": (
            "360° Sound: Dual drivers and passive radiators combine to provide "
            "20W of sound in all directions."
        ),
        "assertion_ids": ["F14"],
    },
    {
        "span_id": "twm_ortizan_design",
        "url": ORTIZAN_URL,
        "start_marker": "A huge 40W of sound delivered by dual high-performance drivers and thumping bass radiators.",
        "end_marker": "You will like Ortizan’s true 360° stereo sound portable wireless speakers.",
        "assertion_ids": ["F15"],
    },
    {
        "span_id": "twm_flare_water",
        "url": FLARE_URL,
        "needle": (
            "IPX7 Waterproof: Complete waterproof protection makes Flare 2 ideal "
            "for beach and pool parties."
        ),
        "assertion_ids": ["F6"],
    },
    {
        "span_id": "twm_ortizan_water",
        "url": ORTIZAN_URL,
        "needle": (
            "【IPX7 Waterproof Speaker】: Bluetooth speaker with IPX7 water "
            "resistance technology uses unbreakable TPU silicone material, perfect "
            "for pool party, travel."
        ),
        "assertion_ids": ["F6"],
    },
    {
        "span_id": "twm_flare_battery",
        "url": FLARE_URL,
        "needle": "Note: Playback volume, lights, and BassUp will affect playtime.",
        "assertion_ids": ["F8"],
    },
    {
        "span_id": "twm_ortizan_battery",
        "url": ORTIZAN_URL,
        "needle": (
            "15H Playing Time The bluetooth speaker with large capacity battery, "
            "One full charge lets you play music for up to 15 hours(Playtime "
            "varies according to volume level and audio content)."
        ),
        "assertion_ids": ["F9"],
    },
    {
        "span_id": "twm_audio_power_context",
        "url": AUDIO_POWER_URL,
        "start_marker": (
            "Audio power is the electrical power transferred from an audio amplifier "
            "to a loudspeaker , measured in watts ."
        ),
        "end_marker": (
            "loudspeakers are limited in the electrical power they can convert to "
            "sound power without being damaged or distorting the audio signal."
        ),
        "assertion_ids": ["F13"],
    },
    {
        "span_id": "twm_audio_power_distortion_condition",
        "url": AUDIO_POWER_URL,
        "needle": (
            "Considerably more power can be delivered if distortion is allowed to "
            "increase; some manufacturers quote maximum power at a higher "
            "distortion, like 10%, making their equipment appear more powerful."
        ),
        "assertion_ids": ["F13"],
    },
    {
        "span_id": "twm_acoustic_dimensions",
        "url": LOUDSPEAKER_URL,
        "start_marker": "Important driver characteristics are:",
        "end_marker": "Colouration (i.e., more or less, delayed resonance ).",
        "assertion_ids": ["F11", "F13"],
    },
    {
        "span_id": "twm_room_interaction",
        "url": LOUDSPEAKER_URL,
        "needle": (
            "It is the performance of a loudspeaker/listening room combination "
            "that really matters, as the two interact in multiple ways."
        ),
        "assertion_ids": ["F11"],
    },
    {
        "span_id": "twm_passive_mechanism",
        "url": PASSIVE_URL,
        "start_marker": "A speaker enclosure using a passive radiator usually contains",
        "end_marker": (
            "makes it easier for the speaker system to create the deepest pitches "
            "(e.g., basslines )."
        ),
        "assertion_ids": ["F10"],
    },
    {
        "span_id": "twm_ip_x_scope",
        "url": IPX7_URL,
        "needle": (
            "The digit is replaced with the letter X when insufficient data has "
            "been gathered to assign a protection level."
        ),
        "assertion_ids": ["F7"],
    },
    {
        "span_id": "twm_ipx7_test",
        "url": IPX7_URL,
        "start_marker": "7 Immersion, up to 1 meter (3\u00a0ft 3\u00a0in) depth",
        "end_marker": "Test duration: 30\u00a0minutes.",
        "assertion_ids": ["F7"],
    },
    {
        "span_id": "twm_codec_forum_scope",
        "url": CODEC_FORUM_URL,
        "needle": (
            "How were your assessments of which codec sounds better made, exactly? "
            "Did you conduct any controlled testing, or were you just basing them "
            "on the assumption that high bitrate = sounds better?"
        ),
        "assertion_ids": ["F12"],
    },
    {
        "span_id": "twm_preference_forum_scope",
        "url": PREFERENCE_FORUM_URL,
        "needle": (
            "I got an old pair of Bose Quiet Comfort 35 ii, audio technica "
            "ath-m50x, and just standard airpod gen 2. All 3 cant compare to my "
            "Tribit X Sound Go."
        ),
        "assertion_ids": ["F12"],
    },
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _source_roles(source_type: str) -> list[str]:
    return {
        "magento": ["product_primary"],
        "wikipedia": ["technical_reference"],
        "postmill": ["community_general"],
        "search_result": ["discovery_record"],
        "case_spec": ["query_context"],
    }.get(source_type, ["unclassified"])


def compile_world_index() -> dict[str, Any]:
    registry = _read_json(SOURCE_GRAPH / "corpus_registry.json")
    pages: list[dict[str, Any]] = []
    for entry in registry["entries"]:
        digest = str(entry["content_sha256"])
        blob_path = SOURCE_GRAPH / "blobs" / digest
        body_bytes = blob_path.read_bytes()
        if sha256(body_bytes).hexdigest() != digest:
            raise RuntimeError(f"source graph blob hash mismatch: {digest}")
        pages.append(
            {
                "page_id": entry["registry_id"],
                "canonical_url": entry["source_url"],
                "content_sha256": digest,
                "content_blob_ref": str(
                    (SOURCE_GRAPH / "blobs" / digest).relative_to(ROOT)
                ),
                "source_family": entry["source_type"],
                "source_roles": _source_roles(str(entry["source_type"])),
                "spans": [],
            }
        )
    pages.sort(key=lambda row: row["canonical_url"])
    manifest = _read_json(SOURCE_GRAPH / "manifest.json")
    world = {
        "schema": WORLD_SCHEMA,
        "task_id": TASK_ID,
        "world_snapshot": registry["corpus_snapshot"],
        "registry_sha256": manifest["corpus_registry_hash"],
        "compiler": {
            "name": "audio_0002_world_index_compiler",
            "version": "v2",
            "semantic_extraction": False,
            "legacy_support_spans_imported": False,
        },
        "registry_urls": sorted(entry["source_url"] for entry in registry["entries"]),
        "pages": pages,
    }
    validate_world_index(world)
    return world


def _extract_task_span(
    *, page: dict[str, Any], spec: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    body_path = ROOT / str(page["content_blob_ref"])
    body_bytes = body_path.read_bytes()
    if sha256(body_bytes).hexdigest() != page["content_sha256"]:
        raise RuntimeError(f"page changed during TWM extraction: {page['canonical_url']}")

    if "needle" in spec:
        span_bytes = str(spec["needle"]).encode("utf-8")
        start = body_bytes.find(span_bytes)
        if start < 0 or body_bytes.find(span_bytes, start + 1) >= 0:
            raise RuntimeError(
                f"{spec['span_id']}: exact extraction must have one match"
            )
        end = start + len(span_bytes)
        rule_kind = "unique_exact_bytes"
        rule_material = str(spec["needle"])
    else:
        start_marker = str(spec["start_marker"]).encode("utf-8")
        end_marker = str(spec["end_marker"]).encode("utf-8")
        start = body_bytes.find(start_marker)
        if start < 0 or body_bytes.find(start_marker, start + 1) >= 0:
            raise RuntimeError(
                f"{spec['span_id']}: start marker must have one match"
            )
        end_marker_start = body_bytes.find(end_marker, start + len(start_marker))
        if end_marker_start < 0:
            raise RuntimeError(f"{spec['span_id']}: end marker not found")
        if body_bytes.find(end_marker, end_marker_start + 1) >= 0:
            raise RuntimeError(
                f"{spec['span_id']}: end marker must have one downstream match"
            )
        end = end_marker_start + len(end_marker)
        span_bytes = body_bytes[start:end]
        rule_kind = "unique_bounded_bytes"
        rule_material = f"{spec['start_marker']}\n---END---\n{spec['end_marker']}"

    text = span_bytes.decode("utf-8")
    rule_id = f"extract_{spec['span_id']}_v1"
    row = {
        "span_id": spec["span_id"],
        "byte_start": start,
        "byte_end": end,
        "text": text,
        "text_sha256": sha256(span_bytes).hexdigest(),
        "support_type": "task_world_model_extraction",
        "assertion_ids": list(spec["assertion_ids"]),
        "extractor_rule_id": rule_id,
    }
    trace = {
        "rule_id": rule_id,
        "rule_kind": rule_kind,
        "span_id": spec["span_id"],
        "canonical_url": page["canonical_url"],
        "page_content_sha256": page["content_sha256"],
        "rule_material_sha256": sha256(rule_material.encode("utf-8")).hexdigest(),
        "byte_start": start,
        "byte_end": end,
        "extracted_text_sha256": row["text_sha256"],
        "match_cardinality": 1,
        "assertion_ids": list(spec["assertion_ids"]),
    }
    return row, trace


def build_task_contract(task: dict[str, Any]) -> dict[str, Any]:
    generator = task["query_contract"]["generator_view"]
    return {
        "schema": "dra_task_contract_v1",
        "task_id": TASK_ID,
        "intent_type": "buying_dilemma_claim_audit",
        "intent": task["intent"],
        "candidate_actions": generator["candidate_actions"],
        "user_constraints": generator["constraints"],
        "requested_facets": [
            "listing_and_measurement",
            "design_and_codec_claims",
            "use_case_reliability",
            "community_validation",
            "decision",
        ],
        "requested_outputs": [
            "comparison",
            "claim_audit",
            "bounded_uncertainty",
            "recommendation_or_deferral",
        ],
        "decision_policy": {
            "hard_budget_usd": 60,
            "priority_order": ["claim_auditability", "distortion_risk", "raw_wattage"],
            "allow_multiple_supported_conclusions": True,
            "acceptable_actions_are_computed": True,
        },
    }


def build_task_world_model(
    structural_world: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    world = deepcopy(structural_world)
    page_by_url = {page["canonical_url"]: page for page in world["pages"]}
    extraction_trace: list[dict[str, Any]] = []
    for spec in TASK_SPAN_SPECS:
        page = page_by_url.get(str(spec["url"]))
        if page is None:
            raise RuntimeError(f"TWM extraction URL is outside the world: {spec['url']}")
        span, trace = _extract_task_span(page=page, spec=spec)
        page["spans"].append(span)
        extraction_trace.append(trace)
    for page in world["pages"]:
        page["spans"].sort(key=lambda row: (row["byte_start"], row["span_id"]))
    world["compiler"]["task_local_semantic_extraction"] = {
        "name": "audio_0002_twm_span_builder",
        "version": "v1",
        "span_count": len(extraction_trace),
        "source": "frozen_page_content_blob_ref",
    }
    validate_world_index(world)

    def assertion(
        assertion_id: str,
        statement: str,
        modality: str,
        source_url: str,
        spans: list[str],
        *,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        page = page_by_url[source_url]
        return {
            "assertion_id": assertion_id,
            "statement": statement,
            "modality": modality,
            "source_role": page["source_roles"][0],
            "known_support_span_ids": spans,
            "answerability_witness_urls": [source_url],
            "limitations": limitations or [],
            "verification_status": "deterministically_extracted_from_frozen_page",
        }

    assertions = [
        assertion("F1", "Soundcore Flare 2 is listed at USD 53.49.", "retailer_claim", FLARE_URL, ["twm_flare_price"]),
        assertion("F2", "Ortizan 40W is listed at USD 57.99.", "retailer_claim", ORTIZAN_URL, ["twm_ortizan_price"]),
        assertion("F3", "Soundcore lists 20 W as two 10 W channels.", "retailer_claim", FLARE_URL, ["twm_flare_output_thd"]),
        assertion("F4", "Soundcore lists THD+N below 1 percent, without a captured test condition.", "retailer_claim", FLARE_URL, ["twm_flare_output_thd"], limitations=["test condition absent from the complete frozen listing"]),
        assertion("F5", "Ortizan lists two 20 W Max channels and qualitative distortion-free-at-maximum wording.", "retailer_claim", ORTIZAN_URL, ["twm_ortizan_output_distortion"], limitations=["no continuous-power basis or quantitative distortion condition"]),
        {
            "assertion_id": "F6",
            "statement": "Both product listings claim IPX7.",
            "modality": "retailer_claim",
            "source_role": "product_primary",
            "known_support_span_ids": ["twm_flare_water", "twm_ortizan_water"],
            "answerability_witness_urls": [FLARE_URL, ORTIZAN_URL],
            "limitations": ["seller declarations, not independent water validation"],
            "verification_status": "deterministically_extracted_from_frozen_page",
        },
        assertion("F7", "IPX7 is a bounded temporary-immersion classification and X assigns no particulate rating.", "technical_scope", IPX7_URL, ["twm_ip_x_scope", "twm_ipx7_test"]),
        assertion("F8", "Soundcore claims 12-hour playback and says volume, lights, and BassUp affect it.", "retailer_claim", FLARE_URL, ["twm_flare_battery"]),
        assertion("F9", "Ortizan claims up to 15 hours and says volume and content affect it.", "retailer_claim", ORTIZAN_URL, ["twm_ortizan_battery"]),
        assertion("F10", "A passive radiator is a real enclosure mechanism but is not by itself a bass-quality measurement.", "mechanism_explanation", PASSIVE_URL, ["twm_passive_mechanism"]),
        assertion("F11", "A 360-degree label alone does not demonstrate uniform off-axis performance or sound quality.", "mechanism_explanation", LOUDSPEAKER_URL, ["twm_acoustic_dimensions", "twm_room_interaction"]),
        {
            "assertion_id": "F12",
            "statement": "The captured forum evidence is general discussion, not same-model water validation.",
            "modality": "community_scope",
            "source_role": "community_general",
            "known_support_span_ids": [
                "twm_codec_forum_scope",
                "twm_preference_forum_scope",
            ],
            "answerability_witness_urls": [CODEC_FORUM_URL, PREFERENCE_FORUM_URL],
            "limitations": ["bounded captured pages, not corpus-wide absence"],
            "verification_status": "deterministically_extracted_from_frozen_page",
        },
        assertion("F13", "Electrical watts alone do not establish perceived loudness or clean maximum output.", "mechanism_explanation", AUDIO_POWER_URL, ["twm_audio_power_context", "twm_audio_power_distortion_condition"]),
        assertion("F14", "The Flare listing advertises 360-degree sound using dual drivers and passive radiators.", "retailer_claim", FLARE_URL, ["twm_flare_design"]),
        assertion("F15", "The Ortizan listing advertises 360-degree sound and bass radiators.", "retailer_claim", ORTIZAN_URL, ["twm_ortizan_design"]),
    ]
    twm = {
        "schema": "dra_task_world_model_v1",
        "task_id": TASK_ID,
        "world_sha256": canonical_sha256(world),
        "construction_policy": "deterministic_task_local_extraction_from_frozen_pages",
        "builder": {
            "name": "audio_0002_task_world_model_builder",
            "version": "v1",
            "input_world_sha256": canonical_sha256(structural_world),
            "legacy_case_facts_used": False,
            "legacy_support_spans_used": False,
        },
        "extraction_trace": extraction_trace,
        "assertions": assertions,
        "relations": [
            {
                "relation_id": "R_PRICE_BUDGET",
                "relation_type": "jointly_comparable_under_constraint",
                "source_assertion_ids": ["F1", "F2"],
                "target": "hard_budget_usd_60",
            },
            {
                "relation_id": "R_OUTPUT_CONDITIONS",
                "relation_type": "interpretation_limited_by",
                "source_assertion_ids": ["F3", "F4", "F5"],
                "target_assertion_ids": ["F13"],
            },
            {
                "relation_id": "R_FLARE_DESIGN_BOUNDARY",
                "relation_type": "marketing_claim_qualified_by",
                "source_assertion_ids": ["F14"],
                "target_assertion_ids": ["F10", "F11"],
            },
            {
                "relation_id": "R_ORTIZAN_DESIGN_BOUNDARY",
                "relation_type": "marketing_claim_qualified_by",
                "source_assertion_ids": ["F15"],
                "target_assertion_ids": ["F10", "F11"],
            },
            {
                "relation_id": "R_WATER_SCOPE",
                "relation_type": "seller_claim_qualified_by",
                "source_assertion_ids": ["F6"],
                "target_assertion_ids": ["F7", "F12"],
            },
            {
                "relation_id": "R_BATTERY_COMPARISON",
                "relation_type": "nominal_values_not_matched_test",
                "source_assertion_ids": ["F8", "F9"],
                "target": "runtime_comparison_uncertain",
            },
        ],
        "conflict_clusters": [
            {
                "cluster_id": "C_OUTPUT_DISCLOSURE",
                "relation": "incomparable_test_conditions",
                "assertion_ids": ["F3", "F4", "F5", "F13"],
                "required_treatment": "do not infer a clean-output winner",
            }
        ],
        "bounded_unknowns": [
            {
                "unknown_id": "U_HIRES_LISTINGS",
                "scope": [FLARE_URL, ORTIZAN_URL],
                "finding": "no hi-res-over-Bluetooth claim in the two complete captured listings",
            },
            {
                "unknown_id": "U_SAME_MODEL_WATER",
                "scope": "captured forum pages or a replayable targeted returned-results set",
                "finding": "no same-model water validation in that bounded scope",
            },
        ],
    }
    return world, twm


def _contract(
    contract_id: str,
    statement: str,
    roles: list[str],
    witnesses: list[str],
    *,
    mode: str = "body",
    window: int = 3500,
) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "statement": statement,
        "acceptable_source_roles": roles,
        "support_mode": mode,
        "binding_window_chars": window,
        "known_witnesses": witnesses,
        "known_witnesses_are_allowlist": False,
    }


def _ep(premise_id: str, contract_id: str) -> dict[str, Any]:
    return {"premise_id": premise_id, "kind": "evidence", "contract_id": contract_id}


def _sp(premise_id: str, certificate_id: str) -> dict[str, Any]:
    return {
        "premise_id": premise_id,
        "kind": "search_certificate",
        "certificate_id": certificate_id,
        "binding_window_chars": 1800,
    }


def _route(route_id: str, premises: list[dict[str, Any]]) -> dict[str, Any]:
    return {"route_id": route_id, "premises": premises}


def _check(
    check_id: str,
    content: str,
    *,
    routes: list[dict[str, Any]] | None = None,
    deps: list[str] | None = None,
    exempt: bool = False,
    critical: bool = False,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "tier": "core",
        "applicable": True,
        "content_contract": content,
        "evidence_exempt": exempt,
        "evidence_routes": routes or [],
        "depends_on_checks": deps or [],
        "critical_error_on_contradiction": critical,
    }


def build_mock_semantic_contracts() -> dict[str, dict[str, Any]]:
    """Executable heuristic contracts used only by the development mock judge.

    These patterns are deliberately stored in the frozen suite instead of in
    report-specific Python labels.  They make the mock's behavior inspectable,
    replayable, and replaceable by a calibrated semantic evaluator later.
    """

    return {
        "K_PRICE_FLARE": {
            "anchors": [r"\$\s*53\.49"],
            "required_groups": [[r"(?:Flare\s*2|Soundcore)"], [r"\$\s*53\.49"]],
        },
        "K_PRICE_ORTIZAN": {
            "anchors": [r"\$\s*57\.99"],
            "required_groups": [[r"Ortizan"], [r"\$\s*57\.99"]],
        },
        "K_OUTPUT_FLARE": {
            "anchors": [r"THD\s*\+?\s*N\s*(?::|<|below)", r"20\s*W\s*\(10\s*W"],
            "required_groups": [
                [r"(?:Flare\s*2|Soundcore)"],
                [r"20\s*W", r"10\s*W\s*[×x]\s*2"],
                [r"THD\s*\+?\s*N\s*(?::|<|below)?\s*<?\s*1\s*%"],
            ],
            "contradiction_patterns": [
                r"gives\s+total\s+continuous\s+power",
                r"measurable\s+assurance\s+of\s+clean\s+sound",
                r"distortion[-\s]?controlled\s+audio",
            ],
            "contradiction_scope": "report",
        },
        "K_OUTPUT_ORTIZAN": {
            "anchors": [r"2\s*[×x]\s*20\s*W\s*Max", r"40\s*W"],
            "required_groups": [
                [r"Ortizan"],
                [r"2\s*[×x]\s*20\s*W\s*Max", r"40\s*W"],
                [r"no\s+THD", r"without\s+(?:a\s+)?quantitative\s+distortion", r"qualitative.*distortion"],
            ],
            "contradiction_patterns": [r"Ortizan.{0,160}(?:is|means|equals)\s+(?:continuous\s+RMS|RMS\s+power)", r"Ortizan.{0,160}THD\s*[<:=]"],
            "contradiction_scope": "report",
        },
        "K_WATT_CONTEXT": {
            "anchors": [r"raw\s+wattage", r"headline\s+watt", r"wattage\s+is\s+not\s+enough"],
            "required_groups": [
                [r"watt(?:age|s)?"],
                [r"not\s+(?:enough|establish|directly\s+comparable)", r"alone\s+do(?:es)?\s+not", r"more\s+important\s+than\s+sheer\s+loudness"],
                [r"distortion", r"loudness", r"efficien"],
            ],
        },
        "K_DISTORTION_COMPARISON": {
            "anchors": [r"distortion\s+risk", r"clean[-\s]?output\s+winner", r"distortion\s+auditability"],
            "required_groups": [
                [r"Flare"],
                [r"Ortizan"],
                [r"distortion|THD"],
            ],
            "contradiction_patterns": [
                r"lower[s]?\s+the\s+risk\s+of\s+unpleasant\s+distortion",
                r"Flare.{0,220}(?:safer\s+choice|lower[-\s]?distortion[-\s]?risk)",
                r"measurable\s+assurance\s+of\s+clean\s+sound",
                r"20\s*W\s+of\s+distortion[-\s]?controlled\s+audio",
            ],
            "contradiction_scope": "report",
        },
        "K_DESIGN_FLARE": {
            "anchors": [r"Flare.{0,120}360", r"360.{0,160}Flare"],
            "required_groups": [[r"Flare"], [r"360"], [r"passive\s+radiator"]],
        },
        "K_DESIGN_ORTIZAN": {
            "anchors": [r"Ortizan.{0,160}360", r"360.{0,160}Ortizan"],
            "required_groups": [[r"Ortizan"], [r"360"], [r"passive\s+radiator"]],
        },
        "K_PASSIVE_BOUNDARY": {
            "anchors": [r"passive\s+radiator"],
            "required_groups": [
                [r"passive\s+radiator"],
                [r"mechanism|enclosure|pressure|resonan"],
                [r"does\s+not\s+(?:measure|prove|demonstrate)", r"presence\s+alone\s+does\s+not", r"not\s+(?:by\s+itself\s+)?proof"],
            ],
        },
        "K_DISPERSION_BOUNDARY": {
            "anchors": [r"polar\s+(?:plots|response)", r"off[-\s]?axis", r"actual\s+sound\s+field"],
            "required_groups": [
                [r"360"],
                [r"polar|off[-\s]?axis|directivity"],
                [r"cannot\s+be\s+audited|does\s+not\s+demonstrate|unconfirmed|without.*measure"],
            ],
        },
        "K_HIRES_FLARE_ABSENCE": {
            "anchors": [r"No\s+mention\s+of\s+high.{0,80}codec", r"Flare.{0,180}no\s+hi[-\s]?res"],
            "required_groups": [[r"Flare"], [r"no\s+(?:mention\s+of\s+)?(?:high.{0,2}resolution|hi.{0,2}res)|no\s+named\s+hi.{0,2}res"], [r"codec|aptX|LDAC"]],
        },
        "K_HIRES_ORTIZAN_ABSENCE": {
            "anchors": [r"Ortizan.{0,180}no\s+hi[-\s]?res", r"No\s+hi[-\s]?res\s+codec\s+claim"],
            "required_groups": [[r"Ortizan"], [r"no\s+(?:hi[-\s]?res|aptX|LDAC)|no\s+named\s+hi[-\s]?res"], [r"codec|aptX|LDAC|Bluetooth\s*5\.0"]],
        },
        "K_HIRES_RELEVANCE": {
            "anchors": [r"neither\s+speaker\s+makes\s+a\s+hi", r"hi[-\s]?res\s+is\s+non[-\s]?discriminating"],
            "required_groups": [[r"neither|both"], [r"hi.{0,2}res|high.{0,2}resolution"], [r"does\s+not\s+influence|non.{0,2}discriminating|unnecessary"]],
        },
        "K_WATER_FLARE": {
            "anchors": [r"Flare.{0,200}IPX7", r"IPX7.{0,200}Flare"],
            "required_groups": [[r"Flare"], [r"IPX7"], [r"listing|claim|rating"], [r"no\s+independent|not\s+independent|solely|only\s+by\s+the\s+rating"]],
        },
        "K_WATER_ORTIZAN": {
            "anchors": [r"Ortizan.{0,200}IPX7", r"IPX7.{0,200}Ortizan"],
            "required_groups": [[r"Ortizan"], [r"IPX7"], [r"listing|advertis|claim|rating"], [r"no\s+(?:test|independent|user)|not\s+independent|solely|only\s+the\s+rating"]],
        },
        "K_IPX7_SCOPE": {
            "anchors": [r"IPX7\s+is\s+defined", r"temporary\s+submersion", r"bounded\s+temporary\s+immersion"],
            "required_groups": [[r"IPX7"], [r"1\s*(?:meter|m).{0,80}30\s*(?:min|minute)|temporary\s+(?:submersion|immersion)|bounded.*immersion"], [r"(?:the\s+)?[“\"']?X[”\"']?.{0,100}(?:dust|particulate|no\s+data)|(?:dust|particulate).{0,100}[“\"']?X[”\"']?|no\s+particulate"]],
        },
        "K_POOL_APPLICATION": {
            "anchors": [r"poolside", r"pool\s+area", r"water[-\s]?resistance\s+confidence"],
            "required_groups": [[r"pool"], [r"IPX7|water"], [r"limit|not\s+unlimited|self[-\s]?declaration|ordinary\s+risk|lack\s+external\s+proof"]],
        },
        "K_BATTERY_FLARE": {
            "anchors": [r"Flare.{0,160}12[-\s]?hour", r"12[-\s]?hour\s+playtime"],
            "required_groups": [[r"Flare"], [r"12\s*(?:hours?|h\b)"], [r"volume"], [r"lights?"], [r"BassUp"]],
        },
        "K_BATTERY_ORTIZAN": {
            "anchors": [r"Ortizan.{0,160}15\s*(?:hours?|h\b)", r"15H\s+Playtime"],
            "required_groups": [[r"Ortizan"], [r"15\s*(?:hours?|h\b)"], [r"volume"], [r"content"]],
        },
        "K_BATTERY_COMPARISON": {
            "anchors": [r"not\s+directly\s+comparable", r"without\s+a\s+standardized\s+testing\s+protocol"],
            "required_groups": [[r"12\s*(?:hours?|h\b)"], [r"15\s*(?:hours?|h\b)"], [r"not\s+directly\s+comparable|without\s+(?:a\s+)?(?:standardized|matched).*condition"]],
        },
        "K_COMMUNITY_EVIDENCE": {
            "anchors": [r"same[-\s]?model\s+water", r"forum.{0,120}(?:general|model)", r"captured\s+codec\s+discussion"],
            "required_groups": [[r"forum|community|owner|user\s+report|captured\s+codec"], [r"same[-\s]?model|either\s+candidate|Flare.{0,80}Ortizan"], [r"bounded|captured|returned\s+(?:results|set)|general\s+(?:discussion|methodology)"]],
            "contradiction_patterns": [
                r"In\s+the\s+sandbox\s+data,\s+there\s+is\s+no\s+forum\s+or\s+review\s+content",
                r"no\s+relevant\s+user\s+reports\s+exist",
                r"no\s+user-submitted\s+water-immersion\s+evidence\s+exists\s+in\s+the\s+sandbox",
            ],
            "contradiction_scope": "report",
        },
        "K_COMMUNITY_CONCLUSION": {
            "anchors": [r"same[-\s]?model\s+water", r"corpus[-\s]?wide\s+absence", r"no\s+relevant\s+user\s+reports"],
            "required_groups": [[r"same[-\s]?model|either\s+candidate"], [r"bounded|captured|returned\s+set|not\s+a\s+claim.*anywhere"], [r"general\s+discussion|validation"]],
            "contradiction_patterns": [
                r"In\s+the\s+sandbox\s+data,\s+there\s+is\s+no\s+forum\s+or\s+review\s+content",
                r"no\s+relevant\s+user\s+reports\s+exist",
                r"no\s+user-submitted\s+water-immersion\s+evidence\s+exists\s+in\s+the\s+sandbox",
            ],
            "contradiction_scope": "report",
        },
        "K_DECISION_ACTION": {
            "anchors": [r"recommended\s+route", r"I\s+recommend", r"recommendation"],
            "required_groups": [[r"recommend(?:ed|ation)?|defer"], [r"Flare|Ortizan"], [r"\$\s*60|60\s+dollar|budget"]],
            "selection_window_chars": 5000,
        },
        "K_DECISION_PRIORITIES": {
            "anchors": [r"single\s+most\s+decisive\s+factor", r"requested\s+priority", r"claim\s+auditability"],
            "required_groups": [[r"auditab"], [r"distortion"], [r"watt|power"]],
            "contradiction_patterns": [
                r"single\s+most\s+decisive\s+factor.{0,260}THD",
                r"THD.{0,220}lower[s]?\s+the\s+risk\s+of\s+unpleasant\s+distortion",
                r"measurable\s+assurance\s+of\s+clean\s+sound",
            ],
            "contradiction_scope": "report",
        },
        "K_DECISION_LIMITS": {
            "anchors": [r"Remaining\s+Measurement\s+Limits", r"Key\s+Trade[-\s]?Off", r"tradeoff\s+is"],
            "required_groups": [[r"trade.{0,2}off|primary\s+trade|lower\s+headline\s+output"], [r"acoustic|directivity|distortion"], [r"water|IPX7"], [r"battery|playtime"], [r"community|owner|user-submitted"]],
            "selection_window_chars": 12000,
        },
    }


def build_mock_evidence_matchers() -> dict[str, dict[str, Any]]:
    return {
        "EC_FLARE_PRICE": {"required_groups": [[r"(?:\$53\.49|final_price.{0,20}53\.49)"]]},
        "EC_ORTIZAN_PRICE": {"required_groups": [[r"(?:\$57\.99|final_price.{0,20}57\.99)"]]},
        "EC_FLARE_OUTPUT": {"required_groups": [[r"20W\s*\(10W\s*×\s*2\)"], [r"THD\+N:\s*<1%"]]},
        "EC_ORTIZAN_OUTPUT": {"required_groups": [[r"2\s*x\s*20W\s*Max"], [r"without\s+distortion\s+even\s+at\s+maximum\s+volume"]]},
        "EC_WATT_CONTEXT": {"required_groups": [[r"measured\s+in\s+watts"], [r"speaker's\s+efficiency"], [r"distorting\s+the\s+audio\s+signal"]]},
        "EC_ACOUSTIC_DIMENSIONS": {"required_groups": [[r"Maximum\s+power\s+handling"], [r"Non-linear\s+distortion"]]},
        "EC_FLARE_DESIGN": {"required_groups": [[r"360°\s+Sound"], [r"passive\s+radiators"]]},
        "EC_ORTIZAN_DESIGN": {"required_groups": [[r"true\s+360°"], [r"(?:bass|passive)\s+radiators"]]},
        "EC_PASSIVE_MECHANISM": {"required_groups": [[r"passive\s+radiator"], [r"sound\s+pressure"], [r"deepest\s+pitches"]]},
        "EC_DISPERSION_SCOPE": {"required_groups": [[r"Off-axis\s+response"], [r"Non-linear\s+distortion"]]},
        "EC_FLARE_WATER": {"required_groups": [[r"IPX7\s+Waterproof"], [r"pool\s+part"]]},
        "EC_ORTIZAN_WATER": {"required_groups": [[r"IPX7\s+water\s+resistance"], [r"pool\s+party"]]},
        "EC_IP_X_SCOPE": {"required_groups": [[r"letter\s+X"], [r"assign\s+a\s+protection\s+level"]]},
        "EC_IPX7_TEST": {"required_groups": [[r"Immersion,\s+up\s+to\s+1\s+meter"], [r"Test\s+duration:\s+30"]]},
        "EC_FLARE_BATTERY": {"required_groups": [[r"Playback\s+volume"], [r"lights"], [r"BassUp"], [r"playtime"]]},
        "EC_ORTIZAN_BATTERY": {"required_groups": [[r"up\s+to\s+15\s+hours"], [r"volume\s+level"], [r"audio\s+content"]]},
        "EC_CODEC_FORUM_SCOPE": {"required_groups": [[r"controlled\s+testing"], [r"high\s+bitrate\s*=\s*sounds\s+better"]]},
        "EC_PREFERENCE_FORUM_SCOPE": {"required_groups": [[r"Tribit\s+X\s+Sound\s+Go"], [r"Bose\s+Quiet\s+Comfort"]]},
    }


def build_research_test_suite(contract_sha: str, twm_sha: str) -> dict[str, Any]:
    evidence_contracts = [
        _contract("EC_FLARE_PRICE", "Flare 2 snapshot price is USD 53.49.", ["product_primary"], ["twm_flare_price"]),
        _contract("EC_ORTIZAN_PRICE", "Ortizan snapshot price is USD 57.99.", ["product_primary"], ["twm_ortizan_price"]),
        _contract("EC_FLARE_OUTPUT", "Flare lists 20 W as 10 W times two and THD+N below 1 percent with no captured condition.", ["product_primary"], ["twm_flare_output_thd"]),
        _contract("EC_ORTIZAN_OUTPUT", "Ortizan lists two 20 W Max channels and qualitative distortion-free wording without a quantitative condition.", ["product_primary"], ["twm_ortizan_output_distortion"]),
        _contract("EC_WATT_CONTEXT", "Watts, efficiency, rating convention, and allowed distortion are distinct measurement considerations.", ["technical_reference"], ["twm_audio_power_context", "twm_audio_power_distortion_condition"]),
        _contract("EC_ACOUSTIC_DIMENSIONS", "Maximum power and nonlinear distortion are separate loudspeaker characteristics.", ["technical_reference"], ["twm_acoustic_dimensions"]),
        _contract("EC_FLARE_DESIGN", "Flare listing makes 360-degree and passive-radiator claims.", ["product_primary"], ["twm_flare_design"]),
        _contract("EC_ORTIZAN_DESIGN", "Ortizan listing makes 360-degree and passive-radiator claims.", ["product_primary"], ["twm_ortizan_design"]),
        _contract("EC_PASSIVE_MECHANISM", "Passive radiator is a real enclosure-pressure mechanism, not a complete quality measurement.", ["technical_reference"], ["twm_passive_mechanism"]),
        _contract("EC_DISPERSION_SCOPE", "A directional label does not replace off-axis and room-interaction evidence.", ["technical_reference"], ["twm_acoustic_dimensions", "twm_room_interaction"]),
        _contract("EC_FLARE_HIRES_ABSENCE", "Complete Flare listing contains no named hi-res-over-Bluetooth claim.", ["product_primary"], [FLARE_URL], mode="closed_page_absence"),
        _contract("EC_ORTIZAN_HIRES_ABSENCE", "Complete Ortizan listing contains no named hi-res-over-Bluetooth claim.", ["product_primary"], [ORTIZAN_URL], mode="closed_page_absence"),
        _contract("EC_FLARE_WATER", "Flare listing claims IPX7.", ["product_primary"], ["twm_flare_water"]),
        _contract("EC_ORTIZAN_WATER", "Ortizan listing claims IPX7.", ["product_primary"], ["twm_ortizan_water"]),
        _contract("EC_IP_X_SCOPE", "X assigns no particulate-protection level.", ["technical_reference"], ["twm_ip_x_scope"]),
        _contract("EC_IPX7_TEST", "IPX7 has a bounded temporary-immersion test.", ["technical_reference"], ["twm_ipx7_test"]),
        _contract("EC_FLARE_BATTERY", "Flare claims 12 hours and discloses volume, light, and BassUp caveats.", ["product_primary"], ["twm_flare_battery"]),
        _contract("EC_ORTIZAN_BATTERY", "Ortizan claims 15 hours and discloses volume and content caveats.", ["product_primary"], ["twm_ortizan_battery"]),
        _contract("EC_CODEC_FORUM_SCOPE", "Captured codec thread is general methodology discussion, not candidate-model testing.", ["community_general"], ["twm_codec_forum_scope"]),
        _contract("EC_PREFERENCE_FORUM_SCOPE", "Captured preference thread is general speaker discussion, not candidate-model water testing.", ["community_general"], ["twm_preference_forum_scope"]),
    ]

    facets = [
        {
            "facet_id": "F_LISTING_MEASUREMENT",
            "label": "Listing facts and measurement audit",
            "units": [
                {
                    "unit_id": "U_PRICE_BUDGET",
                    "checks": [
                        _check("K_PRICE_FLARE", "State Flare's exact frozen price and compare it with the USD 60 hard budget.", routes=[_route("listing", [_ep("P_FLARE_PRICE", "EC_FLARE_PRICE")])]),
                        _check("K_PRICE_ORTIZAN", "State Ortizan's exact frozen price and compare it with the USD 60 hard budget.", routes=[_route("listing", [_ep("P_ORTIZAN_PRICE", "EC_ORTIZAN_PRICE")])]),
                    ],
                },
                {
                    "unit_id": "U_OUTPUT_DISTORTION",
                    "checks": [
                        _check("K_OUTPUT_FLARE", "Preserve Flare's 20 W (10 W x 2), THD+N wording, and missing captured test condition without calling it continuous clean power.", routes=[_route("listing", [_ep("P_FLARE_OUTPUT", "EC_FLARE_OUTPUT")])], critical=True),
                        _check("K_OUTPUT_ORTIZAN", "Preserve Ortizan's 2 x 20 W Max and qualitative distortion wording without inventing continuous power or a THD condition.", routes=[_route("listing", [_ep("P_ORTIZAN_OUTPUT", "EC_ORTIZAN_OUTPUT")])], critical=True),
                        _check("K_WATT_CONTEXT", "Explain why headline watts alone do not establish loudness or clean maximum output.", routes=[_route("audio_power", [_ep("P_WATT", "EC_WATT_CONTEXT")]), _route("acoustic_dimensions", [_ep("P_ACOUSTIC", "EC_ACOUSTIC_DIMENSIONS")])]),
                        _check("K_DISTORTION_COMPARISON", "Compare auditability without declaring a clean-output winner from incompatible or underspecified conditions.", routes=[_route("audio_power_context", [_ep("P_FLARE", "EC_FLARE_OUTPUT"), _ep("P_ORTIZAN", "EC_ORTIZAN_OUTPUT"), _ep("P_CONTEXT", "EC_WATT_CONTEXT")]), _route("acoustics_dimensions", [_ep("P_FLARE", "EC_FLARE_OUTPUT"), _ep("P_ORTIZAN", "EC_ORTIZAN_OUTPUT"), _ep("P_CONTEXT", "EC_ACOUSTIC_DIMENSIONS")])], critical=True),
                    ],
                },
            ],
        },
        {
            "facet_id": "F_DESIGN_CODEC",
            "label": "Design and codec claim boundaries",
            "units": [
                {
                    "unit_id": "U_DESIGN_CLAIMS",
                    "checks": [
                        _check("K_DESIGN_FLARE", "Attribute Flare's 360-degree and passive-radiator labels to its listing.", routes=[_route("listing", [_ep("P_FLARE_DESIGN", "EC_FLARE_DESIGN")])]),
                        _check("K_DESIGN_ORTIZAN", "Attribute Ortizan's 360-degree and passive-radiator labels to its listing.", routes=[_route("listing", [_ep("P_ORTIZAN_DESIGN", "EC_ORTIZAN_DESIGN")])]),
                        _check("K_PASSIVE_BOUNDARY", "Treat passive radiator as a real mechanism without turning its presence into proof of superior bass.", routes=[_route("mechanism", [_ep("P_PASSIVE", "EC_PASSIVE_MECHANISM")])], critical=True),
                        _check("K_DISPERSION_BOUNDARY", "State that a 360-degree label does not demonstrate uniform off-axis quality without measurements.", routes=[_route("mechanism", [_ep("P_DISPERSION", "EC_DISPERSION_SCOPE")])], critical=True),
                    ],
                },
                {
                    "unit_id": "U_HIRES_AUDIT",
                    "checks": [
                        _check("K_HIRES_FLARE_ABSENCE", "Give a listing-scoped no-hi-res finding for the complete captured Flare page.", routes=[_route("bounded_absence", [_ep("P_FLARE_SCAN", "EC_FLARE_HIRES_ABSENCE")])]),
                        _check("K_HIRES_ORTIZAN_ABSENCE", "Give a listing-scoped no-hi-res finding for the complete captured Ortizan page.", routes=[_route("bounded_absence", [_ep("P_ORTIZAN_SCAN", "EC_ORTIZAN_HIRES_ABSENCE")])]),
                        _check("K_HIRES_RELEVANCE", "Conclude that hi-res is non-discriminating in this snapshot and avoid an unnecessary codec detour.", deps=["K_HIRES_FLARE_ABSENCE", "K_HIRES_ORTIZAN_ABSENCE"], exempt=True),
                    ],
                },
            ],
        },
        {
            "facet_id": "F_USE_CASE_RELIABILITY",
            "label": "Poolside and runtime reliability",
            "units": [
                {
                    "unit_id": "U_WATER_SCOPE",
                    "checks": [
                        _check("K_WATER_FLARE", "State that the Flare listing claims IPX7 without upgrading it to independent validation.", routes=[_route("listing", [_ep("P_FLARE_WATER", "EC_FLARE_WATER")])]),
                        _check("K_WATER_ORTIZAN", "State that the Ortizan listing claims IPX7 without upgrading it to independent validation.", routes=[_route("listing", [_ep("P_ORTIZAN_WATER", "EC_ORTIZAN_WATER")])]),
                        _check("K_IPX7_SCOPE", "Explain bounded immersion scope and the meaning of X.", routes=[_route("technical_scope", [_ep("P_IP_X", "EC_IP_X_SCOPE"), _ep("P_IPX7_TEST", "EC_IPX7_TEST")])], critical=True),
                        _check("K_POOL_APPLICATION", "Apply the bounded rating to poolside use and preserve remaining validation limits.", deps=["K_WATER_FLARE", "K_WATER_ORTIZAN", "K_IPX7_SCOPE"], exempt=True, critical=True),
                    ],
                },
                {
                    "unit_id": "U_BATTERY_CAVEATS",
                    "checks": [
                        _check("K_BATTERY_FLARE", "State Flare's 12-hour claim with volume, lights, and BassUp caveats.", routes=[_route("listing", [_ep("P_FLARE_BATTERY", "EC_FLARE_BATTERY")])]),
                        _check("K_BATTERY_ORTIZAN", "State Ortizan's 15-hour claim with volume and content caveats.", routes=[_route("listing", [_ep("P_ORTIZAN_BATTERY", "EC_ORTIZAN_BATTERY")])]),
                        _check("K_BATTERY_COMPARISON", "Do not treat nominal hours as directly comparable without matched test conditions.", deps=["K_BATTERY_FLARE", "K_BATTERY_ORTIZAN"], exempt=True),
                    ],
                },
            ],
        },
        {
            "facet_id": "F_COMMUNITY_VALIDATION",
            "label": "Community evidence scope",
            "units": [
                {
                    "unit_id": "U_COMMUNITY_SCOPE",
                    "checks": [
                        _check("K_COMMUNITY_EVIDENCE", "Use either a captured general thread or a replayable bounded search to establish the scope of community evidence.", routes=[_route("codec_thread", [_ep("P_CODEC_THREAD", "EC_CODEC_FORUM_SCOPE")]), _route("preference_thread", [_ep("P_PREFERENCE_THREAD", "EC_PREFERENCE_FORUM_SCOPE")]), _route("bounded_search", [_sp("P_SEARCH", "CERT_SAME_MODEL_WATER_SEARCH")])]),
                        _check("K_COMMUNITY_CONCLUSION", "Distinguish general discussion from same-model water validation and avoid a corpus-wide absence claim.", deps=["K_COMMUNITY_EVIDENCE"], exempt=True, critical=True),
                    ],
                }
            ],
        },
        {
            "facet_id": "F_DECISION",
            "label": "Constraint-linked recommendation",
            "units": [
                {
                    "unit_id": "U_RECOMMENDATION",
                    "checks": [
                        _check("K_DECISION_ACTION", "Recommend either candidate or explicitly defer while respecting the USD 60 hard budget.", deps=["K_PRICE_FLARE", "K_PRICE_ORTIZAN"], exempt=True),
                        _check("K_DECISION_PRIORITIES", "Tie the decision to auditability before distortion risk before raw wattage, without unsupported decisive claims.", deps=["K_DISTORTION_COMPARISON", "K_POOL_APPLICATION", "K_BATTERY_COMPARISON", "K_COMMUNITY_CONCLUSION"], exempt=True, critical=True),
                        _check("K_DECISION_LIMITS", "State the key tradeoff and remaining acoustic, water, battery, and community measurement limits.", deps=["K_PASSIVE_BOUNDARY", "K_DISPERSION_BOUNDARY", "K_HIRES_RELEVANCE", "K_POOL_APPLICATION", "K_BATTERY_COMPARISON", "K_COMMUNITY_CONCLUSION"], exempt=True),
                    ],
                }
            ],
        },
    ]
    suite = {
        "schema": SUITE_SCHEMA,
        "task_id": TASK_ID,
        "compiler": {
            "name": "audio_0002_rts_compiler",
            "version": "v1",
            "status": "single_task_candidate",
            "task_contract_sha256": contract_sha,
            "task_world_model_sha256": twm_sha,
        },
        "aggregation": "facet_macro_unit_macro_check_mean",
        "evidence_contracts": evidence_contracts,
        "mock_semantic_contracts": build_mock_semantic_contracts(),
        "mock_evidence_matchers": build_mock_evidence_matchers(),
        "search_certificates": [
            {
                "certificate_id": "CERT_SAME_MODEL_WATER_SEARCH",
                "required_entity_groups": [
                    ["soundcore flare 2", "soundcore flare2"],
                    ["ortizan 40w", "ortizan 40 w"],
                ],
                "required_topic_groups": [
                    ["water", "pool", "immersion", "ipx7"],
                    ["forum", "owner", "user", "review"],
                ],
                "require_all_returned_results_observed": True,
                "require_capture_page_observed": True,
                "scope_label": "returned results of one targeted same-model water/community query",
            }
        ],
        "facets": facets,
        "full_pass_contract": {
            "require_all_applicable_core_checks": True,
            "require_output_contract": True,
            "forbid_critical_errors": True,
            "forbid_confirmed_fabricated_urls": True,
        },
    }
    validate_suite(suite)
    return suite


def controlled_sentences(*, community_route: str = "reference") -> dict[str, str]:
    community = (
        "The captured codec discussion is general methodology, not a test of either "
        f"candidate in water. [codec discussion]({CODEC_FORUM_URL})"
    )
    if community_route == "bounded_search":
        community = (
            "Within the returned results of a targeted Soundcore Flare 2 and Ortizan "
            "40W water-owner forum search, I found only general discussion and no "
            "same-model water validation in that returned set. "
            f"[search capture]({SEARCH_CAPTURE_URL})"
        )
    return {
        "K_PRICE_FLARE": f"The captured Flare 2 price is $53.49, inside the hard $60 budget. [Flare listing]({FLARE_URL})",
        "K_PRICE_ORTIZAN": f"The captured Ortizan price is $57.99, also inside the hard $60 budget. [Ortizan listing]({ORTIZAN_URL})",
        "K_OUTPUT_FLARE": f"Flare lists 20 W as 10 W times two and THD+N below 1%, but the captured listing gives no THD test condition, so this is not proof of clean continuous output. [Flare listing]({FLARE_URL})",
        "K_OUTPUT_ORTIZAN": f"Ortizan lists two 20 W Max channels and qualitative distortion-free-at-maximum wording, without a continuous-power basis or quantitative distortion condition. [Ortizan listing]({ORTIZAN_URL})",
        "K_WATT_CONTEXT": f"Electrical watts, speaker efficiency, rating convention, and allowed distortion are distinct, so headline wattage alone does not establish loudness or clean maximum output. [audio power]({AUDIO_POWER_URL})",
        "K_DISTORTION_COMPARISON": f"The listings make Ortizan's wording less auditable, but Flare's unstated THD condition also prevents declaring a clean-output winner from these pages alone. [Flare]({FLARE_URL}) [Ortizan]({ORTIZAN_URL}) [measurement context]({AUDIO_POWER_URL})",
        "K_DESIGN_FLARE": f"Flare's listing attributes its 360-degree label to dual drivers and passive radiators. [Flare listing]({FLARE_URL})",
        "K_DESIGN_ORTIZAN": f"Ortizan's listing advertises true 360-degree sound and dual passive radiators. [Ortizan listing]({ORTIZAN_URL})",
        "K_PASSIVE_BOUNDARY": f"A passive radiator is a real enclosure-pressure mechanism, but its presence alone does not measure bass quality. [passive radiator]({PASSIVE_URL})",
        "K_DISPERSION_BOUNDARY": f"A 360-degree label does not demonstrate uniform off-axis response or better sound without directivity and room-interaction evidence. [loudspeaker acoustics]({LOUDSPEAKER_URL})",
        "K_HIRES_FLARE_ABSENCE": f"A complete scan of the captured Flare listing found no named hi-res-over-Bluetooth codec claim. [Flare listing]({FLARE_URL})",
        "K_HIRES_ORTIZAN_ABSENCE": f"A complete scan of the captured Ortizan listing found no named hi-res-over-Bluetooth codec claim. [Ortizan listing]({ORTIZAN_URL})",
        "K_HIRES_RELEVANCE": "Because neither captured listing makes that claim, hi-res is non-discriminating here and an LDAC detour is unnecessary.",
        "K_WATER_FLARE": f"The Flare page makes an IPX7 seller claim; it is not independent same-model water validation. [Flare listing]({FLARE_URL})",
        "K_WATER_ORTIZAN": f"The Ortizan page makes an IPX7 seller claim; it is not independent same-model water validation. [Ortizan listing]({ORTIZAN_URL})",
        "K_IPX7_SCOPE": f"IPX7 covers bounded temporary immersion under defined conditions, and X means no particulate-protection level was assigned. [IP code]({IPX7_URL})",
        "K_POOL_APPLICATION": "For poolside use, either speaker still needs ordinary risk controls because a bounded rating is not unlimited pool, saltwater, jet, or drop protection.",
        "K_BATTERY_FLARE": f"Flare claims 12 hours and discloses that volume, lights, and BassUp affect playtime. [Flare listing]({FLARE_URL})",
        "K_BATTERY_ORTIZAN": f"Ortizan claims up to 15 hours and discloses that volume and audio content affect playtime. [Ortizan listing]({ORTIZAN_URL})",
        "K_BATTERY_COMPARISON": "The 12-hour and 15-hour figures are not directly comparable without matched volume, content, lighting, and feature conditions.",
        "K_COMMUNITY_EVIDENCE": community,
        "K_COMMUNITY_CONCLUSION": "I therefore describe only the bounded captured result, not a claim that no same-model validation exists anywhere in the sandbox.",
        "K_DECISION_ACTION": "I recommend the Soundcore Flare 2 for this $60 purchase, while Ortizan remains a possible choice for a buyer who values its Max-power claim more heavily.",
        "K_DECISION_PRIORITIES": "The recommendation follows the requested priority: narrower and more auditable wording first, uncertainty about distortion second, and raw wattage last.",
        "K_DECISION_LIMITS": "The tradeoff is lower headline output versus narrower disclosure; acoustic directivity, matched distortion, battery, water survival, and same-model owner validation remain unmeasured.",
    }


SECTION_ORDER = [
    ("Price and budget", ["K_PRICE_FLARE", "K_PRICE_ORTIZAN"]),
    (
        "Output and distortion",
        [
            "K_OUTPUT_FLARE",
            "K_OUTPUT_ORTIZAN",
            "K_WATT_CONTEXT",
            "K_DISTORTION_COMPARISON",
        ],
    ),
    (
        "Design claims",
        [
            "K_DESIGN_FLARE",
            "K_DESIGN_ORTIZAN",
            "K_PASSIVE_BOUNDARY",
            "K_DISPERSION_BOUNDARY",
        ],
    ),
    (
        "Hi-res audit",
        ["K_HIRES_FLARE_ABSENCE", "K_HIRES_ORTIZAN_ABSENCE", "K_HIRES_RELEVANCE"],
    ),
    (
        "Poolside water scope",
        ["K_WATER_FLARE", "K_WATER_ORTIZAN", "K_IPX7_SCOPE", "K_POOL_APPLICATION"],
    ),
    (
        "Battery",
        ["K_BATTERY_FLARE", "K_BATTERY_ORTIZAN", "K_BATTERY_COMPARISON"],
    ),
    ("Community evidence", ["K_COMMUNITY_EVIDENCE", "K_COMMUNITY_CONCLUSION"]),
    (
        "Recommendation",
        ["K_DECISION_ACTION", "K_DECISION_PRIORITIES", "K_DECISION_LIMITS"],
    ),
]


def controlled_report(sentences: dict[str, str]) -> str:
    lines = [
        "# Portable speaker claim audit under $60",
        "",
        "This report compares the two frozen listings under the user's stated priorities.",
    ]
    for title, check_ids in SECTION_ORDER:
        lines.extend(["", f"## {title}", ""])
        for check_id in check_ids:
            lines.extend([sentences[check_id], ""])
    return "\n".join(lines).rstrip() + "\n"


def _ledger_from_records(run_id: str, records: list[dict[str, Any]]) -> ObservationLedger:
    return ObservationLedger.from_records(
        records,
        expected_run_id=run_id,
        capture_complete=True,
    )


def full_fixture_ledger(
    world: dict[str, Any], *, run_id: str, exclude_urls: set[str] | None = None
) -> ObservationLedger:
    excluded = exclude_urls or set()
    query = "soundcore flare 2 ortizan 40w water pool owner forum review"
    search_text = "Returned one general speaker-preference discussion."
    records: list[dict[str, Any]] = [
        {
            "run_id": run_id,
            "event_id": 1,
            "timestamp": 1.0,
            "event_type": "search_result",
            "request_url": SEARCH_CAPTURE_URL,
            "canonical_url": PREFERENCE_FORUM_URL,
            "content_text": search_text,
            "content_sha256": sha256(search_text.encode("utf-8")).hexdigest(),
            "observable": True,
            "metadata": {
                "query": query,
                "search_capture_url": SEARCH_CAPTURE_URL,
            },
        }
    ]
    event_id = 2
    for page in world["pages"]:
        url = page["canonical_url"]
        if url in excluded:
            continue
        body = (ROOT / page["content_blob_ref"]).read_text(encoding="utf-8")
        records.append(
            {
                "run_id": run_id,
                "event_id": event_id,
                "timestamp": float(event_id),
                "event_type": "fetch_body",
                "request_url": url,
                "canonical_url": url,
                "content_text": body,
                "content_sha256": page["content_sha256"],
                "http_status": 200,
                "observable": True,
                "metadata": {"delivery_scope": "complete_page"},
            }
        )
        event_id += 1
    ledger = _ledger_from_records(run_id, records)
    if not ledger.complete:
        raise RuntimeError(f"fixture ledger invalid: {ledger.withhold_reason_codes}")
    return ledger


def empty_fixture_ledger(run_id: str) -> ObservationLedger:
    ledger = _ledger_from_records(run_id, [])
    if not ledger.complete:
        raise RuntimeError(f"empty fixture ledger invalid: {ledger.withhold_reason_codes}")
    return ledger


def _check_map(suite: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        check["check_id"]: check
        for facet in suite["facets"]
        for unit in facet["units"]
        for check in unit["checks"]
    }


def _world_maps(world: dict[str, Any]):
    spans: dict[str, dict[str, Any]] = {}
    pages: dict[str, dict[str, Any]] = {}
    for page in world["pages"]:
        pages[page["canonical_url"]] = page
        for span in page["spans"]:
            row = dict(span)
            row["canonical_url"] = page["canonical_url"]
            spans[span["span_id"]] = row
    return pages, spans


def _contract_map(suite: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["contract_id"]: row for row in suite["evidence_contracts"]}


DEFAULT_ROUTE_OVERRIDES = {
    "K_WATT_CONTEXT": "audio_power",
    "K_DISTORTION_COMPARISON": "audio_power_context",
    "K_COMMUNITY_EVIDENCE": "codec_thread",
}


def _binding_for_premise(
    *,
    check_id: str,
    route_id: str,
    premise: dict[str, Any],
    sentence: str,
    report: str,
    suite: dict[str, Any],
    world: dict[str, Any],
    url_override: str | None = None,
    support_override: str | None = None,
) -> dict[str, Any]:
    start = report.find(sentence)
    if start < 0:
        raise RuntimeError(f"sentence not found for {check_id}")
    if premise.get("kind", "evidence") == "search_certificate":
        return {
            "url": url_override or SEARCH_CAPTURE_URL,
            "quote": sentence,
            "start": start,
            "end": start + len(sentence),
        }
    contracts = _contract_map(suite)
    pages, spans = _world_maps(world)
    contract = contracts[premise["contract_id"]]
    mode = contract.get("support_mode", "body")
    witness = contract["known_witnesses"][0]
    evidence_span_id: str | None = None
    evidence_quote = ""
    if mode == "closed_page_absence":
        url = witness
    else:
        evidence_span_id = witness
        span = spans[witness]
        url = span["canonical_url"]
        evidence_quote = span["text"]
    url = url_override or url
    binding = {
        "url": url,
        "quote": sentence,
        "start": start,
        "end": start + len(sentence),
        "evidence_span_id": evidence_span_id,
        "evidence_quote": evidence_quote,
        "support_verdict": support_override or "supported",
    }
    if url_override and url_override not in pages:
        binding["evidence_span_id"] = None
    return binding


def construction_judgment(
    *,
    suite: dict[str, Any],
    world: dict[str, Any],
    report: str,
    ledger: ObservationLedger,
    sentences: dict[str, str] | None,
    route_overrides: dict[str, str] | None = None,
    binding_url_overrides: dict[tuple[str, str, str], str] | None = None,
    support_overrides: dict[tuple[str, str, str], str] | None = None,
    url_audits: list[dict[str, Any]] | None = None,
    all_content_satisfied: bool = True,
) -> dict[str, Any]:
    checks = _check_map(suite)
    chosen_routes = dict(DEFAULT_ROUTE_OVERRIDES)
    chosen_routes.update(route_overrides or {})
    url_overrides = binding_url_overrides or {}
    support = support_overrides or {}
    rows: list[dict[str, Any]] = []
    for check_id, check in checks.items():
        sentence = (sentences or {}).get(check_id, "")
        start = report.find(sentence) if sentence else -1
        content = (
            {
                "verdict": "satisfied",
                "quote": sentence,
                "start": start,
                "end": start + len(sentence),
                "reason": "construction-known oracle content",
            }
            if all_content_satisfied and sentence and start >= 0
            else {
                "verdict": "not_satisfied",
                "quote": "",
                "start": None,
                "end": None,
                "reason": "controlled negative fixture",
            }
        )
        route_attempts: list[dict[str, Any]] = []
        if content["verdict"] == "satisfied" and check["evidence_routes"]:
            route_id = chosen_routes.get(check_id, check["evidence_routes"][0]["route_id"])
            route = next(row for row in check["evidence_routes"] if row["route_id"] == route_id)
            premise_rows = []
            for premise in route["premises"]:
                key = (check_id, route_id, premise["premise_id"])
                premise_rows.append(
                    {
                        "premise_id": premise["premise_id"],
                        "bindings": [
                            _binding_for_premise(
                                check_id=check_id,
                                route_id=route_id,
                                premise=premise,
                                sentence=sentence,
                                report=report,
                                suite=suite,
                                world=world,
                                url_override=url_overrides.get(key),
                                support_override=support.get(key),
                            )
                        ],
                    }
                )
            route_attempts.append(
                {
                    "route_id": route_id,
                    "coherence_verdict": "coherent",
                    "conflict_verdict": (
                        "resolved" if check_id == "K_DISTORTION_COMPARISON" else "not_material"
                    ),
                    "premises": premise_rows,
                }
            )
        rows.append(
            {
                "check_id": check_id,
                "content": content,
                "route_attempts": route_attempts,
            }
        )
    return {
        "schema": JUDGMENT_SCHEMA,
        "task_id": TASK_ID,
        "evaluator": {
            "provider": "construction_known_fixture",
            "version": "v1",
            "formal_eligible": True,
        },
        "seals": {
            "suite_sha256": canonical_sha256(suite),
            "world_sha256": canonical_sha256(world),
            "report_sha256": sha256(report.encode("utf-8")).hexdigest(),
            "ledger_sha256": canonical_sha256(ledger.to_dict()),
        },
        "checks": rows,
        "url_audits": url_audits or [],
        "output_contract": {
            "verdict": "satisfied" if all_content_satisfied else "not_satisfied"
        },
    }


def _row(judgment: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(row for row in judgment["checks"] if row["check_id"] == check_id)


def frankenstein_judgment(
    *,
    suite: dict[str, Any],
    world: dict[str, Any],
    report: str,
    ledger: ObservationLedger,
    sentences: dict[str, str],
) -> dict[str, Any]:
    judgment = construction_judgment(
        suite=suite,
        world=world,
        report=report,
        ledger=ledger,
        sentences=sentences,
    )
    check = _check_map(suite)["K_DISTORTION_COMPARISON"]
    sentence = sentences["K_DISTORTION_COMPARISON"]
    attempts = []
    for route in check["evidence_routes"]:
        if route["route_id"] == "audio_power_context":
            selected = route["premises"][:2]
        else:
            selected = route["premises"][2:]
        attempts.append(
            {
                "route_id": route["route_id"],
                "coherence_verdict": "coherent",
                "conflict_verdict": "resolved",
                "premises": [
                    {
                        "premise_id": premise["premise_id"],
                        "bindings": [
                            _binding_for_premise(
                                check_id="K_DISTORTION_COMPARISON",
                                route_id=route["route_id"],
                                premise=premise,
                                sentence=sentence,
                                report=report,
                                suite=suite,
                                world=world,
                            )
                        ],
                    }
                    for premise in selected
                ],
            }
        )
    _row(judgment, "K_DISTORTION_COMPARISON")["route_attempts"] = attempts
    return judgment


def real_run_projection() -> ObservationLedger:
    run_id = "gpt-researcher-20260717T090549-1380fd670a38-projection"
    sources = [
        (
            FLARE_URL,
            "de270f0b8132815e259945008187a338d1283b9194068775d3d2f27acdaf6b59",
        ),
        (
            ORTIZAN_URL,
            "5fe2d0cdf4cd65d21040e66984a668fd36fc42c6a225302ffd4d7e5c2e485846",
        ),
    ]
    records: list[dict[str, Any]] = []
    for event_id, (url, digest) in enumerate(sources, 1):
        records.append(
            {
                "run_id": run_id,
                "event_id": event_id,
                "timestamp": float(event_id),
                "event_type": "fetch_body",
                "request_url": url,
                "canonical_url": url,
                "content_sha256": digest,
                "blob_ref": digest,
                "http_status": 200,
                "observable": True,
                "metadata": {
                    "delivery_scope": "complete_page",
                    "projection_policy": "retain_only_two_candidate_product_fetches",
                },
            }
        )
    ledger = ObservationLedger.from_records(
        records,
        expected_run_id=run_id,
        blob_loader=BASE / "real_run/blobs",
        capture_complete=True,
    )
    if not ledger.complete:
        raise RuntimeError(f"real-run projection invalid: {ledger.withhold_reason_codes}")
    return ledger


def _write_ledger(path: Path, ledger: ObservationLedger) -> None:
    _write_json(path, ledger.to_dict())


def _score_and_write(
    *,
    name: str,
    suite: dict[str, Any],
    world: dict[str, Any],
    report: str,
    ledger: ObservationLedger,
    judgment: dict[str, Any],
    report_path: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    _write_text(report_path, report)
    _write_ledger(ledger_path, ledger)
    judgment_path = BASE / "controlled/judgments" / f"{name}.json"
    score_path = BASE / "controlled/scores" / f"{name}.json"
    _write_json(judgment_path, judgment)
    result = score_grounded_research_coverage(
        suite=suite,
        world=world,
        report=report,
        ledger=ledger,
        judgment=judgment,
    )
    _write_json(score_path, result)
    return result


def _scenario_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_grc": result.get("raw_grc"),
        "official_grc": result.get("official_grc"),
        "content_breadth": result.get("content_breadth"),
        "full_pass": result.get("full_pass"),
        "passed_checks": result.get("passed_checks"),
        "applicable_checks": result.get("applicable_checks"),
        "fabricated_urls": len(result.get("integrity", {}).get("fabricated_urls", [])),
        "real_off_world_urls": len(result.get("integrity", {}).get("real_off_world_urls", [])),
        "unobserved_citations": len(result.get("integrity", {}).get("unobserved_citations", [])),
        "pending_checks": len(result.get("pending_checks", [])),
        "formal_eligible": result.get("formal_eligible"),
    }


def build_frozen_manifest(world: dict[str, Any], suite: dict[str, Any]) -> dict[str, Any]:
    graph_files = [
        "manifest.json",
        "corpus_registry.json",
        "nodes.jsonl",
        "edges.jsonl",
    ]
    real_blobs = sorted((BASE / "real_run/blobs").iterdir())
    return {
        "schema": "dra_single_task_frozen_input_manifest_v1",
        "task_id": TASK_ID,
        "status": "development_vertical_slice",
        "inputs": {
            "public_task": {"path": str(TASK_PATH.relative_to(ROOT)), "sha256": _file_sha(TASK_PATH)},
            "source_graph": [
                {
                    "path": str((SOURCE_GRAPH / name).relative_to(ROOT)),
                    "sha256": _file_sha(SOURCE_GRAPH / name),
                }
                for name in graph_files
            ],
            "real_report": {"path": str((BASE / "real_run/report.md").relative_to(ROOT)), "sha256": _file_sha(BASE / "real_run/report.md")},
            "real_delivery_blobs": [
                {"path": str(path.relative_to(ROOT)), "sha256": _file_sha(path)}
                for path in real_blobs
            ],
        },
        "legacy_comparison_assets_not_consumed_by_twm_builder": [
            {
                "path": str(CASE_PATH.relative_to(ROOT)),
                "sha256": _file_sha(CASE_PATH),
                "reason": "retained only for historical comparison",
            },
            {
                "path": str(OLD_RUBRIC_PATH.relative_to(ROOT)),
                "sha256": _file_sha(OLD_RUBRIC_PATH),
                "reason": "retained only for old-score comparison",
            },
            {
                "path": str((SOURCE_GRAPH / "support_spans.jsonl").relative_to(ROOT)),
                "sha256": _file_sha(SOURCE_GRAPH / "support_spans.jsonl"),
                "reason": "explicitly excluded; task spans are re-extracted from page bodies",
            },
        ],
        "compiled": {
            "world_sha256": canonical_sha256(world),
            "suite_sha256": canonical_sha256(suite),
            "task_world_model_sha256": canonical_sha256(
                _read_json(BASE / "task-world-model.json")
            ),
            "structural_world_sha256": canonical_sha256(
                _read_json(BASE / "world-index-structural.json")
            ),
        },
        "policy": {
            "construction_witnesses_are_url_allowlist": False,
            "formal_score_requires_calibrated_semantic_evaluator": True,
            "real_run_projection_may_not_support_search_quality_claims": True,
            "real_run_evaluator": "twm_backed_mock_evaluator",
            "real_run_formal_eligible": False,
        },
    }


def _check_pass(result: dict[str, Any], check_id: str) -> bool:
    return next(
        row["grounded_pass"]
        for row in result["check_results"]
        if row["check_id"] == check_id
    )


def _experiment_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# `dra_v3_dev_audio_0002` 沙盒原生评分纵向实验",
        "",
        "> 状态：development-only。受控基线的语义标签由构造已知；真实旧报告由 TWM-backed deterministic mock 自动判断。mock 尚未经过人工校准，因此不能进入正式榜单。",
        "",
        "## 本次真正跑通的链路",
        "",
        "```text",
        "冻结 task / graph / page bodies / run",
        "  -> 轻量 structural World Index（不导入旧答案 span）",
        "  -> 从冻结正文确定性抽取 task-local spans",
        "  -> Task World Model（assertions + conflicts + bounded unknowns）",
        "  -> 5 facets / 8 units / 25 checks 的 Research Test Suite",
        "  -> report + observation ledger + sealed TWM-backed mock judgment",
        "  -> ContentBreadth / Raw GRC / Official GRC / Full Pass / URL 与证据诊断",
        "```",
        "",
        "每个 check 只有在内容合同满足，并且至少一条完整、连贯的证据路线全部通过时才得分。不同路线之间不能逐前提拼接。构题 witness 只证明可答，不是 URL 白名单。",
        "",
        "## 这次重构的边界",
        "",
        "- World Index 只从 registry 和冻结正文建立，明确不导入旧 case facts 与旧 `support_spans.jsonl`。",
        "- TWM builder 用 19 条可审计的唯一字节匹配规则，从冻结正文重新抽取 task-local spans；每条都记录页面哈希、字节偏移、规则哈希和唯一命中数。",
        "- 15 条 assertion 的语义表述仍属于单题 compiler 模板，不宣称已经实现跨 56 题的自动事实归纳。",
        "- 真实报告的 25 项 verdict 不再由人工表填写，而由 suite 内冻结的 regex 合同自动生成；这是可替换的 mock，不是经过人类校准的正式 judge。",
        "- 引用是否在册、是否本次观察、是否就地绑定、页面角色与 span/certificate 是否有效，仍由确定性 scorer 独立复核，mock 不能自行加分。",
        "",
        "## 受控实验结果",
        "",
        "| 场景 | ContentBreadth | Raw GRC | Official GRC | Full Pass | 说明 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    descriptions = {
        "oracle_reference": "已知论坛 witness 路线",
        "twm_mock_oracle": "同一 oracle 由 TWM-backed mock 自动判定",
        "oracle_alternative": "有界搜索替代路线",
        "null": "空报告",
        "url_dump": "只有链接，没有研究内容",
        "fluent_unsupported": "内容完整但本次没有交付证据",
        "frankenstein": "把两条路线的残片拼在一起",
        "unobserved_ipx7": "IPX7 技术页未在本次交付",
        "wrong_binding": "相关领域页面错绑到 watt claim",
        "contradicted_citation": "IPX7 支持判为反驳",
        "fabricated_url": "额外加入确认不存在的沙盒 URL",
        "real_off_world_only": "用真实外部 URL 替代一个在册证据",
    }
    for name, row in summary["controlled_scenarios"].items():
        official = "PENDING" if row["official_grc"] is None else f"{row['official_grc']:.3f}"
        lines.append(
            f"| `{name}` | {row['content_breadth']:.3f} | {row['raw_grc']:.3f} | "
            f"{official} | {row['full_pass']} | {descriptions[name]} |"
        )
    real = summary["real_run"]
    lines.extend(
        [
            "",
            "## 真实旧报告重放",
            "",
            "| 指标 | 结果 |",
            "|---|---:|",
            f"| ContentBreadth | {real['content_breadth']:.3f} |",
            f"| Raw GRC | {real['raw_grc']:.3f} |",
            f"| Official GRC | {real['official_grc']:.3f} |",
            f"| Grounded checks | {real['passed_checks']}/{real['applicable_checks']} |",
            f"| Full Pass | {real['full_pass']} |",
            f"| Fabricated URL | {real['fabricated_urls']} |",
            f"| Formal eligible | {str(real['formal_eligible']).lower()} |",
            "",
            "这个结果不再来自人工填写的 25 项 verdict，也不是旧固定路线的 0/15。它由冻结的页面正文重构 TWM 后自动得到：报告确实从 Ortizan 商品页完成的局部研究被保留；Soundcore 无 URL、技术页无引用、论坛范围过度概括、THD 条件过推和推荐依赖失败则被逐项暴露。",
            "",
            "## 验收门",
            "",
            "| 验收项 | 结果 |",
            "|---|:---:|",
        ]
    )
    for gate, passed in summary["release_gates"].items():
        lines.append(f"| `{gate}` | {'PASS' if passed else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## 仍未被这一个样例证明的内容",
            "",
            "- 25 个 checks 是否代表跨题通用 compiler 的稳定输出，仍需 Dev-14 的双人校准与编辑率统计。",
            "- TWM-backed mock 的 regex 合同尚未通过双人金标、替代表述集和腐蚀集校准；当前只证明世界模型到评分器的自动闭环，不证明正式语义判定精度。",
            "- 真实运行使用的是两页候选商品 fetch 的评分投影，不能用来评价完整搜索 API 召回或整个 harness 的检索效率。",
            "- Observation Ledger v2 的 raw fetch 到 model-delivered artifact 血统仍需在 12 个 adapter 上逐一做 canary。",
            "",
            "因此，下一步应先复制这个纵向样例到另外两种任务结构，而不是直接批量生成 56 份未校准测试。",
            "",
        ]
    )
    return "\n".join(lines)


def _readme() -> str:
    return f"""# DRA v3.3 single-task vertical slice

Task: `{TASK_ID}`

This directory is a development-only, replayable example of the sandbox-native
scoring design. It contains the frozen source graph, a compiled light World
Index, a Task World Model, a 5-facet / 8-unit / 25-check Research Test Suite,
controlled adversarial fixtures, and one projected real run.

Run from the repository root:

```bash
PYTHONPATH=. python3 scripts/run_audio_0002_sandbox_native_slice.py
PYTHONPATH=. python3 -m pytest -q tests/test_sandbox_native_audio_0002.py
```

Replay any sealed fixture directly:

```bash
PYTHONPATH=. python3 scripts/score_sandbox_native_grc.py \\
  --suite data/pilot_v33/{TASK_ID}/research-test-suite.json \\
  --world data/pilot_v33/{TASK_ID}/world-index.json \\
  --report data/pilot_v33/{TASK_ID}/controlled/reports/oracle_alternative.md \\
  --ledger data/pilot_v33/{TASK_ID}/controlled/ledgers/oracle_alternative.json \\
  --judgment data/pilot_v33/{TASK_ID}/controlled/judgments/oracle_alternative.json \\
  --pretty
```

The construction judgments are known test labels. A second oracle replay and
the real report are judged by the deterministic TWM-backed mock evaluator. Its
outputs have `formal_eligible=false`: they demonstrate the complete automated
World Model path, not leaderboard validity.
"""


def run() -> dict[str, Any]:
    task = _read_json(TASK_PATH)
    structural_world = compile_world_index()
    task_contract = build_task_contract(task)
    world, twm = build_task_world_model(structural_world)
    suite = build_research_test_suite(
        canonical_sha256(task_contract), canonical_sha256(twm)
    )

    _write_json(BASE / "world-index-structural.json", structural_world)
    _write_json(BASE / "world-index.json", world)
    _write_json(BASE / "task-contract.json", task_contract)
    _write_json(BASE / "task-world-model.json", twm)
    _write_json(BASE / "research-test-suite.json", suite)

    full = full_fixture_ledger(world, run_id="fixture-full")
    no_ipx7 = full_fixture_ledger(
        world, run_id="fixture-no-ipx7", exclude_urls={IPX7_URL}
    )
    empty = empty_fixture_ledger("fixture-empty")

    scenarios: dict[str, dict[str, Any]] = {}

    def score_controlled(
        name: str,
        report: str,
        ledger: ObservationLedger,
        judgment: dict[str, Any],
    ) -> dict[str, Any]:
        result = _score_and_write(
            name=name,
            suite=suite,
            world=world,
            report=report,
            ledger=ledger,
            judgment=judgment,
            report_path=BASE / "controlled/reports" / f"{name}.md",
            ledger_path=BASE / "controlled/ledgers" / f"{name}.json",
        )
        scenarios[name] = result
        return result

    reference_sentences = controlled_sentences()
    reference_report = controlled_report(reference_sentences)
    reference_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=reference_report,
        ledger=full,
        sentences=reference_sentences,
    )
    score_controlled("oracle_reference", reference_report, full, reference_judgment)

    mock_oracle_judgment = evaluate_report_with_twm_mock(
        suite=suite,
        world=world,
        twm=twm,
        report=reference_report,
        ledger=full,
    )
    score_controlled(
        "twm_mock_oracle", reference_report, full, mock_oracle_judgment
    )

    alternative_sentences = controlled_sentences(community_route="bounded_search")
    alternative_report = controlled_report(alternative_sentences)
    alternative_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=alternative_report,
        ledger=full,
        sentences=alternative_sentences,
        route_overrides={"K_COMMUNITY_EVIDENCE": "bounded_search"},
    )
    score_controlled(
        "oracle_alternative", alternative_report, full, alternative_judgment
    )

    null_report = ""
    null_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=null_report,
        ledger=empty,
        sentences=None,
        all_content_satisfied=False,
    )
    score_controlled("null", null_report, empty, null_judgment)

    url_dump_report = "# Sources only\n\n" + "\n".join(
        f"- [source]({url})" for url in world["registry_urls"]
    ) + "\n"
    url_dump_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=url_dump_report,
        ledger=empty,
        sentences=None,
        all_content_satisfied=False,
    )
    score_controlled("url_dump", url_dump_report, empty, url_dump_judgment)

    unsupported_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=reference_report,
        ledger=empty,
        sentences=reference_sentences,
    )
    score_controlled(
        "fluent_unsupported", reference_report, empty, unsupported_judgment
    )

    frankenstein = frankenstein_judgment(
        suite=suite,
        world=world,
        report=reference_report,
        ledger=full,
        sentences=reference_sentences,
    )
    score_controlled("frankenstein", reference_report, full, frankenstein)

    unobserved_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=reference_report,
        ledger=no_ipx7,
        sentences=reference_sentences,
    )
    score_controlled(
        "unobserved_ipx7", reference_report, no_ipx7, unobserved_judgment
    )

    wrong_binding_key = ("K_WATT_CONTEXT", "audio_power", "P_WATT")
    wrong_binding_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=reference_report,
        ledger=full,
        sentences=reference_sentences,
        binding_url_overrides={wrong_binding_key: PASSIVE_URL},
        support_overrides={wrong_binding_key: "wrong_binding"},
    )
    score_controlled(
        "wrong_binding", reference_report, full, wrong_binding_judgment
    )

    contradicted_key = ("K_IPX7_SCOPE", "technical_scope", "P_IPX7_TEST")
    contradicted_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=reference_report,
        ledger=full,
        sentences=reference_sentences,
        support_overrides={contradicted_key: "contradicted"},
    )
    score_controlled(
        "contradicted_citation", reference_report, full, contradicted_judgment
    )

    fake_url = "http://localhost:7770/not-a-real-speaker.html"
    fabricated_report = (
        reference_report
        + f"\nUnrelated fabricated appendix citation: [fabricated]({fake_url})\n"
    )
    fabricated_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=fabricated_report,
        ledger=full,
        sentences=reference_sentences,
        url_audits=[{"url": fake_url, "status": "nonexistent_fabricated"}],
    )
    score_controlled(
        "fabricated_url", fabricated_report, full, fabricated_judgment
    )

    external_url = "https://example.com/audio-power"
    offworld_sentences = controlled_sentences()
    offworld_sentences["K_WATT_CONTEXT"] = (
        "Electrical watts alone do not establish loudness or clean output. "
        f"[external measurement]({external_url})"
    )
    offworld_report = controlled_report(offworld_sentences)
    offworld_key = ("K_WATT_CONTEXT", "audio_power", "P_WATT")
    offworld_judgment = construction_judgment(
        suite=suite,
        world=world,
        report=offworld_report,
        ledger=full,
        sentences=offworld_sentences,
        binding_url_overrides={offworld_key: external_url},
        url_audits=[{"url": external_url, "status": "real_off_world"}],
    )
    score_controlled(
        "real_off_world_only", offworld_report, full, offworld_judgment
    )

    real_report = (BASE / "real_run/report.md").read_text(encoding="utf-8")
    real_ledger = real_run_projection()
    real_judgment = evaluate_report_with_twm_mock(
        suite=suite,
        world=world,
        twm=twm,
        report=real_report,
        ledger=real_ledger,
    )
    _write_ledger(BASE / "real_run/observation-ledger-projection.json", real_ledger)
    _write_json(BASE / "real_run/judgment-twm-mock.json", real_judgment)
    real_score = score_grounded_research_coverage(
        suite=suite,
        world=world,
        report=real_report,
        ledger=real_ledger,
        judgment=real_judgment,
    )
    _write_json(BASE / "real_run/score.json", real_score)

    controlled_summary = {
        name: _scenario_summary(result) for name, result in scenarios.items()
    }
    real_summary = _scenario_summary(real_score)
    gates = {
        "oracle_full_pass": scenarios["oracle_reference"]["raw_grc"] == 1.0
        and scenarios["oracle_reference"]["full_pass"] == 1,
        "twm_mock_recovers_oracle": scenarios["twm_mock_oracle"]["raw_grc"] == 1.0
        and scenarios["twm_mock_oracle"]["full_pass"] == 1,
        "null_floor": scenarios["null"]["raw_grc"] == 0.0,
        "url_dump_floor": scenarios["url_dump"]["raw_grc"] == 0.0,
        "fluent_unsupported_separation": scenarios["fluent_unsupported"]["content_breadth"] == 1.0
        and scenarios["fluent_unsupported"]["raw_grc"] == 0.0,
        "alternative_route_equivalence": scenarios["oracle_alternative"]["raw_grc"]
        == scenarios["oracle_reference"]["raw_grc"],
        "frankenstein_rejected": not _check_pass(
            scenarios["frankenstein"], "K_DISTORTION_COMPARISON"
        ),
        "local_unobserved_effect": not _check_pass(
            scenarios["unobserved_ipx7"], "K_IPX7_SCOPE"
        )
        and _check_pass(scenarios["unobserved_ipx7"], "K_PRICE_FLARE"),
        "wrong_binding_rejected": not _check_pass(
            scenarios["wrong_binding"], "K_WATT_CONTEXT"
        ),
        "contradiction_is_critical": bool(
            scenarios["contradicted_citation"]["integrity"]["critical_errors"]
        ),
        "fabrication_gate": scenarios["fabricated_url"]["raw_grc"] == 1.0
        and scenarios["fabricated_url"]["official_grc"] == 0.0,
        "offworld_not_mislabeled_fabrication": not scenarios["real_off_world_only"]["integrity"]["fabricated_urls"]
        and bool(scenarios["real_off_world_only"]["integrity"]["real_off_world_urls"]),
        "real_report_partial_not_zero": 0.0 < real_score["raw_grc"] < real_score["content_breadth"],
        "no_pending_controlled": all(
            not result["pending_checks"]
            and not result["integrity"]["unadjudicated_off_registry_urls"]
            for result in scenarios.values()
        ),
    }
    summary = {
        "schema": "dra_single_task_vertical_slice_summary_v1",
        "task_id": TASK_ID,
        "suite_shape": {"facets": 5, "units": 8, "checks": 25},
        "controlled_scenarios": controlled_summary,
        "real_run": real_summary,
        "release_gates": gates,
        "all_release_gates_passed": all(gates.values()),
    }
    _write_json(BASE / "experiment-summary.json", summary)
    _write_text(BASE / "EXPERIMENT_REPORT.md", _experiment_markdown(summary))
    _write_text(BASE / "README.md", _readme())
    _write_json(BASE / "frozen-input-manifest.json", build_frozen_manifest(world, suite))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="print the machine-readable experiment summary",
    )
    args = parser.parse_args()
    summary = run()
    if args.print_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"built {TASK_ID}: gates="
            f"{sum(summary['release_gates'].values())}/{len(summary['release_gates'])}, "
            f"real_raw_grc={summary['real_run']['raw_grc']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
