"""Post-adapter EN→ZH scene-prompt translation stage (D-language, 2026-07-13).

Seedance 2.0 is a ByteDance model; the corpus (Dan Kieft playbook L43, lanshu
Chinese-first guidance) says its prompt body parses better in Chinese. This
stage translates the adapter's FINAL composed English scene prompt into
Chinese just before render submission, keeping the pipeline English end-to-end
upstream (writer, craft gate, grounding — all unchanged) and keeping the
adapter's composition deterministic (D-compose: no LLM inside the adapter).

Design (spec docs/superpowers/specs/2026-07-13-chinese-prompt-translation.md,
grill decisions Q1-Q5):

- Q1: the FULL composed prompt is translated in ONE LLM call (no hybrid
  fixed-block constants in v1).
- Q2: dialogue preservation is checked against the code-copied
  ``ShotSpec.dialogue_line`` strings (structured ground truth), never against
  quotes regex-parsed out of the English prose — so the caller passes the
  package's dialogue lines in alongside the job.
- Q3: "output is Chinese" = CJK-majority on the residue: after stripping the
  known dialogue lines and ``(imageN)`` tokens, CJK ideographs must outnumber
  ASCII letters (tolerates Latin character names; catches half-translations).
- Q4: ONE deterministic normalization runs before the checks — fullwidth
  parens around imageN tokens (``（image1）`` → ``(image1)``); ordinary prose
  parens are left alone.
- Q5: the outcome is recorded on ``RenderJob.translation_status`` so dumped
  run JSONs self-explain (not-attempted / translated / fallback:<check>).

Fallback is MECHANICAL ONLY and loud: any failed check logs a WARNING naming
the check and the original English job is rendered instead. No retry, no
back-translation judge. Failed Higgsfield jobs are refunded, so the worst
case of a bad-but-passing translation is one observable bad render — the
first live Chinese render is this feature's validation gate.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob

logger = logging.getLogger(__name__)

# Explicit per-caller budget: a full Chinese scene prompt can run ~3000 CJK
# chars ≈ 4-5k tokens; the shared parse() default has silently truncated big
# outputs three times in this repo (memory feedback_shared_max_tokens_truncation).
TRANSLATION_MAX_TOKENS = 6000

_IMAGE_TOKEN_RE = re.compile(r"\(image\d+\)")
# Q4 normalization: fullwidth parens ONLY when wrapping an imageN token.
_FULLWIDTH_IMAGE_RE = re.compile(r"（\s*(image\d+)\s*）")

TRANSLATION_SYSTEM_PROMPT = """\
You are a professional translator of AI-video generation prompts. You receive
ONE English "scene prompt" written for Seedance 2.0 (a ByteDance video model)
and produce its Chinese translation. Seedance parses Chinese with higher
fidelity, so the Chinese version you write IS the prompt that will be sent to
the model — translation quality directly decides render quality.

Rules, in priority order:

1. PRESERVE EXACTLY, byte for byte, never translated or reformatted:
   - Positional reference tokens like (image1), (image2) — keep halfwidth
     ASCII parentheses, keep them adjacent to the noun they bind, exactly as
     placed in the English.
   - Spoken dialogue: any quoted line a character says stays in ENGLISH,
     inside quotes, word for word. Translate the framing around it (e.g.
     Will says "Stay back" → 威尔说 "Stay back"), never the line itself.
2. Translate everything else into natural, precise simplified Chinese prose —
   this is a director's shot description, not literary prose.
3. Camera and craft vocabulary: use standard Chinese cinematography terms —
   正面角度 / 侧面角度 / 过肩 / 低角度仰拍 / 高角度俯拍 / 大远景 / 全身 /
   中景 / 面部特写 / 极特写 / 镜头缓缓推近 / 镜头缓缓拉远 / 水平横摇 /
   手持晃动 / 固定镜头. Keep camera movement and subject movement as separate
   clauses, exactly as the English separates them.
4. Keep the shot structure: each English shot sentence (including "Then cut
   to:" transitions) becomes its own Chinese sentence with an explicit cut
   marker (切换到 / 镜头切至). Do not merge, split, reorder, or summarize
   shots.
5. Keep counted actions countable (three steps → 三步), keep every concrete
   audio event concrete, and translate the constraint tail (no text, no
   music, quality requirements) fully — do not drop constraints.
6. Output ONLY the Chinese prompt text. No commentary, no markdown fences,
   no English translation alongside.
"""


class _ChinesePrompt(BaseModel):
    """Structured output of the translation call — exactly one field.

    Keeping the response model single-field means schema validation only
    enforces "returned a string"; all real acceptance logic lives in the
    deterministic checks below.
    """

    chinese_prompt: str


def _is_cjk(char: str) -> bool:
    """Return True for a CJK Unified Ideograph (the hanzi block).

    Range: U+4E00–U+9FFF. Punctuation (，。) and kana are deliberately not
    counted — the majority test asks "is the prose itself Chinese", and hanzi
    count alone answers that.
    """
    return "一" <= char <= "鿿"


def _cjk_majority(text: str, dialogue_lines: list[str]) -> bool:
    """Q3 check: CJK ideographs outnumber ASCII letters on the residue.

    The residue is the output minus the spans that are SUPPOSED to be English:
    the known dialogue lines (structured ground truth) and the (imageN)
    tokens. Latin character names surviving in the prose are fine — they lose
    the count to full-sentence Chinese. A half-translated prompt fails.
    """
    residue = text
    for line in dialogue_lines:
        residue = residue.replace(line, " ")
    residue = _IMAGE_TOKEN_RE.sub(" ", residue)
    cjk = sum(1 for c in residue if _is_cjk(c))
    ascii_letters = sum(1 for c in residue if c.isascii() and c.isalpha())
    return cjk > ascii_letters


def translate_job(
    job: RenderJob,
    dialogue_lines: list[str],
    rules: RenderRules,
    llm,
) -> RenderJob:
    """Translate one composed RenderJob's prompt EN→ZH, or fall back loudly.

    Args:
        job: The adapter-composed job. ``job.prompt`` is the final English
            scene prompt (D-compose output, byte-identical to the English
            lane).
        dialogue_lines: The package's ``ShotSpec.dialogue_line`` values (the
            code-copied ground truth, Nones already filtered out by the
            caller). Every one of them must survive VERBATIM in the Chinese
            output.
        rules: Live RenderRules; the stage reads
            ``models.<cli_id>.dialect.prompt_language`` and
            ``models.<cli_id>.limits.max_prompt_chars``.
        llm: An ``llm_for_seat("prompt_translator")`` instance (anything with
            the repo's ``.parse()`` seat interface).

    Returns:
        A new RenderJob. Three shapes:
        - leaf absent/``en``: the SAME job object, untouched
          (``translation_status`` stays ``"not_attempted"``).
        - translation passed all checks: ``prompt`` is Chinese,
          ``prompt_english`` carries the original, status ``"translated"``.
        - any mechanical check failed: original English prompt kept, status
          ``"fallback:<check>"``, WARNING logged. Never raises for LLM or
          check failures — a translation problem must never kill a render run.
    """
    model_block = rules.model(job.model_cli_id)
    if model_block.get("dialect", {}).get("prompt_language") != "zh":
        return job

    def _fallback(check: str) -> RenderJob:
        logger.warning(
            "prompt translation fallback (%s) — sending English prompt for %s",
            check,
            job.model_cli_id,
        )
        return job.model_copy(update={"translation_status": f"fallback:{check}"})

    try:
        result = llm.parse(
            prompt=(
                "Translate this scene prompt to Chinese per the system rules.\n\n"
                f"<scene_prompt>\n{job.prompt}\n</scene_prompt>"
            ),
            response_model=_ChinesePrompt,
            system=TRANSLATION_SYSTEM_PROMPT,
            max_tokens=TRANSLATION_MAX_TOKENS,
        )
    except Exception:
        logger.exception("prompt_translator LLM call failed")
        return _fallback("llm_error")

    text = _FULLWIDTH_IMAGE_RE.sub(r"(\1)", result.chinese_prompt.strip())

    if not text:
        return _fallback("empty_output")

    english_tokens = set(_IMAGE_TOKEN_RE.findall(job.prompt))
    if any(token not in text for token in english_tokens):
        return _fallback("image_token_missing")

    if any(line not in text for line in dialogue_lines):
        return _fallback("dialogue_missing")

    if not _cjk_majority(text, dialogue_lines):
        return _fallback("cjk_minority")

    max_chars = model_block["limits"]["max_prompt_chars"]
    if len(text) > max_chars:
        return _fallback("over_char_limit")

    return job.model_copy(
        update={
            "prompt": text,
            "prompt_english": job.prompt,
            "translation_status": "translated",
        }
    )
