"""Qwen3 policy for the Phase B multi-turn GRPO pilot.

The module is importable on CPU-only machines. Heavy training dependencies
such as torch, Unsloth, vLLM, and bitsandbytes are imported only inside the
methods that need them.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from .action_parser import parse_action, render_observation
from .env import Action, Finalize
from .policy import Generation


# Qwen3 has no dense 3B; the project's documented backup (4B) is the real default.
_DEFAULT_MODEL = "unsloth/Qwen3-4B"
_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


class QwenPolicy:
    """Stateful policy that records per-episode token and response masks."""

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        model_name: str | None = None,
        ctx: int | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        lr: float | None = None,
        lora_r: int | None = None,
        lora_alpha: int | None = None,
        gpu_memory_utilization: float | None = None,
        load_in_4bit: bool | None = None,
        use_vllm: bool | None = None,
        enable_thinking: bool | None = None,
    ) -> None:
        self.model_name = _DEFAULT_MODEL
        self.ctx = 8192
        self.max_new_tokens = 512
        self.temperature = 0.7
        self.top_p = 0.95
        self.lr = 5e-7
        self.lora_r = 16
        self.lora_alpha = 32
        self.gpu_memory_utilization = 0.6
        self.load_in_4bit = True
        # vLLM generation is a throughput optimization. The pilot defaults to
        # plain HF generate (use_vllm=False) so it does not depend on a CUDA-
        # matched vLLM build; flip to True once a torch-matched vLLM is in place.
        self.use_vllm = False
        # Backward over a long trajectory runs GPU kernels past the Windows TDR
        # watchdog (~2s) on the shared display GPU -> "CUDA driver error". Cap the
        # number of trailing tokens the GRPO backward processes (the report span
        # is at the end, so it stays trainable). Generation still uses full ctx.
        self.train_seq_cap = 1024
        # Qwen3 thinking mode: with it ON the model burns the turn budget on
        # <think> reasoning and often never reaches the directive. Qwen3-4B emits
        # a clean directive directly with thinking OFF (1.7B does not, so make it
        # configurable). Default OFF for the 4B pilot.
        self.enable_thinking = False

        self.config_path = Path(config_path) if config_path is not None else None
        if self.config_path is not None:
            self._apply_config(self.config_path)

        if model_name is not None:
            self.model_name = _normalize_model_name(model_name)
        if ctx is not None:
            self.ctx = int(ctx)
        if max_new_tokens is not None:
            self.max_new_tokens = int(max_new_tokens)
        if temperature is not None:
            self.temperature = float(temperature)
        if top_p is not None:
            self.top_p = float(top_p)
        if lr is not None:
            self.lr = float(lr)
        if lora_r is not None:
            self.lora_r = int(lora_r)
        if lora_alpha is not None:
            self.lora_alpha = int(lora_alpha)
        if gpu_memory_utilization is not None:
            self.gpu_memory_utilization = float(gpu_memory_utilization)
        if load_in_4bit is not None:
            self.load_in_4bit = bool(load_in_4bit)
        if use_vllm is not None:
            self.use_vllm = bool(use_vllm)
        if enable_thinking is not None:
            self.enable_thinking = bool(enable_thinking)

        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._optimizer: Any | None = None
        self._sampling_params: Any | None = None
        self._adapter_path: Path | None = None
        self._tokenizer_path: Path | None = None
        self._pending_optimizer_path: Path | None = None
        self._step = 0

        self._turns: list[dict[str, str]] = []
        self._tok_ids: list[int] = []
        self._resp_mask: list[int] = []
        self._episode_records: list[tuple[list[int], list[int]]] = []
        self._episode_recorded = False
        self._last_observation_marker: tuple[Any, ...] | None = None

    def start_episode(self, task_config: dict[str, Any] | None = None) -> None:
        """Reset chat state and seed it with system plus task messages."""

        if self._tok_ids and not self._episode_recorded:
            self._freeze_episode_record()

        task = dict(task_config or {})
        prompt = _task_prompt(task)
        self._turns = [
            {"role": "system", "content": self._system_prompt(task)},
            {"role": "user", "content": prompt},
        ]
        self._tok_ids = []
        self._resp_mask = []
        self._episode_recorded = False
        self._last_observation_marker = None

    def act(self, observation: dict[str, Any]) -> Action:
        """Generate one assistant turn and parse it into one env action."""

        if not self._turns:
            self.start_episode((observation or {}).get("task_config") or {})

        self._append_observation(observation or {})
        self._ensure_model()

        prompt_text, prompt_ids = self._render_chat()
        self._append_context_tokens(prompt_ids)

        generated = self._generate_texts([prompt_text])[0]
        out_ids = self._tokenize(generated)
        self._tok_ids.extend(out_ids)
        self._resp_mask.extend([1] * len(out_ids))

        action = parse_action(generated)
        self._turns.append({"role": "assistant", "content": generated})

        if isinstance(action, Finalize):
            self._freeze_episode_record()

        return action

    def generate(self, task_prompt: str, *, n: int) -> list[Generation]:
        """Generate ``n`` single-turn candidates through the vLLM path."""

        if n <= 0:
            return []
        messages = [
            {"role": "system", "content": self._system_prompt({})},
            {"role": "user", "content": str(task_prompt or "")},
        ]
        prompt_text = self._render_messages(messages)
        prompt_ids = self._tokenize(prompt_text)
        texts = self._generate_texts([prompt_text for _ in range(int(n))])

        generations: list[Generation] = []
        for text in texts:
            action = parse_action(text)
            report = action.report_md if isinstance(action, Finalize) else text
            out_ids = self._tokenize(text)
            generations.append(
                Generation(
                    actions=[action],
                    report_md=report,
                    token_ids=[*prompt_ids, *out_ids],
                    logprobs=None,
                    metadata={"text": text},
                )
            )
        return generations

    def update(self, batch: dict[str, Any]) -> dict[str, float]:
        """Run one single-epoch GRPO update over recorded episodes."""

        if self._tok_ids and not self._episode_recorded:
            self._freeze_episode_record()

        advantages = [float(value) for value in batch.get("advantages", [])]
        rewards = [float(value) for value in batch.get("rewards", [])]
        expected = len(batch.get("rollouts") or advantages)
        if expected <= 0:
            return {
                "loss": 0.0,
                "mean_reward": _mean(rewards),
                "mean_abs_adv": _mean_abs(advantages),
                "n_resp_tokens": 0.0,
                "grad_norm": 0.0,
            }
        if len(self._episode_records) < expected:
            raise RuntimeError(
                "QwenPolicy.update expected "
                f"{expected} episode records, got {len(self._episode_records)}"
            )

        if "lr" in batch:
            self.lr = float(batch["lr"])
        self._ensure_optimizer()
        self._set_optimizer_lr(self.lr)

        import torch

        model = self._model
        assert model is not None
        optimizer = self._optimizer
        assert optimizer is not None
        model.train()

        records = self._episode_records[:expected]
        mask_tool_tokens = bool(batch.get("mask_tool_tokens", True))
        prepared: list[tuple[list[int], list[int], float]] = []
        for (tok_ids, resp_mask), advantage in zip(records, advantages):
            ids = [int(x) for x in tok_ids]
            mask = _aligned_mask(resp_mask, len(ids), mask_tool_tokens=mask_tool_tokens)
            resp_tokens = sum(mask[1:]) if len(mask) > 1 else 0
            if len(ids) >= 2 and resp_tokens > 0 and math.isfinite(float(advantage)):
                prepared.append((ids, mask, float(advantage)))

        if not prepared:
            self._episode_records.clear()
            return {
                "loss": 0.0,
                "mean_reward": _mean(rewards),
                "mean_abs_adv": _mean_abs(advantages),
                "n_resp_tokens": 0.0,
                "grad_norm": 0.0,
            }

        params = self._trainable_parameters()
        optimizer.zero_grad(set_to_none=True)
        device = _model_device(model)
        loss_values: list[float] = []
        n_resp_tokens = 0

        for ids, mask, advantage in prepared:
            # Train only on the trailing window. This (a) keeps ids within the
            # model max length, (b) keeps the final report (the key trainable
            # response span, which sits at the end), and (c) bounds the backward
            # kernel length so it stays under the Windows TDR watchdog.
            cap = min(self.ctx, self.train_seq_cap)
            if len(ids) > cap:
                ids = ids[-cap:]
                mask = mask[-cap:]
            ids_tensor = torch.tensor(ids, dtype=torch.long, device=device).unsqueeze(0)
            resp_tensor = torch.tensor(mask, dtype=torch.float32, device=device)
            logits = model(input_ids=ids_tensor[:, :-1]).logits  # [1, L, V]
            targets = ids_tensor[0, 1:]                           # [L]
            resp_shift = resp_tensor[1:]                          # [L]
            # Compute token log-probs ONLY at response positions. Materializing a
            # full [L, vocab] log_softmax (vocab ~152k) is a huge tensor + kernel
            # that OOMs / trips the Windows GPU watchdog (TDR) on the shared
            # display GPU. Slicing to response rows first keeps it small.
            resp_pos = torch.nonzero(resp_shift > 0.5, as_tuple=False).squeeze(-1)
            if resp_pos.numel() == 0:
                continue
            sel_logits = logits[0].index_select(0, resp_pos)     # [R, V]
            sel_targets = targets.index_select(0, resp_pos)       # [R]
            logZ = torch.logsumexp(sel_logits.float(), dim=-1)    # [R]
            tok_logit = sel_logits.float().gather(-1, sel_targets.unsqueeze(-1)).squeeze(-1)  # [R]
            token_logp = tok_logit - logZ                         # [R]
            loss_i = -(float(advantage) * token_logp.mean())
            (loss_i / len(prepared)).backward()
            loss_values.append(float(loss_i.detach().float().cpu().item()))
            n_resp_tokens += int(resp_pos.numel())

        grad_norm_tensor = torch.nn.utils.clip_grad_norm_(params, 1.0)
        if hasattr(grad_norm_tensor, "detach"):
            grad_norm = float(grad_norm_tensor.detach().cpu().item())
        else:
            grad_norm = float(grad_norm_tensor)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)

        self._step += 1
        self._episode_records.clear()

        return {
            "loss": _mean(loss_values),
            "mean_reward": _mean(rewards),
            "mean_abs_adv": _mean_abs(advantages),
            "n_resp_tokens": float(n_resp_tokens),
            "grad_norm": grad_norm,
        }

    def save(self, path: str | Path) -> None:
        """Save LoRA weights, tokenizer files, optimizer state, and metadata."""

        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        if self._model is not None:
            lora_dir = target / "lora"
            self._model.save_pretrained(lora_dir)
        if self._tokenizer is not None:
            self._tokenizer.save_pretrained(target / "tokenizer")
        if self._optimizer is not None:
            import torch

            torch.save(self._optimizer.state_dict(), target / "optimizer.pt")

        payload = {
            "model_name": self.model_name,
            "ctx": self.ctx,
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "lr": self.lr,
            "lora_r": self.lora_r,
            "lora_alpha": self.lora_alpha,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "load_in_4bit": self.load_in_4bit,
            "step": self._step,
        }
        (target / "qwen_policy.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load(self, path: str | Path) -> None:
        """Load policy metadata and defer heavy state loading until needed."""

        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(path)
        metadata_path = root / "qwen_policy.json"
        if metadata_path.exists():
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.model_name = _normalize_model_name(payload.get("model_name") or self.model_name)
            self.ctx = int(payload.get("ctx", self.ctx))
            self.max_new_tokens = int(payload.get("max_new_tokens", self.max_new_tokens))
            self.temperature = float(payload.get("temperature", self.temperature))
            self.top_p = float(payload.get("top_p", self.top_p))
            self.lr = float(payload.get("lr", self.lr))
            self.lora_r = int(payload.get("lora_r", self.lora_r))
            self.lora_alpha = int(payload.get("lora_alpha", self.lora_alpha))
            self.gpu_memory_utilization = float(
                payload.get("gpu_memory_utilization", self.gpu_memory_utilization)
            )
            self.load_in_4bit = bool(payload.get("load_in_4bit", self.load_in_4bit))
            self._step = int(payload.get("step", self._step))

        self._adapter_path = root / "lora" if (root / "lora").exists() else None
        self._tokenizer_path = root / "tokenizer" if (root / "tokenizer").exists() else None
        self._pending_optimizer_path = (
            root / "optimizer.pt" if (root / "optimizer.pt").exists() else None
        )
        self._model = None
        self._tokenizer = None
        self._optimizer = None
        self._sampling_params = None

    def _ensure_model(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        from unsloth import FastLanguageModel

        load_name = str(self._adapter_path or self.model_name)
        load_kwargs: dict[str, Any] = {
            "model_name": load_name,
            "max_seq_length": self.ctx,
            "load_in_4bit": self.load_in_4bit,
        }
        if self.use_vllm:
            # vLLM-colocated inference (Standby weight sharing). Only used when a
            # torch-matched vLLM build is confirmed working on the box.
            load_kwargs["fast_inference"] = True
            load_kwargs["gpu_memory_utilization"] = self.gpu_memory_utilization
        self._model, self._tokenizer = FastLanguageModel.from_pretrained(**load_kwargs)  # CONFIRM-ON-BOX

        if self._adapter_path is None:
            self._model = FastLanguageModel.get_peft_model(
                self._model,
                r=self.lora_r,
                lora_alpha=self.lora_alpha,
                target_modules=list(_TARGET_MODULES),
                use_gradient_checkpointing="unsloth",
            )  # CONFIRM-ON-BOX

        if self._tokenizer_path is not None:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(
                str(self._tokenizer_path),
                trust_remote_code=True,
            )

        self._configure_model_and_tokenizer()

    def _ensure_optimizer(self) -> None:
        self._ensure_model()
        if self._optimizer is not None:
            return
        import bitsandbytes as bnb

        self._optimizer = bnb.optim.AdamW8bit(self._trainable_parameters(), lr=self.lr)
        if self._pending_optimizer_path is not None:
            import torch

            state = torch.load(self._pending_optimizer_path, map_location="cpu")
            self._optimizer.load_state_dict(state)
            self._pending_optimizer_path = None

    def _sampling(self) -> Any:
        if self._sampling_params is None:
            from vllm import SamplingParams

            self._sampling_params = SamplingParams(
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_new_tokens,
            )  # CONFIRM-ON-BOX
        return self._sampling_params

    def _generate_texts(self, prompts: list[str]) -> list[str]:
        self._ensure_model()
        assert self._model is not None
        if self.use_vllm:
            outputs = self._model.fast_generate(
                prompts,
                sampling_params=self._sampling(),
            )  # CONFIRM-ON-BOX
            texts = [_extract_generated_text(item) for item in _as_list(outputs)]
        else:
            texts = self._hf_generate(prompts)
        if len(texts) < len(prompts):
            texts.extend([""] * (len(prompts) - len(texts)))
        return texts[: len(prompts)]

    def _hf_generate(self, prompts: list[str]) -> list[str]:
        """Plain HF batch generation (no vLLM). Left-pads, decodes the suffix."""
        import torch

        tokenizer = self._tokenizer
        model = self._model
        assert tokenizer is not None and model is not None
        prev_side = getattr(tokenizer, "padding_side", "right")
        tokenizer.padding_side = "left"
        try:
            enc = tokenizer(
                list(prompts),
                return_tensors="pt",
                padding=True,
                add_special_tokens=False,
            )
            device = _model_device(model)
            enc = {key: value.to(device) for key, value in enc.items()}
            pad_id = getattr(tokenizer, "pad_token_id", None)
            if pad_id is None:
                pad_id = getattr(tokenizer, "eos_token_id", None)
            gen_kwargs: dict[str, Any] = {
                "max_new_tokens": self.max_new_tokens,
                "do_sample": self.temperature > 0,
                "top_p": self.top_p,
                "pad_token_id": pad_id,
            }
            if self.temperature > 0:
                gen_kwargs["temperature"] = self.temperature
            # use_cache=False forces a full-sequence forward at each decode step,
            # avoiding unsloth-2026.3.11's buggy Qwen3 incremental-decode RoPE
            # kernel (cos mis-broadcast on single-token decode). Slower but
            # correct, and it keeps the model trainable for the GRPO forward.
            gen_kwargs["use_cache"] = False
            with torch.no_grad():
                out = model.generate(**enc, **gen_kwargs)
            in_len = enc["input_ids"].shape[1]
            texts = [
                tokenizer.decode(out[i][in_len:], skip_special_tokens=True)
                for i in range(out.shape[0])
            ]
            return texts
        finally:
            tokenizer.padding_side = prev_side

    def _render_chat(self) -> tuple[str, list[int]]:
        text = self._render_messages(self._turns)
        return text, self._tokenize(text)

    def _render_messages(self, messages: list[dict[str, str]]) -> str:
        self._ensure_model()
        tokenizer = self._tokenizer
        assert tokenizer is not None
        # enable_thinking controls Qwen3 thinking mode (default OFF for the 4B,
        # which then emits a directive directly). parse_action still strips any
        # <think> block, so thinking-ON models also work. Fall back gracefully
        # for tokenizers that do not accept the kwarg.
        try:
            return str(
                tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=self.enable_thinking,
                )
            )
        except TypeError:
            pass
        except Exception:
            return _fallback_chat_template(messages)
        try:
            return str(
                tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            )
        except Exception:
            return _fallback_chat_template(messages)

    def _tokenize(self, text: str) -> list[int]:
        self._ensure_model()
        tokenizer = self._tokenizer
        assert tokenizer is not None
        encoded = tokenizer(str(text or ""), add_special_tokens=False)
        ids = encoded["input_ids"] if isinstance(encoded, dict) else encoded.input_ids
        if ids and isinstance(ids[0], list):
            ids = ids[0]
        return [int(value) for value in ids]

    def _append_observation(self, observation: dict[str, Any]) -> None:
        step_count = int(observation.get("step_count") or 0)
        last_action = str(observation.get("last_action") or "")
        marker = (
            step_count,
            last_action,
            int(observation.get("tool_calls_used") or 0),
            bool(observation.get("done")),
        )
        if marker == self._last_observation_marker:
            return
        self._last_observation_marker = marker
        if step_count == 0 and last_action == "reset":
            return
        self._turns.append({"role": "user", "content": render_observation(observation)})

    def _append_context_tokens(self, prompt_ids: list[int]) -> None:
        if not prompt_ids:
            return
        if not self._tok_ids:
            new_tokens = prompt_ids
        elif (
            len(prompt_ids) >= len(self._tok_ids)
            and prompt_ids[: len(self._tok_ids)] == self._tok_ids
        ):
            new_tokens = prompt_ids[len(self._tok_ids) :]
        else:
            overlap = _suffix_prefix_overlap(self._tok_ids, prompt_ids)
            new_tokens = prompt_ids[overlap:]
        self._tok_ids.extend(int(value) for value in new_tokens)
        self._resp_mask.extend([0] * len(new_tokens))

    def _freeze_episode_record(self) -> None:
        if self._episode_recorded or not self._tok_ids:
            return
        self._episode_records.append((list(self._tok_ids), list(self._resp_mask)))
        self._episode_recorded = True

    def _trainable_parameters(self) -> list[Any]:
        model = self._model
        assert model is not None
        return [param for param in model.parameters() if getattr(param, "requires_grad", False)]

    def _set_optimizer_lr(self, lr: float) -> None:
        if self._optimizer is None:
            return
        for group in self._optimizer.param_groups:
            group["lr"] = lr

    def _configure_model_and_tokenizer(self) -> None:
        tokenizer = self._tokenizer
        if tokenizer is not None and getattr(tokenizer, "pad_token", None) is None:
            eos = getattr(tokenizer, "eos_token", None)
            if eos is not None:
                tokenizer.pad_token = eos
        model = self._model
        config = getattr(model, "config", None)
        if config is not None and hasattr(config, "use_cache"):
            config.use_cache = False

    def _system_prompt(self, task_config: dict[str, Any]) -> str:
        language_note = _language_instruction(task_config)
        return (
            "You are a Deep Research Arena agent in a closed sandbox. Gather evidence with "
            "tools, then write a substantial, well-structured report grounded in the pages "
            "you READ. Output EXACTLY ONE directive per turn, as a single line, with nothing "
            "after it (except FINALIZE, whose report may span many lines).\n"
            "Directives:\n"
            "  SEARCH: <query>     - search the sandbox; returns result URLs\n"
            "  OPEN: <url>         - select a URL from the latest search_results\n"
            "  READ                - read the page you just OPENed (adds it to your evidence)\n"
            "  NOTE: <text>        - save a key fact to memory (optional)\n"
            "  FINALIZE: <report>  - your final markdown report\n"
            "Workflow: SEARCH, then repeatedly OPEN a returned url and READ it. READ AT LEAST "
            "THREE different pages (ideally 4-5) before you FINALIZE; run another SEARCH if you "
            "need more sources. Only OPEN urls that appear in the latest search_results (never "
            "invent a url). Do NOT write from memory: every claim must come from a page you READ.\n"
            "The FINALIZE report MUST be a structured article of AT LEAST 300 words with:\n"
            "  - several '## Section' headings,\n"
            "  - specific facts, numbers and comparisons taken from the pages you READ,\n"
            "  - a markdown citation [title](url) right after each claim, pointing to the exact "
            "page you READ it from.\n"
            "Cite ONLY pages you actually READ. Your FIRST directive must be SEARCH.\n"
            "Example first turn:\n"
            "SEARCH: noise cancelling headphones"
            f"{language_note}"
        )

    def _apply_config(self, path: Path) -> None:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        model = data.get("model") or {}
        grpo = data.get("grpo") or {}
        if model.get("base_model"):
            self.model_name = _normalize_model_name(model["base_model"])
        if model.get("context_length"):
            self.ctx = int(model["context_length"])
        if model.get("lora_rank"):
            self.lora_r = int(model["lora_rank"])
        if model.get("lora_alpha"):
            self.lora_alpha = int(model["lora_alpha"])
        if grpo.get("learning_rate"):
            self.lr = float(grpo["learning_rate"])


def _task_prompt(task_config: dict[str, Any]) -> str:
    prompt = str(
        task_config.get("prompt")
        or task_config.get("intent")
        or task_config.get("question")
        or ""
    )
    substitutions = {
        "__SHOPPING__": os.environ.get("SHOPPING", "http://localhost:7770"),
        "__REDDIT__": os.environ.get("REDDIT", "http://localhost:9999"),
        "__WIKIPEDIA__": os.environ.get("WIKIPEDIA", "http://localhost:8090"),
    }
    for needle, replacement in substitutions.items():
        prompt = prompt.replace(needle, replacement)
    return prompt


def _language_instruction(task_config: dict[str, Any]) -> str:
    lang = str(task_config.get("language", "en") or "en").lower()
    if lang == "zh":
        return "\n\n请用中文撰写完整的研究报告。"
    if lang == "bilingual":
        return (
            "\n\nProvide the full research report in BOTH English and Chinese "
            "(中英双语,两种语言都要完整)."
        )
    return ""


def _fallback_chat_template(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").upper()
        content = str(message.get("content") or "")
        parts.append(f"{role}:\n{content}")
    parts.append("ASSISTANT:\n")
    return "\n\n".join(parts)


def _extract_generated_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if "text" in item:
            return str(item["text"])
        outputs = item.get("outputs")
        if isinstance(outputs, list) and outputs:
            return _extract_generated_text(outputs[0])
    outputs = getattr(item, "outputs", None)
    if outputs:
        return _extract_generated_text(outputs[0])
    text = getattr(item, "text", None)
    if text is not None:
        return str(text)
    return str(item)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _aligned_mask(
    mask: list[int],
    length: int,
    *,
    mask_tool_tokens: bool,
) -> list[int]:
    if not mask_tool_tokens:
        return [1 for _ in range(length)]
    out = [1 if int(value) else 0 for value in list(mask[:length])]
    if len(out) < length:
        out.extend([0] * (length - len(out)))
    return out


def _suffix_prefix_overlap(left: list[int], right: list[int]) -> int:
    max_len = min(len(left), len(right))
    for size in range(max_len, 0, -1):
        if left[-size:] == right[:size]:
            return size
    return 0


def _model_device(model: Any) -> Any:
    device = getattr(model, "device", None)
    if device is not None:
        return device
    return next(model.parameters()).device


def _mean(values: list[float]) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return sum(finite) / len(finite) if finite else 0.0


def _mean_abs(values: list[float]) -> float:
    finite = [abs(float(value)) for value in values if math.isfinite(float(value))]
    return sum(finite) / len(finite) if finite else 0.0


def _normalize_model_name(name: Any) -> str:
    value = str(name or _DEFAULT_MODEL).strip()
    if not value:
        return _DEFAULT_MODEL
    if "/" not in value and value.lower() in {"qwen3-3b", "qwen3-4b"}:
        return _DEFAULT_MODEL
    return value


__all__ = ["QwenPolicy"]
