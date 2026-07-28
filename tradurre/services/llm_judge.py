"""LLM-based alignment judge, restricted to structured index-mapping output.

Requires the optional 'align' dependency group (transformers, torch, accelerate) --
not installed by default, meant to run in a heavier environment (e.g. Colab).
Importing this module without those deps installed is safe; instantiating
LLMJudge raises a clear RuntimeError.

Hard design constraint (per user requirement): the LLM must never generate,
rewrite, or paraphrase the translation. Its only valid output channel is a JSON
index-mapping over the sentences it was given; every output is strictly
validated against the original sentence lists before being trusted, and
anything that fails validation is discarded (logged, original alignment kept).
"""

import json
import logging
import time

logger = logging.getLogger("tradurre.llm_judge")

DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"

_PROMPT_TEMPLATE = """You are an expert literary-translation alignment assistant.

Below are the SOURCE sentences and TARGET sentences of one paragraph (already \
split into individual sentences, but possibly grouped incorrectly). Translators \
sometimes merge two sentences into one, split one into two, reorder within a \
paragraph, or omit a sentence.

SOURCE:
{source_list}

TARGET:
{target_list}

Task: decide which SOURCE sentence indices correspond to which TARGET sentence \
indices. Do NOT translate, rewrite, paraphrase, or add any text -- you are only \
grouping existing sentences by index.

Respond with ONLY a JSON array (no markdown fences, no other text). Each element:
{{"source_indices": [ints], "target_indices": [ints]}}
Every SOURCE index (0..{n_source_minus_1}) and every TARGET index \
(0..{n_target_minus_1}) must appear in exactly one element's list (a list may be \
empty on one side to represent an omission). Order elements by their position in \
the paragraph.
"""


def _load_llm(model_name: str, device: str | None):
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as e:
        raise RuntimeError(
            "LLM-judge alignment requires the 'align' optional dependency group "
            "(transformers, torch, accelerate). Install with: uv sync --extra align"
        ) from e

    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("loading LLM judge model %r on device %r", model_name, resolved_device)
    t0 = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto")
    model = model.to(resolved_device)
    logger.info("LLM judge model loaded in %.1fs", time.monotonic() - t0)
    return tokenizer, model, resolved_device


class LLMJudge:
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        self.tokenizer, self.model, self.device = _load_llm(model_name, device)
        self.model_name = model_name

    def judge_paragraph(
        self, source_sentences: list[str], target_sentences: list[str]
    ) -> list[tuple[list[int], list[int]]] | None:
        """Ask the LLM to propose an index-mapping for one ambiguous paragraph.

        Returns a validated list of (source_indices, target_indices) groups, or
        None if the model's output failed validation -- the caller should keep
        the prior (embedding/anchor) alignment for this paragraph in that case.
        """
        prompt = _build_prompt(source_sentences, target_sentences)
        raw_output = self._generate(prompt)
        groups = _validate_mapping(raw_output, source_sentences, target_sentences)
        if groups is None:
            logger.warning(
                "LLM judge output rejected for a %d/%d-sentence paragraph; "
                "raw output logged at DEBUG",
                len(source_sentences), len(target_sentences),
            )
            logger.debug("rejected LLM judge output: %r", raw_output)
        return groups

    def _generate(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        input_ids = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to(self.device)
        t0 = time.monotonic()
        output = self.model.generate(
            input_ids, max_new_tokens=1024, do_sample=False,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        text = self.tokenizer.decode(
            output[0][input_ids.shape[1]:], skip_special_tokens=True
        )
        logger.debug(
            "LLM judge generated %d chars in %.1fs", len(text), time.monotonic() - t0
        )
        return text


def _build_prompt(source_sentences: list[str], target_sentences: list[str]) -> str:
    source_list = "\n".join(f"{i}: {s}" for i, s in enumerate(source_sentences))
    target_list = "\n".join(f"{i}: {s}" for i, s in enumerate(target_sentences))
    return _PROMPT_TEMPLATE.format(
        source_list=source_list,
        target_list=target_list,
        n_source_minus_1=max(len(source_sentences) - 1, 0),
        n_target_minus_1=max(len(target_sentences) - 1, 0),
    )


def _validate_mapping(
    raw_output: str, source_sentences: list[str], target_sentences: list[str]
) -> list[tuple[list[int], list[int]]] | None:
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]

    try:
        mapping = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("LLM judge returned unparseable JSON: %s", e)
        return None

    if not isinstance(mapping, list):
        logger.error("LLM judge mapping root is not a list: %r", type(mapping))
        return None

    seen_src: set[int] = set()
    seen_tgt: set[int] = set()
    groups: list[tuple[list[int], list[int]]] = []

    for item in mapping:
        if (
            not isinstance(item, dict)
            or "source_indices" not in item
            or "target_indices" not in item
        ):
            logger.error("LLM judge mapping item malformed: %r", item)
            return None

        s_idx, t_idx = item["source_indices"], item["target_indices"]
        if not isinstance(s_idx, list) or not isinstance(t_idx, list):
            logger.error("LLM judge mapping indices are not lists: %r", item)
            return None

        for i in s_idx:
            if not isinstance(i, int) or not (0 <= i < len(source_sentences)) or i in seen_src:
                logger.error("LLM judge produced invalid/duplicate source index: %r", i)
                return None
            seen_src.add(i)
        for i in t_idx:
            if not isinstance(i, int) or not (0 <= i < len(target_sentences)) or i in seen_tgt:
                logger.error("LLM judge produced invalid/duplicate target index: %r", i)
                return None
            seen_tgt.add(i)

        groups.append((sorted(s_idx), sorted(t_idx)))

    if seen_src != set(range(len(source_sentences))):
        logger.error(
            "LLM judge mapping does not cover all source sentences (%d/%d covered)",
            len(seen_src), len(source_sentences),
        )
        return None
    if seen_tgt != set(range(len(target_sentences))):
        logger.error(
            "LLM judge mapping does not cover all target sentences (%d/%d covered)",
            len(seen_tgt), len(target_sentences),
        )
        return None

    logger.info("LLM judge produced a validated mapping with %d groups", len(groups))
    return groups


def apply_mapping(
    groups: list[tuple[list[int], list[int]]],
    source_sentences: list[str],
    target_sentences: list[str],
) -> list[tuple[str, str]]:
    """Reconstruct (source_text, target_text) pairs strictly from the original
    sentence text, per a validated index mapping. Never introduces new text."""
    result = []
    for s_idx, t_idx in groups:
        src = " ".join(source_sentences[i] for i in s_idx)
        tgt = " ".join(target_sentences[i] for i in t_idx)
        result.append((src, tgt))
    return result
