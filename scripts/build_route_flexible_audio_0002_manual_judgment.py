#!/usr/bin/env python3
"""Build the auditable manual fallback judgment for the audio_0002 pilot.

This is intentionally task-specific. It is used only when the configured LLM
judge transports are unavailable, and stamps itself as manual pilot evidence.
Every report quote and positive page quote is asserted against the sealed input.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.observation_ledger import load_observation_ledger
from src.eval.route_flexible_scorer import canonical_sha256, validate_rubric


ORTIZAN_URL = (
    "http://localhost:7770/ortizan-portable-bluetooth-speaker-40w-loud-stereo-"
    "sound-ipx7-waterproof-bluetooth-speakers-with-bluetooth-5-0-dual-pairing-"
    "6600-mah-15h-playtime-power-bank-function-for-party.html"
)


REPORT_JUDGMENTS = {
    "E_FLARE_CORE": (
        "contradicted",
        "This is a fully auditable claim: it gives total continuous power and defines distortion as Total Harmonic Distortion plus Noise below 1%.",
        "The report preserves the numbers but incorrectly calls the power continuous and omits the missing THD+N test condition.",
    ),
    "E_ORTIZAN_CORE": (
        "satisfied",
        "The listing markets “40 W Loud Stereo Sound” and “Built with 2 × 20 W Max speaker” ([Ortizan product page, n.d.]). However, the phrase “Max” suggests peak or burst power rather than continuous RMS, and **no THD or distortion figure is provided**.",
        "The price, Max wording, and lack of quantitative distortion conditions are reported with bounded language.",
    ),
    "E_FLARE_DESIGN": (
        "satisfied",
        "While no polar plots are supplied, the claim is tied to a specific driver‑and‑radiator layout, which at least offers a physical basis for 360‑degree dispersion.",
        "The report attributes the design claim and preserves the absence of directivity measurements.",
    ),
    "E_ORTIZAN_DESIGN": (
        "satisfied",
        "Like the Flare 2, the 360‑degree claim is unsupported by directivity measurements, but the mention of dual passive radiators indicates a design attempt at omnidirectional low‑frequency radiation.",
        "The report attributes both labels and does not present them as measured directivity.",
    ),
    "E_FLARE_WATER": (
        "satisfied",
        "The IPX7 test (submersion in 1 m of water for 30 min) is referenced only by the rating; no independent certification or owner testing is provided in the sandbox corpus.",
        "The listing claim is separated from independent validation.",
    ),
    "E_ORTIZAN_WATER": (
        "satisfied",
        "Again, only the rating is given; no test protocol or user‑submitted water‑immersion evidence exists in the sandbox.",
        "The listing claim is separated from independent validation.",
    ),
    "E_IPX7_SCOPE": (
        "satisfied",
        "IPX7 is defined by the International Electrotechnical Commission (IEC) standard 60529: immersion in water up to 1 meter depth for 30 minutes. It certifies resistance to temporary submersion but does **not** test for protection against dust (the “X” placeholder) or against high‑pressure water jets.",
        "The report states a bounded immersion meaning and the unassigned particulate digit.",
    ),
    "E_FLARE_BATTERY": (
        "satisfied",
        "Crucially, a footnote warns: “Playback volume, lights, and BassUp will affect playtime” ([Anker Soundcore Flare 2 product page, n.d.]).",
        "The 12-hour claim and the listed operating caveats are reported.",
    ),
    "E_ORTIZAN_BATTERY": (
        "satisfied",
        "The fine print adds: “Playtime varies according to volume level and audio content” ([Ortizan product page, n.d.]).",
        "The 15-hour claim and its caveat are reported.",
    ),
    "E_FLARE_NO_HIRES": (
        "satisfied",
        "No mention of high‑resolution audio codecs (aptX, LDAC, etc.) appears.",
        "The report gives a listing-scoped negative finding.",
    ),
    "E_ORTIZAN_NO_HIRES": (
        "satisfied",
        "No hi‑res codec claim appears. Bluetooth 5.0 is mentioned, but no aptX, LDAC, or other high‑quality codecs are specified.",
        "The report gives a listing-scoped negative finding.",
    ),
    "A_WATT_DISTORTION": (
        "contradicted",
        "In contrast, the Flare 2’s <1% THD+N suggests that the amplifier and drivers were designed to stay within a linear range at the rated 20 W.",
        "This makes the exact inference the target forbids because the captured listing does not state the THD+N test condition.",
    ),
    "A_DESIGN_BOUNDARY": (
        "satisfied",
        "Neither listing supplies polar response graphs, so the actual sound field cannot be audited.",
        "The report refuses to convert the labels into demonstrated dispersion quality.",
    ),
    "A_WATER_BOUNDARY": (
        "satisfied",
        "All water‑resistance confidence must be inferred from the manufacturer’s self‑declaration.",
        "The report distinguishes declarations from independent validation and applies a bounded rating meaning.",
    ),
    "A_BATTERY_BOUNDARY": (
        "satisfied",
        "Without a standardized testing protocol (e.g., CEA‑2006‑B), these numbers are not directly comparable.",
        "The report preserves the operating caveats and refuses a direct nominal-hours comparison.",
    ),
    "A_HIRES_NOT_DECISIVE": (
        "satisfied",
        "Therefore, **neither speaker makes a hi‑res‑over‑Bluetooth claim**, and this factor does not influence the recommendation.",
        "The no-claim route is used, so an LDAC detour is unnecessary.",
    ),
    "A_FORUM_SCOPE": (
        "contradicted",
        "In the sandbox data, there is no forum or review content that validates water survival for either the Flare 2 or the Ortizan 40 W.",
        "The wording asserts corpus-wide absence even though the trace only licenses a bounded returned-results claim.",
    ),
    "A_DECISION": (
        "contradicted",
        "The single most decisive factor is the presence of a quantifiable distortion specification (THD + N < 1%), which gives the buyer a concrete performance benchmark and lowers the risk of unpleasant distortion at high volumes.",
        "The recommendation is explicit and constraint-aware, but its decisive rationale overclaims an unstated THD test condition.",
    ),
}


PAGE_QUOTES = {
    "E_ORTIZAN_CORE": [
        '"final_price":57.99',
        "Built with 2 x 20W Max speaker, Ortizan bluetooth speaker provides crystal clear sound and powerful bass without distortion even at maximum volume.",
    ],
    "E_ORTIZAN_DESIGN": [
        "You will like Ortizan’s true 360° stereo sound portable wireless speakers.",
        "And the dual passive radiators provide premium deep bass.",
    ],
    "E_ORTIZAN_WATER": [
        "Bluetooth speaker with IPX7 water resistance technology uses unbreakable TPU silicone material, perfect for pool party, travel.",
    ],
    "E_ORTIZAN_BATTERY": [
        "One full charge lets you play music for up to 15 hours(Playtime varies according to volume level and audio content).",
    ],
    "E_ORTIZAN_NO_HIRES": [],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubric", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prior-semantic-artifact", type=Path)
    args = parser.parse_args()

    rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
    validate_rubric(rubric)
    report = args.report.read_text(encoding="utf-8")
    ledger = load_observation_ledger(args.ledger)
    if not ledger.complete:
        raise ValueError(f"ledger incomplete: {ledger.withhold_reason_codes}")
    expected_ids = {str(target["target_id"]) for target in rubric["targets"]}
    if set(REPORT_JUDGMENTS) != expected_ids:
        raise ValueError("manual judgment target set does not match rubric")

    report_results = []
    for target_id in [str(target["target_id"]) for target in rubric["targets"]]:
        verdict, quote, reason = REPORT_JUDGMENTS[target_id]
        start = report.find(quote)
        if start < 0:
            raise ValueError(f"report quote not found for {target_id}")
        report_results.append(
            {
                "target_id": target_id,
                "verdict": verdict,
                "matched_quote": quote,
                "start": start,
                "end": start + len(quote),
                "reason": reason,
            }
        )

    event = next(
        event
        for event in ledger.events
        if event.canonical_url == ORTIZAN_URL
        and event.event_type == "fetch_body"
        and event.http_status == 200
    )
    body = event.visible_text(ledger.blob_loader)
    if body is None:
        raise ValueError("Ortizan observed body unavailable")
    evidence_results = []
    for target_id, quotes in PAGE_QUOTES.items():
        for quote in quotes:
            if quote not in body:
                raise ValueError(f"page quote not found for {target_id}: {quote}")
        evidence_results.append(
            {
                "target_id": target_id,
                "citation_url": ORTIZAN_URL,
                "verdict": "supported",
                "matched_evidence_quote": quotes[0] if quotes else None,
                "matched_evidence_quotes": quotes,
                "observed_content_sha256": event.content_sha256,
                "reason": (
                    "Complete observed page contains the exact listing evidence."
                    if quotes
                    else "Complete observed page was inspected for the bounded absence claim."
                ),
            }
        )

    prior = None
    if args.prior_semantic_artifact:
        prior = {
            "path": args.prior_semantic_artifact.as_posix(),
            "sha256": sha256(args.prior_semantic_artifact.read_bytes()).hexdigest(),
        }
    artifact = {
        "schema": "route_flexible_judgment_v1",
        "prompt_version": "manual_pilot_adjudication_v1",
        "rubric_sha256": canonical_sha256(rubric),
        "report_sha256": sha256(report.encode("utf-8")).hexdigest(),
        "run_id": ledger.run_id,
        "judge": {
            "provider": "manual_adjudication",
            "model": "codex_gpt5",
            "formal_eligible": False,
            "reason": "DeepSeek transport returned 502 and GPT-5.6 Luna returned 402 during the pilot.",
        },
        "prior_semantic_artifact": prior,
        "report_results": report_results,
        "evidence_results": evidence_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "targets": len(report_results)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
