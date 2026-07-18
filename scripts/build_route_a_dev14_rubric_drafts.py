#!/usr/bin/env python3
"""Build public-query-only Route A rubric drafts for the Dev-14 tasks.

The generated artifacts are intentionally ``draft`` and contain no evidence
URLs or known-support witnesses.  Evidence answerability is audited later;
this script only compiles necessary-but-not-sufficient obligations from the
public query and records whether the wording came from the Liu Yibo interview
or from an AI-led draft.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval.query_rubric_schema import (  # noqa: E402
    QueryRubric,
    canonical_json_sha256,
    compile_query_rubric,
)


DEFAULT_MANIFEST = ROOT / "data/calibration/route_a_dev14/task_manifest.json"
DEFAULT_OUTPUT = ROOT / "data/golden/query_rubric_drafts/route_a_dev14_20260716"
ALL_ROLES = ["shopping", "forums", "wiki"]


def atom(
    atom_id: str,
    atom_type: str,
    description: str,
    *,
    mention: list[list[str]],
    response: list[list[str]],
    evidence: list[list[str]],
    query_basis: str,
    required_roles: list[str] | None = None,
    minimum_sources: int = 1,
) -> dict[str, Any]:
    required_roles = required_roles or []
    return {
        "atom_id": atom_id,
        "atom_type": atom_type,
        "description": description,
        "required": True,
        "mention": {"all_term_groups": mention},
        "response_contract": {"all_term_groups": response},
        "evidence": {
            "acceptable_source_roles": ALL_ROLES,
            "required_source_roles": required_roles,
            "minimum_distinct_sources": minimum_sources,
            "observation_mode": "body",
            "track_discovery": True,
            "citation_binding_window_chars": 500,
            "evidence_window_chars": 1500,
            "relevance_contract": {"all_term_groups": evidence},
            "known_support": [],
        },
        "approved": False,
        "review_note": (
            f"Necessary-but-not-sufficient draft. Query basis: {query_basis}. "
            "Evidence answerability not assessed."
        ),
    }


SPECS: dict[str, list[dict[str, Any]]] = {
    "dr_cross_deep_0001": [
        atom(
            "R1_price_value",
            "dimension",
            "Judge whether higher-priced headphones provide meaningful value beyond brand premium.",
            mention=[["expensive", "premium", "price"], ["brand", "logo", "value"]],
            response=[["better", "worth", "value", "premium"], ["brand", "logo", "price"]],
            evidence=[["price", "premium", "expensive"], ["performance", "quality", "value"]],
            query_basis="Is the expensive stuff genuinely better or am I just paying for the logo?",
        ),
        atom(
            "R2_anc_claim",
            "dimension",
            "Judge whether active noise cancellation delivers a meaningful real-world benefit.",
            mention=[["active noise cancellation", "active noise cancelling", "ANC"]],
            response=[["active noise cancellation", "active noise cancelling", "ANC"], ["effective", "works", "benefit", "performance"]],
            evidence=[["active noise cancellation", "active noise cancelling", "ANC"], ["noise", "sound"]],
            query_basis="do things like active noise cancelling ... really do what the ads say?",
        ),
        atom(
            "R3_codec_claim",
            "dimension",
            "Judge whether advanced Bluetooth codecs provide a meaningful practical benefit.",
            mention=[["Bluetooth codec", "Bluetooth codecs", "aptX", "LDAC", "codec"]],
            response=[["codec", "aptX", "LDAC"], ["audible", "benefit", "difference", "effective"]],
            evidence=[["Bluetooth", "codec", "aptX", "LDAC"], ["audio", "sound", "quality"]],
            query_basis="the fancy Bluetooth codecs really do what the ads say?",
        ),
        atom(
            "R4_recommendations",
            "synthesis",
            "Recommend several headphones at different prices and justify them for bus and noisy-office use.",
            mention=[["recommend", "pick", "choice", "buy"], ["price", "budget", "$"], ["bus", "office", "commute", "noisy"]],
            response=[["recommend", "pick", "buy", "choice"], ["because", "reason", "suit", "fit"], ["bus", "office", "commute", "noise"]],
            evidence=[["headphone", "headphones", "earbuds"], ["noise", "ANC", "isolation"], ["price", "$", "cost"]],
            query_basis="a few solid picks at different prices and the reasons behind them; bus and noisy office",
        ),
    ],
    "dr_cross_deep_0002": [
        atom(
            "R1_coffee_claims",
            "dimension",
            "Verify the stated coffee claims, including dark-roast caffeine and how quickly beans go stale.",
            mention=[["dark roast", "dark-roast"], ["caffeine"], ["stale", "freshness", "fresh"]],
            response=[["dark roast", "dark-roast"], ["caffeine"], ["stale", "freshness", "weeks"]],
            evidence=[["coffee", "beans"], ["caffeine", "stale", "freshness"]],
            query_basis="whether dark roast really has more caffeine or beans really go stale in weeks",
        ),
        atom(
            "R2_beginner_options",
            "option",
            "Compare the beginner implications of the coffee and equipment options raised in the query.",
            mention=[["single-origin", "single origin", "blend"], ["whole bean", "whole-bean", "ground coffee"], ["moka", "stovetop", "espresso pot"]],
            response=[["beginner", "starting", "start"], ["single-origin", "blend", "whole bean", "moka", "stovetop"]],
            evidence=[["coffee", "bean", "moka", "stovetop"], ["beginner", "brew", "price", "equipment"]],
            query_basis="single-origin, supermarket blend, whole-bean, and stovetop espresso pot alternatives",
        ),
        atom(
            "R3_brewing_tutorial",
            "dimension",
            "Provide an actionable beginner brewing procedure rather than only naming equipment.",
            mention=[["brew", "brewing", "prepare", "preparation"], ["step", "method", "ratio", "water"]],
            response=[["brew", "brewing", "prepare"], ["step", "ratio", "water", "grind", "time"]],
            evidence=[["coffee", "brew", "brewing"], ["water", "grind", "ratio", "time", "method"]],
            query_basis="what would you honestly start a beginner on (human interpretation: include a usable tutorial)",
        ),
        atom(
            "R4_beginner_recommendation",
            "synthesis",
            "Recommend a beginner setup while accounting for learning burden and abandonment risk.",
            mention=[["recommend", "start", "beginner", "buy"], ["abandon", "unused", "learning", "effort", "gear"]],
            response=[["recommend", "start", "buy", "choice"], ["beginner"], ["abandon", "unused", "simple", "effort", "learning"]],
            evidence=[["coffee", "equipment", "gear"], ["beginner", "easy", "simple", "workflow"]],
            query_basis="without me buying gear I'll abandon by spring",
        ),
    ],
    "dr_cross_deep_0003": [
        atom(
            "R1_earbud_anc_physics",
            "dimension",
            "Judge whether earbud noise cancellation is physically and necessarily weaker than over-ear ANC.",
            mention=[["earbud", "earbuds", "in-ear"], ["over-ear", "big cups", "headphone"], ["ANC", "noise cancellation", "noise cancelling"]],
            response=[["earbud", "in-ear"], ["over-ear", "headphone"], ["physical", "necessarily", "always", "depends", "weaker", "better"]],
            evidence=[["earbud", "over-ear"], ["ANC", "noise cancellation", "seal", "isolation"]],
            query_basis="small earbuds can't physically work as well as big cups. Is that true?",
        ),
        atom(
            "R2_budget_split",
            "option",
            "Explain a realistic split of the $250 budget between wireless earbuds and a rugged portable speaker.",
            mention=[["$250", "250"], ["earbud", "earbuds"], ["speaker"]],
            response=[["budget", "$250", "250"], ["earbud", "earbuds"], ["speaker"], ["split", "allocate", "$", "cost"]],
            evidence=[["earbud", "earbuds"], ["speaker"], ["price", "$", "cost"]],
            query_basis="the same money could cover both; worry that splitting the budget means mediocrity",
        ),
        atom(
            "R3_plan_tradeoff",
            "dimension",
            "Compare one good over-ear ANC headphone against earbuds plus speaker for office and camping use.",
            mention=[["over-ear", "headphone"], ["earbud", "earbuds"], ["speaker"], ["office", "camping"]],
            response=[["trade-off", "tradeoff", "compare", "versus", "option"], ["office"], ["camping"], ["over-ear", "headphone"], ["earbud", "speaker"]],
            evidence=[["headphone", "over-ear", "earbud"], ["speaker"], ["office", "camping", "portable", "noise"]],
            query_basis="Walk me through the trade-off between the two plans",
        ),
        atom(
            "R4_final_purchase",
            "synthesis",
            "Make a clear final purchase recommendation within the $250 budget.",
            mention=[["recommend", "buy", "purchase", "choose"], ["$250", "250", "budget"]],
            response=[["recommend", "buy", "purchase", "choose"], ["$250", "250", "budget"]],
            evidence=[["price", "$", "cost"], ["headphone", "earbud", "speaker"]],
            query_basis="what you'd actually buy with my $250",
        ),
    ],
    "dr_cross_deep_0004": [
        atom(
            "R1_camera_options_tradeoff",
            "option",
            "Compare realistic first-camera options, including new mirrorless and used DSLR kits, under the risk of rapid obsolescence.",
            mention=[["mirrorless"], ["DSLR"], ["used", "second-hand", "secondhand"], ["trade-off", "tradeoff", "compare", "option"]],
            response=[["mirrorless"], ["DSLR"], ["new", "used"], ["trade-off", "tradeoff", "advantage", "disadvantage", "option"], ["outgrow", "upgrade", "future", "long-term"]],
            evidence=[["camera", "mirrorless", "DSLR"], ["lens", "kit", "used", "price"]],
            query_basis="new mirrorless ... used DSLR kit ... realistic options ... trade-offs; don't want to outgrow it",
        ),
        atom(
            "R2_photographer_advice",
            "source_role",
            "Report advice from actual photographers to first-time buyers.",
            mention=[["photographer", "photographers", "owner", "user"], ["beginner", "first camera", "first setup", "newcomer"]],
            response=[["photographer", "photographers", "owner", "user"], ["advice", "recommend", "regret", "learned"]],
            evidence=[["photographer", "photographers", "owner", "user"], ["beginner", "first camera", "advice"]],
            query_basis="what do actual photographers tell beginners",
            required_roles=["forums"],
        ),
        atom(
            "R3_800_plan",
            "synthesis",
            "Recommend a concrete first photography setup and budget allocation around $800.",
            mention=[["$800", "800", "budget"], ["recommend", "buy", "setup", "choose"]],
            response=[["recommend", "buy", "choose", "setup"], ["$800", "800", "budget"], ["camera", "lens", "kit"]],
            evidence=[["camera", "lens", "kit"], ["price", "$", "cost"]],
            query_basis="what would you do with $800?",
        ),
    ],
    "dr_cross_deep_0005": [
        atom(
            "R1_speaker_claims",
            "dimension",
            "Evaluate the physical meaning and marketing limits of the listed portable-speaker claims, including high-volume distortion.",
            mention=[["40 watts", "40W", "watt"], ["360", "360-degree"], ["IPX7", "waterproof"], ["passive radiator", "bass"], ["hi-res", "Bluetooth"]],
            response=[["physical", "real", "meaningful", "marketing"], ["watt", "360", "IPX7", "passive radiator", "hi-res"], ["distortion", "distort", "volume"]],
            evidence=[["speaker", "portable speaker"], ["watt", "360", "IPX7", "passive radiator", "hi-res", "distortion"]],
            query_basis="Which of these claims mean something physically real ... which are marketing?; distorted when turned up",
        ),
        atom(
            "R2_pool_beach_owners",
            "source_role",
            "Assess whether owners who used speakers at pools or beaches corroborate the claims.",
            mention=[["owner", "owners", "user", "users"], ["pool", "beach"], ["claim", "waterproof", "bass", "performance"]],
            response=[["owner", "owners", "user", "users"], ["pool", "beach"], ["confirm", "support", "hold up", "failed", "experience"]],
            evidence=[["pool", "beach", "water"], ["owner", "user", "experience"]],
            query_basis="do owners who actually took theirs to the pool or beach back any of it up?",
            required_roles=["forums"],
        ),
        atom(
            "R3_speaker_recommendation",
            "synthesis",
            "Recommend a portable speaker whose relevant claims hold in practice.",
            mention=[["recommend", "pick", "buy", "choice"], ["speaker"]],
            response=[["recommend", "pick", "buy", "choice"], ["speaker"], ["claim", "performance", "holds", "reliable"]],
            evidence=[["speaker"], ["performance", "waterproof", "distortion", "bass"]],
            query_basis="Point me at a speaker whose claims actually hold",
        ),
    ],
    "dr_cross_deep_0006": [
        atom(
            "R1_decay_verdict",
            "dimension",
            "Judge whether true-wireless battery and connection decay are format-level inevitabilities or amplified anecdotes.",
            mention=[["battery"], ["connection", "disconnect", "dropout", "one side"], ["inevitable", "inevitability", "horror stories", "anecdote", "disposable"]],
            response=[["battery"], ["connection", "disconnect", "dropout", "one side"], ["inevitable", "common", "rare", "anecdote", "disposable", "depends"]],
            evidence=[["true wireless", "wireless earbud", "TWS", "earbud"], ["battery", "connection", "dropout", "disconnect"]],
            query_basis="physical inevitability of the format or just a few loud horror stories?; honest verdict",
        ),
        atom(
            "R2_ratings_community_reconcile",
            "dimension",
            "Reconcile near-five-star product ratings with hobbyist reports that true-wireless earbuds are disposable.",
            mention=[["rating", "ratings", "stars", "reviews"], ["hobbyist", "community", "enthusiast"], ["disposable", "battery", "connection"]],
            response=[["rating", "ratings", "reviews", "stars"], ["community", "hobbyist", "enthusiast"], ["difference", "reconcile", "explain", "why", "conflict"]],
            evidence=[["rating", "ratings", "reviews"], ["community", "hobbyist", "owner"], ["battery", "connection", "durability"]],
            query_basis="Those are two totally different pictures and I don't know which to believe",
            required_roles=["shopping", "forums"],
            minimum_sources=2,
        ),
        atom(
            "R3_durable_pair",
            "synthesis",
            "If recommending true wireless, identify the pair most likely to hold up and explain why.",
            mention=[["recommend", "pair", "buy", "choice"], ["durable", "holds up", "last", "longevity"]],
            response=[["recommend", "pair", "buy", "choice"], ["durable", "holds up", "last", "longevity"], ["because", "reason", "evidence"]],
            evidence=[["earbud", "earbuds", "TWS"], ["durability", "battery", "connection", "longevity"]],
            query_basis="which pair holds up best if I go ahead",
        ),
    ],
    "dr_cross_deep_0007": [
        atom(
            "R1_failure_modes",
            "dimension",
            "Explain the major long-term headphone failure modes.",
            mention=[["headband", "earpad", "ear pad", "cable", "battery"], ["fail", "failure", "crack", "flake", "wear", "break"]],
            response=[["headband", "earpad", "ear pad", "cable", "battery"], ["fail", "failure", "crack", "flake", "wear", "break"], ["cause", "because", "mechanism", "reason"]],
            evidence=[["headphone", "headphones"], ["failure", "wear", "battery", "headband", "earpad", "cable"]],
            query_basis="What actually kills headphones over the years?",
        ),
        atom(
            "R2_wireless_battery",
            "dimension",
            "Judge whether a nonreplaceable battery makes wireless headphones unsuitable for decade-scale use.",
            mention=[["wireless"], ["battery"], ["decade", "ten years", "2036", "long-term", "longevity"]],
            response=[["wireless"], ["battery"], ["limit", "doom", "replace", "lifespan", "longevity"]],
            evidence=[["wireless headphone", "wireless"], ["battery", "cycle", "degradation", "replacement"]],
            query_basis="does going wireless doom me from the start because of the battery?",
        ),
        atom(
            "R3_replaceable_parts",
            "dimension",
            "Judge whether replaceable pads and cables materially improve service life.",
            mention=[["replaceable"], ["pad", "pads", "earpad", "earpads"], ["cable", "cables"]],
            response=[["replaceable"], ["pad", "earpad"], ["cable"], ["matter", "lifespan", "repair", "longevity", "gimmick"]],
            evidence=[["headphone"], ["replaceable", "repair"], ["pad", "cable"]],
            query_basis="Do replaceable pads and cables genuinely matter or is that a spec-sheet gimmick?",
        ),
        atom(
            "R4_decade_owner_experience",
            "source_role",
            "Report long-term owner experience with headphones surviving roughly a decade of daily use.",
            mention=[["owner", "owners", "user", "users"], ["decade", "ten years", "10 years", "long-term"], ["daily", "regular", "years"]],
            response=[["owner", "owners", "user", "users"], ["decade", "ten years", "10 years", "long-term"], ["survived", "lasted", "still works", "daily"]],
            evidence=[["owner", "user"], ["headphone"], ["years", "decade", "long-term", "daily"]],
            query_basis="what long-term owners say survived a decade of daily use",
            required_roles=["forums"],
        ),
        atom(
            "R5_longevity_pick",
            "synthesis",
            "Recommend one over-ear headphone consistent with the decade-long longevity goal.",
            mention=[["recommend", "pick", "buy", "bet"], ["over-ear", "headphone"], ["decade", "2036", "long-term", "longevity"]],
            response=[["recommend", "pick", "buy", "choice"], ["headphone", "over-ear"], ["decade", "2036", "long-term", "last", "repair"]],
            evidence=[["headphone", "over-ear"], ["durable", "repair", "replaceable", "years", "longevity"]],
            query_basis="the one pair you'd bet on; still wearing in 2036",
        ),
    ],
    "dr_cross_deep_0008": [
        atom(
            "R1_price_cutoff",
            "dimension",
            "Identify and justify the price region where true-wireless sound-quality gains materially diminish.",
            mention=[["price", "$", "cost"], ["sound", "audio quality"], ["cutoff", "diminishing", "stop", "plateau"]],
            response=[["price", "$", "cost"], ["sound", "audio quality"], ["cutoff", "diminishing return", "plateau", "stop"]],
            evidence=[["earbud", "true wireless", "TWS"], ["price", "cost"], ["sound", "audio quality"]],
            query_basis="where the money actually stops buying sound; Is there a real cutoff price?",
        ),
        atom(
            "R2_codec_cutoff",
            "dimension",
            "Judge whether aptX or other advanced codecs shift the practical cutoff and under what listening conditions.",
            mention=[["aptX", "codec", "codecs"], ["cutoff", "price", "audible", "hear", "difference"]],
            response=[["aptX", "codec"], ["audible", "hear", "difference", "benefit"], ["gear", "device", "condition", "environment", "bus"]],
            evidence=[["aptX", "codec", "Bluetooth"], ["audio", "sound", "quality", "audible"]],
            query_basis="does stuff like aptX ... shift it, or is that only audible on gear I'll never own?",
        ),
        atom(
            "R3_cross_price_owners",
            "source_role",
            "Report experience from owners who have used both cheap and flagship earbuds.",
            mention=[["owner", "owners", "user", "users"], ["cheap", "$30", "budget"], ["flagship", "$280", "premium", "expensive"]],
            response=[["owner", "owners", "user", "users"], ["cheap", "budget"], ["flagship", "premium", "expensive"], ["compare", "difference", "same", "better"]],
            evidence=[["owner", "user"], ["cheap", "budget"], ["flagship", "premium"]],
            query_basis="Owners of both cheap and flagship buds must have opinions here",
            required_roles=["forums"],
        ),
        atom(
            "R4_stop_price",
            "synthesis",
            "State the price at which this buyer should stop spending more.",
            mention=[["price", "$", "budget"], ["stop", "cap", "limit", "maximum"]],
            response=[["price", "$", "budget"], ["stop", "cap", "limit", "maximum", "spend"]],
            evidence=[["earbud", "earbuds"], ["price", "$", "cost"], ["performance", "sound", "value"]],
            query_basis="Tell me the price you'd stop at",
        ),
        atom(
            "R5_pair_at_budget",
            "synthesis",
            "Recommend a true-wireless earbud near the stated stopping price.",
            mention=[["recommend", "pair", "pick", "buy"], ["earbud", "earbuds", "true wireless"]],
            response=[["recommend", "pair", "pick", "buy"], ["earbud", "earbuds"], ["price", "$", "budget", "value"]],
            evidence=[["earbud", "earbuds"], ["price", "$", "value", "sound"]],
            query_basis="the pair to get there",
        ),
    ],
    "dr_cross_deep_0009": [
        atom(
            "R1_wired_to_wireless_history",
            "dimension",
            "Explain the transition from headphone jacks to predominantly wireless listening.",
            mention=[["headphone jack", "jack", "wired", "cable"], ["wireless", "Bluetooth"], ["history", "transition", "evolution", "shift"]],
            response=[["wired", "headphone jack", "jack"], ["wireless", "Bluetooth"], ["transition", "shift", "history", "because", "adoption"]],
            evidence=[["headphone jack", "wired"], ["Bluetooth", "wireless"], ["history", "adoption", "transition"]],
            query_basis="How did we get from headphone jacks to everything being wireless?",
            required_roles=["wiki"],
        ),
        atom(
            "R2_bluetooth_audio_mechanism",
            "dimension",
            "Explain what happens to audio when it is transmitted over Bluetooth.",
            mention=[["Bluetooth"], ["audio", "music", "sound"], ["codec", "compress", "compression", "encode", "bitrate"]],
            response=[["Bluetooth"], ["audio", "music", "sound"], ["codec", "compress", "encode", "bitrate", "transmit"]],
            evidence=[["Bluetooth"], ["audio", "codec", "compression", "bitrate"]],
            query_basis="what actually happens to the audio when it goes over Bluetooth",
            required_roles=["wiki"],
        ),
        atom(
            "R3_cable_sound_verdict",
            "dimension",
            "Judge whether wired headphones still have a meaningful sound-quality advantage today.",
            mention=[["wired", "cable"], ["wireless", "Bluetooth"], ["sound", "audio quality", "music"]],
            response=[["wired", "cable"], ["Bluetooth", "wireless"], ["better", "difference", "loss", "quality", "today", "current"]],
            evidence=[["wired", "cable"], ["Bluetooth", "wireless"], ["audio", "quality", "codec"]],
            query_basis="is the cable crowd still right today?",
        ),
        atom(
            "R4_buyer_regret",
            "source_role",
            "Compare current buyer regrets or satisfaction after choosing wired versus wireless.",
            mention=[["buyer", "buyers", "owner", "owners", "user"], ["wired", "cable"], ["wireless", "Bluetooth"], ["regret", "satisfied", "prefer"]],
            response=[["buyer", "owner", "user"], ["wired", "cable"], ["wireless", "Bluetooth"], ["regret", "satisfied", "prefer", "experience"]],
            evidence=[["owner", "buyer", "user"], ["wired", "wireless"], ["regret", "experience", "prefer"]],
            query_basis="whether current buyers regret going one way or the other",
            required_roles=["forums"],
        ),
        atom(
            "R5_starter_pair",
            "synthesis",
            "Recommend a starter headphone consistent with the wired-versus-wireless analysis.",
            mention=[["recommend", "start", "pick", "buy"], ["headphone", "pair"]],
            response=[["recommend", "start", "pick", "buy"], ["headphone", "pair"], ["wired", "wireless", "Bluetooth", "cable"]],
            evidence=[["headphone"], ["wired", "wireless", "Bluetooth"], ["price", "performance", "features"]],
            query_basis="which pair you'd start me on",
        ),
    ],
    "dr_cross_deep_0010": [
        atom(
            "R1_glasses_seal_claim",
            "dimension",
            "Judge whether eyeglass arms materially degrade over-ear seal and noise-control performance.",
            mention=[["glasses", "eyeglass"], ["seal"], ["noise cancellation", "noise cancelling", "ANC", "isolation"]],
            response=[["glasses", "eyeglass"], ["seal"], ["degrade", "break", "reduce", "effect", "overblown", "depends"]],
            evidence=[["glasses", "eyeglass"], ["seal"], ["noise", "ANC", "isolation"]],
            query_basis="glasses arms break the seal so the noise cancelling stops working properly. Is that a real physical problem or overblown?",
        ),
        atom(
            "R2_form_factor_tradeoff",
            "option",
            "Compare over-ear, on-ear, and earbud options for engine noise, ten-hour comfort, glasses fit, and small-bag portability.",
            mention=[["over-ear"], ["on-ear"], ["earbud", "earbuds", "in-ear"], ["glasses"], ["ten hours", "10 hours", "long-haul", "flight"], ["bag", "portable", "compact"]],
            response=[["over-ear"], ["on-ear"], ["earbud", "in-ear"], ["comfort", "fit", "seal"], ["bag", "portable", "compact"], ["engine", "noise", "flight"]],
            evidence=[["over-ear", "on-ear", "earbud"], ["noise", "comfort", "fit", "portable", "battery"]],
            query_basis="Would compact on-ears or good earbuds serve a glasses wearer better for ten hours in the air?; small backpack",
        ),
        atom(
            "R3_frequent_flyer_experience",
            "source_role",
            "Report experience from frequent flyers who wear glasses.",
            mention=[["frequent flyer", "flyer", "traveler", "passenger"], ["glasses", "eyeglass"], ["experience", "owner", "user"]],
            response=[["frequent flyer", "flyer", "traveler", "passenger"], ["glasses", "eyeglass"], ["experience", "reported", "found", "comfort", "seal"]],
            evidence=[["flyer", "flight", "traveler"], ["glasses"], ["experience", "comfort", "seal"]],
            query_basis="hear from frequent flyers who wear glasses too",
            required_roles=["forums"],
        ),
        atom(
            "R4_flight_recommendation",
            "synthesis",
            "Recommend an option that fits both the user's small bag and glasses-wearing face for long-haul flights.",
            mention=[["recommend", "pick", "buy", "choice"], ["bag", "portable", "compact"], ["glasses", "fit", "face"], ["flight", "long-haul", "ten hours"]],
            response=[["recommend", "pick", "buy", "choice"], ["bag", "portable", "compact"], ["glasses", "fit", "seal"], ["flight", "long-haul", "comfort"]],
            evidence=[["headphone", "earbud", "on-ear", "over-ear"], ["portable", "comfort", "fit", "noise"]],
            query_basis="a pick that fits my bag and my face",
        ),
    ],
    "dr_cross_deep_0011": [
        atom(
            "R1_keyboard_plan_tradeoff",
            "option",
            "Compare a cheaper hot-swappable board plus later switch upgrades against spending the full budget on a known prebuilt.",
            mention=[["hot-swappable", "hot swappable", "hotswap"], ["prebuilt", "pre-built"], ["switch", "switches"], ["$120", "120", "budget"]],
            response=[["hot-swappable", "hotswap"], ["prebuilt"], ["trade-off", "tradeoff", "compare", "advantage", "disadvantage"], ["$120", "120", "budget"]],
            evidence=[["keyboard"], ["hot-swappable", "hotswap", "prebuilt"], ["price", "$", "switch"]],
            query_basis="cheaper hot-swappable board ... or blowing the whole budget on a well-known prebuilt",
        ),
        atom(
            "R2_switch_fit",
            "dimension",
            "Compare linear and tactile switches for office writing and shooter gaming.",
            mention=[["linear"], ["tactile"], ["office", "writing", "typing"], ["shooter", "gaming", "game"]],
            response=[["linear"], ["tactile"], ["typing", "writing", "office"], ["gaming", "shooter"], ["fit", "prefer", "trade-off", "recommend"]],
            evidence=[["switch", "linear", "tactile"], ["typing", "gaming", "actuation", "feel"]],
            query_basis="whether linear or tactile switches suit someone like me",
        ),
        atom(
            "R3_120_priorities",
            "dimension",
            "Explain which keyboard features and quality factors matter at roughly $120 for the stated mixed use.",
            mention=[["$120", "120", "budget", "price"], ["matter", "priority", "important", "feature", "quality"]],
            response=[["$120", "120", "budget", "price"], ["matter", "priority", "important", "feature", "quality"], ["typing", "office", "gaming", "shooter"]],
            evidence=[["keyboard"], ["price", "$", "feature", "quality"], ["typing", "gaming"]],
            query_basis="What actually matters at this price",
        ),
        atom(
            "R4_owner_regrets",
            "source_role",
            "Report what buyers of the competing options later regretted.",
            mention=[["owner", "buyer", "people", "user"], ["regret", "regretted"], ["hot-swappable", "hotswap", "prebuilt", "linear", "tactile"]],
            response=[["owner", "buyer", "user"], ["regret", "regretted", "wish", "problem"], ["hot-swappable", "hotswap", "prebuilt", "linear", "tactile"]],
            evidence=[["owner", "buyer", "user"], ["keyboard", "switch"], ["regret", "problem", "experience"]],
            query_basis="what people who bought each option ended up regretting",
            required_roles=["forums"],
        ),
        atom(
            "R5_cart_recommendation",
            "synthesis",
            "Recommend a concrete keyboard purchase plan within $120 for office writing and shooters.",
            mention=[["recommend", "cart", "buy", "pick", "choose"], ["$120", "120", "budget"], ["office", "writing", "typing"], ["shooter", "gaming"]],
            response=[["recommend", "cart", "buy", "pick", "choose"], ["$120", "120", "budget"], ["keyboard", "switch"], ["typing", "office", "gaming", "shooter"]],
            evidence=[["keyboard", "switch"], ["price", "$"], ["typing", "gaming"]],
            query_basis="what would you put in the cart if you were me?",
        ),
    ],
    "dr_cross_deep_0012": [
        atom(
            "R1_polling_rate",
            "dimension",
            "Judge the physical and human-perceptible advantage of 8000 Hz keyboard polling.",
            mention=[["8000Hz", "8000 Hz", "8K", "polling rate"], ["perceptible", "noticeable", "latency", "advantage"]],
            response=[["8000Hz", "8000 Hz", "8K", "polling"], ["latency", "perceptible", "noticeable", "advantage", "difference"]],
            evidence=[["keyboard"], ["polling", "8000", "latency"]],
            query_basis="8000Hz polling ... physically real advantages ... humanly perceptible",
        ),
        atom(
            "R2_optical_debounce",
            "dimension",
            "Judge the physical and human-perceptible advantage of optical switches and near-zero debounce.",
            mention=[["optical switch", "optical switches", "optical"], ["debounce", "debounce delay"], ["perceptible", "noticeable", "latency", "advantage"]],
            response=[["optical"], ["debounce"], ["latency", "perceptible", "noticeable", "advantage", "difference"]],
            evidence=[["optical switch", "optical"], ["debounce", "latency"]],
            query_basis="optical switches with supposedly zero debounce delay",
        ),
        atom(
            "R3_n_key_rollover",
            "dimension",
            "Judge the practical advantage of full N-key rollover beyond a sufficient baseline.",
            mention=[["N-key rollover", "N key rollover", "NKRO", "rollover"], ["advantage", "matter", "useful", "perceptible"]],
            response=[["N-key rollover", "NKRO", "rollover"], ["advantage", "matter", "useful", "need", "baseline"]],
            evidence=[["keyboard"], ["N-key rollover", "NKRO", "rollover"]],
            query_basis="full N-key rollover like they're life-changing",
        ),
        atom(
            "R4_aim_claim_reconcile",
            "dimension",
            "Reconcile buyer reports of improved aim with physical limits and placebo explanations.",
            mention=[["buyer", "review", "reviews", "people", "user"], ["aim"], ["placebo", "perceptible", "physical", "noticeable"]],
            response=[["aim"], ["review", "buyer", "user"], ["placebo", "perceptible", "physical", "confound", "explain"]],
            evidence=[["review", "buyer", "user"], ["aim", "performance"], ["polling", "latency", "placebo"]],
            query_basis="buyer reviews ... swearing their aim got better; which are placebo",
            required_roles=["shopping"],
        ),
        atom(
            "R5_sensible_board",
            "synthesis",
            "Recommend a sensibly priced keyboard that includes the features judged to matter.",
            mention=[["recommend", "board", "keyboard", "buy", "pick"], ["price", "priced", "budget", "value"], ["feature", "matter", "useful"]],
            response=[["recommend", "buy", "pick"], ["keyboard", "board"], ["price", "budget", "value"], ["feature", "polling", "optical", "rollover", "NKRO"]],
            evidence=[["keyboard", "board"], ["price", "$", "feature"], ["polling", "optical", "rollover"]],
            query_basis="a sensibly priced board that already has the ones that genuinely matter",
        ),
    ],
    "dr_cross_deep_0013": [
        atom(
            "R1_ratings_hobbyist_reconcile",
            "dimension",
            "Reconcile near-five-star ratings with hobbyist reports of double typing and warranty problems.",
            mention=[["rating", "ratings", "stars", "reviews"], ["hobbyist", "enthusiast", "community"], ["double-typing", "double typing", "chatter"], ["warranty"]],
            response=[["rating", "ratings", "stars", "reviews"], ["hobbyist", "enthusiast", "community"], ["honeymoon", "snobbery", "bias", "explain", "difference", "failure"]],
            evidence=[["rating", "review"], ["hobbyist", "community", "owner"], ["double typing", "chatter", "warranty"]],
            query_basis="Are those star ratings just honeymoon-period impressions ... or is the hate pure snobbery?",
            required_roles=["shopping", "forums"],
            minimum_sources=2,
        ),
        atom(
            "R2_chatter_cause",
            "dimension",
            "Explain what causes keyboard double typing or chatter.",
            mention=[["double-typing", "double typing", "chatter"], ["cause", "causes", "because", "mechanism"]],
            response=[["double-typing", "double typing", "chatter"], ["cause", "because", "mechanism", "contact", "switch", "firmware"]],
            evidence=[["keyboard", "switch"], ["double typing", "chatter"], ["cause", "contact", "debounce", "firmware"]],
            query_basis="what actually causes that double-typing",
        ),
        atom(
            "R3_chatter_fixability",
            "dimension",
            "Judge whether double typing is fixable and what repair limits apply.",
            mention=[["double-typing", "double typing", "chatter"], ["fix", "fixable", "repair", "replace"]],
            response=[["double-typing", "double typing", "chatter"], ["fix", "fixable", "repair", "replace", "temporary", "permanent"]],
            evidence=[["keyboard", "switch"], ["chatter", "double typing"], ["fix", "repair", "replace"]],
            query_basis="whether it's fixable",
        ),
        atom(
            "R5_keyboard_recommendation",
            "synthesis",
            "Recommend a keyboard appropriate for professional typing if the reliability concerns are supported, explicitly accounting for chatter-related work disruption.",
            mention=[["recommend", "buy", "pick", "choose"], ["keyboard", "board"], ["reliable", "chatter", "double typing"], ["work", "professional", "typing"]],
            response=[["recommend", "buy", "pick", "choose"], ["keyboard", "board"], ["reliable", "chatter", "double typing"], ["typing", "work", "professional"]],
            evidence=[["keyboard", "board"], ["reliability", "chatter", "switch", "warranty"]],
            query_basis="what I should buy if the fears are founded; I type for a living",
        ),
    ],
    "dr_cross_deep_0014": [
        atom(
            "R1_keyboard_failure_modes",
            "dimension",
            "Explain which components and failure modes determine real keyboard longevity.",
            mention=[["switch", "switches"], ["keycap", "keycaps"], ["stabilizer", "stabilizers"], ["circuit board", "PCB"], ["cable"]],
            response=[["switch", "keycap", "stabilizer", "PCB", "circuit board", "cable"], ["fail", "failure", "wear", "break", "longevity", "first"]],
            evidence=[["keyboard"], ["switch", "keycap", "stabilizer", "PCB", "cable"], ["failure", "wear", "durability"]],
            query_basis="whether it's actually the keycaps, stabilizers, or circuit board that give out first; prior stuck key and cable failures",
        ),
        atom(
            "R2_keystroke_rating",
            "dimension",
            "Judge how much 50- or 100-million-keystroke switch ratings predict real-world durability.",
            mention=[["50 million", "100 million", "million keystroke", "keystroke rating"], ["real world", "real-world", "meaning", "predict", "durability"]],
            response=[["million", "keystroke", "rating"], ["real world", "real-world", "meaning", "predict", "limit", "durability"]],
            evidence=[["switch"], ["keystroke", "million", "rating"], ["durability", "test", "failure"]],
            query_basis="Switches advertise 50 or 100 million keystroke ratings ... whether that number means anything in real life",
        ),
        atom(
            "R3_long_term_owners",
            "source_role",
            "Report which keyboards long-term owners say survived years of heavy daily use.",
            mention=[["owner", "owners", "user", "users"], ["years", "long-term", "decade"], ["daily", "abuse", "heavy use", "still going"]],
            response=[["owner", "owners", "user", "users"], ["years", "long-term", "decade"], ["survived", "still going", "lasted", "daily"]],
            evidence=[["owner", "user"], ["keyboard"], ["years", "long-term", "daily", "abuse"]],
            query_basis="Which boards do long-term owners say are still going strong after years of daily abuse?",
            required_roles=["forums"],
        ),
        atom(
            "R5_bifl_keyboard",
            "synthesis",
            "Recommend a genuine buy-it-for-life keyboard consistent with the failure-mode evidence and decade-long goal.",
            mention=[["recommend", "pick", "buy", "choose"], ["keyboard", "board"], ["buy-it-for-life", "decade", "long-term", "durable"]],
            response=[["recommend", "pick", "buy", "choose"], ["keyboard", "board"], ["buy-it-for-life", "decade", "long-term", "durable", "repair"]],
            evidence=[["keyboard", "board"], ["durability", "repair", "replaceable", "years"]],
            query_basis="what would you pick as the genuine buy-it-for-life option?",
        ),
    ],
}


HUMAN_DRAFT_TASKS = {f"dr_cross_deep_{i:04d}" for i in range(1, 8)}


def build(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = manifest.get("tasks") or []
    task_ids = [str(task.get("task_id")) for task in tasks]
    if set(task_ids) != set(SPECS):
        raise SystemExit(
            "task/spec mismatch: "
            + json.dumps(
                {
                    "missing_specs": sorted(set(task_ids) - set(SPECS)),
                    "extra_specs": sorted(set(SPECS) - set(task_ids)),
                },
                ensure_ascii=False,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(task["task_id"])
        mode = (
            "human_interviewed_unresolved_plus_ai_compilation"
            if task_id in HUMAN_DRAFT_TASKS
            else "ai_led_draft"
        )
        minimal_task = {
            "task_id": task_id,
            "task_version": task.get("task_version", 2),
            "query": task["query"],
        }
        compiled = compile_query_rubric(
            minimal_task,
            SPECS[task_id],
            status="draft",
            generator=mode,
        )
        payload = compiled.to_dict(include_hash=False)
        payload["authoring"].update(
            {
                "source": "public_query_only",
                "annotation_mode": mode,
                "annotator_id": "刘弈博" if task_id in HUMAN_DRAFT_TASKS else None,
                "evidence_answerability": "not_assessed",
                "formal_calibration_eligible": False,
            }
        )
        payload["rubric_sha256"] = canonical_json_sha256(payload)
        QueryRubric.from_dict(payload)
        target = output_dir / f"{task_id}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        rows.append(
            {
                "task_id": task_id,
                "query_sha256": payload["query_sha256"],
                "rubric_sha256": payload["rubric_sha256"],
                "atom_count": len(payload["atoms"]),
                "annotation_mode": mode,
                "status": "draft",
                "evidence_answerability": "not_assessed",
                "path": str(target.relative_to(ROOT)),
            }
        )

    output_manifest = {
        "packet_version": "route_a_dev14_rubric_drafts_v1",
        "schema_version": "query_rubric_v1",
        "scoring_semantics": "grounded_requirements_v1",
        "task_count": len(rows),
        "atom_count": sum(row["atom_count"] for row in rows),
        "status": "draft",
        "evidence_answerability": "not_assessed",
        "formal_calibration_eligible": False,
        "notes": [
            "No answer keys, evidence URLs, evidence graph, or agent reports were used.",
            "No atom weights or unique answer routes are present.",
            "Tasks 1-7 preserve human interview input but remain unresolved drafts.",
            "Tasks 8-14 are AI-led drafts and are not independent human annotations.",
        ],
        "tasks": rows,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(output_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = build(args.manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
