"""Co-STORM runner for the deep-research benchmark.

Integrates Stanford Co-STORM (collaborative_storm) against our sandbox.
Reuses the SandboxSearchRM from storm_runner.py for search, and provides
a local SentenceTransformer-based Encoder to replace the default LiteLLM
embedding Encoder (since DeepSeek has no embedding endpoint).

Co-STORM extends STORM with multi-perspective collaborative research:
  1. warm_start()  — mini-STORM with multiple expert perspectives
  2. step() loop   — simulated user + expert round-table conversation
  3. generate_report() — synthesizes the knowledge-base mind-map into an article

The same RM interface (dspy.Retrieve subclass) is used, so SandboxSearchRM
plugs in directly.

Usage (on westd, with shim+sandbox+ds_proxy running):
    export SHIM_URL=http://localhost:8081
    export DS_PROXY_URL=http://localhost:8088/v1
    export OPENAI_API_KEY=anything
    python3 -c "
    import asyncio
    from scripts.runners.costorm_runner import run
    print(asyncio.run(run(
        intent='Compare headphone prices across stores...',
        model='deepseek-v4-flash',
        shim_url='http://localhost:8081',
        proxy_url='http://localhost:8088/v1',
    )))
    "
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Union

import numpy as np

# Prevent HuggingFace from trying to download models at import time.
# The model must be pre-cached on westd.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Local sentence-transformer Encoder that replaces knowledge_storm's
# LiteLLM-based Encoder.  Co-STORM uses Encoder for:
#   1. Moderator snippet re-ranking (cosine similarity)
#   2. InsertInformationModule (placing info into the mind-map tree)
#   3. KnowledgeBase structure embedding
# We use a local SentenceTransformer model (paraphrase-MiniLM-L6-v2) which
# is already cached on westd, avoiding external embedding API calls.
# ---------------------------------------------------------------------------

_ST_MODEL_NAME = "paraphrase-MiniLM-L6-v2"
_st_model = None  # lazy singleton


def _get_st_model():
    """Lazy-load the SentenceTransformer model (singleton)."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading SentenceTransformer model: {_ST_MODEL_NAME}")
        _st_model = SentenceTransformer(_ST_MODEL_NAME)
        logger.info("SentenceTransformer model loaded.")
    return _st_model


class LocalEncoder:
    """Drop-in replacement for knowledge_storm.encoder.Encoder.

    Uses a local SentenceTransformer model instead of LiteLLM embeddings.
    Implements the same interface: encode(texts) -> np.ndarray.
    """

    def __init__(self, **kwargs):
        # Accept and ignore any kwargs that the real Encoder would take
        # (encoder_type, api_key, api_base, api_version).
        self.total_token_usage = 0

    def get_total_token_usage(self, reset: bool = False) -> int:
        usage = self.total_token_usage
        if reset:
            self.total_token_usage = 0
        return usage

    def encode(
        self,
        texts: Union[str, List[str]],
        max_workers: int = 5,
    ) -> np.ndarray:
        """Encode texts into embeddings using local SentenceTransformer.

        Args:
            texts: Single string or list of strings to embed.
            max_workers: Ignored (ST handles batching internally).

        Returns:
            np.ndarray of shape (dim,) for single text or (n, dim) for list.
        """
        model = _get_st_model()

        if isinstance(texts, str):
            emb = model.encode([texts], show_progress_bar=False)
            return emb[0]  # shape: (dim,)

        if not texts:
            return np.array([[]])

        emb = model.encode(texts, show_progress_bar=False, batch_size=32)
        return np.array(emb)  # shape: (n, dim)


# ---------------------------------------------------------------------------
# Monkey-patch knowledge_storm.encoder.Encoder so that all internal code
# that does `Encoder()` gets our local version instead of crashing on
# missing ENCODER_API_TYPE env var.
# ---------------------------------------------------------------------------

def _patch_encoder():
    """Replace knowledge_storm.encoder.Encoder with LocalEncoder."""
    import knowledge_storm.encoder as enc_mod
    enc_mod.Encoder = LocalEncoder

    # Also patch the dataclass module which imports Encoder at top level
    import knowledge_storm.dataclass as dc_mod
    dc_mod.Encoder = LocalEncoder

    # Patch collaborative_storm agents module
    import knowledge_storm.collaborative_storm.modules.co_storm_agents as agents_mod
    agents_mod.Encoder = LocalEncoder

    # Patch collaborative_storm engine module
    import knowledge_storm.collaborative_storm.engine as engine_mod
    engine_mod.Encoder = LocalEncoder

    # Patch information_insertion_module
    import knowledge_storm.collaborative_storm.modules.information_insertion_module as iim
    iim.Encoder = LocalEncoder


# ---------------------------------------------------------------------------
# Build the Co-STORM runner with our custom RM + LiteLLM model.
# ---------------------------------------------------------------------------

def _build_costorm_runner(
    shim_url: str,
    proxy_url: str,
    model: str,
    topic: str,
    api_key: str = "anything",
):
    """Construct a CoStormRunner using our SandboxSearchRM + LocalEncoder.

    Uses Co-STORM's official constructor args and LM config setters.
    """
    # Patch Encoder BEFORE importing Co-STORM engine
    _patch_encoder()

    from knowledge_storm.collaborative_storm.engine import (
        CoStormRunner,
        RunnerArgument,
        CollaborativeStormLMConfigs,
    )
    from knowledge_storm.lm import LitellmModel
    from knowledge_storm.logging_wrapper import LoggingWrapper

    # Import SandboxSearchRM from our storm_runner
    from scripts.runners.storm_runner import SandboxSearchRM

    # -- Language model config --
    llm_kwargs = dict(
        model=f"openai/{model}",
        api_key=api_key,
        api_base=proxy_url,
        max_tokens=4096,
        temperature=0.7,
        top_p=0.9,
    )

    lm_config = CollaborativeStormLMConfigs()
    # Set all 6 LM slots to our backbone via LiteLLM OpenAI-compat routing
    for setter in (
        lm_config.set_question_answering_lm,
        lm_config.set_discourse_manage_lm,
        lm_config.set_utterance_polishing_lm,
        lm_config.set_warmstart_outline_gen_lm,
        lm_config.set_question_asking_lm,
        lm_config.set_knowledge_base_lm,
    ):
        setter(LitellmModel(**llm_kwargs))

    # -- Runner arguments --
    # Keep conversation short to avoid excessive LLM calls while still
    # getting multi-perspective coverage.
    args = RunnerArgument(
        topic=topic,
        retrieve_top_k=5,
        max_search_queries=2,
        total_conv_turn=10,         # main conversation turns after warm-start
        max_search_thread=3,
        max_search_queries_per_turn=3,
        warmstart_max_num_experts=3,
        warmstart_max_turn_per_experts=2,
        warmstart_max_thread=2,
        max_thread_num=3,           # keep concurrency modest to avoid rate limits
        max_num_round_table_experts=2,
        moderator_override_N_consecutive_answering_turn=3,
        node_expansion_trigger_count=10,
    )

    # -- Logging wrapper --
    logging_wrapper = LoggingWrapper(lm_config)

    # -- Retrieval model: our sandbox shim --
    rm = SandboxSearchRM(
        shim_url=shim_url,
        k=5,
        include_raw_content=True,
    )

    runner = CoStormRunner(
        lm_config=lm_config,
        runner_argument=args,
        logging_wrapper=logging_wrapper,
        rm=rm,
    )

    return runner


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Agent identifier for the auto-discovery registry. Must match the
# AGENT_NAME used in score files: data/results/deep_v3/co-storm__<task>_matrix.score.json
AGENT_NAME = "co-storm"


async def run(
    intent: str,
    model: str,
    shim_url: str,
    proxy_url: str,
) -> str:
    """Run Co-STORM and return the markdown report.

    Args:
        intent: The research topic / query.
        model: LLM model name (e.g. 'deepseek-v4-flash').
        shim_url: Tavily-compatible search shim (e.g. 'http://localhost:8081').
        proxy_url: OpenAI-compatible LLM proxy (e.g. 'http://localhost:8088/v1').

    Returns:
        The generated article as a markdown string with inline citations.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "anything")

    # Truncate topic to avoid filesystem path issues
    topic = intent[:300]

    logger.info(f"[co-storm] Starting Co-STORM for topic: {topic[:80]}...")

    runner = _build_costorm_runner(
        shim_url=shim_url,
        proxy_url=proxy_url,
        model=model,
        topic=topic,
        api_key=api_key,
    )

    # ---- Phase 1: Warm Start ----
    # Conducts background research with multiple expert perspectives,
    # builds the initial knowledge base (mind map).
    logger.info("[co-storm] Phase 1: warm_start()")
    runner.warm_start()

    # ---- Phase 2: Simulated Conversation ----
    # Run conversation turns. The pattern is:
    #   - Inject a simulated user question
    #   - Let Co-STORM answer with 2-3 expert/moderator turns
    #   - Repeat with next user intent
    # This interleaving ensures experts answer each question (building
    # the knowledge base) before the next user question is injected.
    total_turns = runner.runner_argument.total_conv_turn
    logger.info(f"[co-storm] Phase 2: running up to {total_turns} conversation turns")

    # Diverse research angles for the simulated user
    user_intents = [
        f"What are the key differences and trade-offs when comparing options for {topic}?",
        f"What do real user reviews and discussions say about {topic}?",
        f"What are the most important factors to consider regarding {topic}?",
    ]

    turn_count = 0
    intent_idx = 0

    while turn_count < total_turns:
        try:
            # Every 3-4 turns, inject a new user intent (if available)
            if intent_idx < len(user_intents) and (
                turn_count == 0 or turn_count % 4 == 0
            ):
                runner.step(
                    simulate_user=True,
                    simulate_user_intent=user_intents[intent_idx],
                )
                intent_idx += 1
            else:
                # Let Co-STORM manage: expert answers / moderator questions
                runner.step()

            turn_count += 1
            logger.info(
                f"[co-storm] Turn {turn_count}/{total_turns} complete "
                f"(history: {len(runner.conversation_history)} turns)"
            )
        except Exception as e:
            logger.warning(
                f"[co-storm] Turn {turn_count + 1} failed: {e}. "
                "Continuing with remaining turns."
            )
            turn_count += 1
            continue

    # ---- Phase 3: Report Generation ----
    # Synthesizes the knowledge base mind-map into a structured article.
    logger.info("[co-storm] Phase 3: generate_report()")
    try:
        report = runner.generate_report()
    except Exception as e:
        logger.error(f"[co-storm] Report generation failed: {e}")
        # Fall back to dumping knowledge base structure
        report = _fallback_report(runner)

    if not report or len(report.strip()) < 50:
        logger.warning("[co-storm] Report too short, attempting fallback.")
        report = _fallback_report(runner)

    logger.info(f"[co-storm] Done. Report length: {len(report)} chars")
    return report


def _fallback_report(runner) -> str:
    """Build a fallback report from conversation history if article generation fails."""
    parts = []
    parts.append(f"# {runner.runner_argument.topic}\n")

    # Add knowledge base outline
    try:
        outline = runner.knowledge_base.get_node_hierarchy_string(
            include_hash_tag=True,
            include_node_content_count=True,
        )
        if outline.strip():
            parts.append("## Knowledge Base Structure\n")
            parts.append(outline)
            parts.append("")
    except Exception:
        pass

    # Add conversation highlights
    parts.append("## Research Conversation\n")
    for i, turn in enumerate(runner.conversation_history):
        role = getattr(turn, "role", "Unknown")
        utterance = getattr(turn, "utterance", "") or getattr(turn, "raw_utterance", "")
        if utterance:
            parts.append(f"**{role}** (turn {i+1}): {utterance}\n")

    return "\n".join(parts)
