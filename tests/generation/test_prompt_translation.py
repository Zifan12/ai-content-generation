"""Tests for the EN→ZH prompt-translation stage (D-language, 2026-07-13).

All tests use a fake LLM — zero network, zero spend. The RenderRules instance
is real (reads config/render_rules.yaml), so these tests also pin the live
config contract: seedance_2_0 carries dialect.prompt_language=zh and
limits.max_prompt_chars=3000.
"""

import logging

import pytest

from src.generation.prompt_translation import _ChinesePrompt, translate_job
from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob


ENGLISH_PROMPT = (
    "Exactly matching the art style of the reference images. Wistoria anime style.\n\n"
    'The teal-haired student is Will (image1). The silver-haired rival is Zeo (image2).\n\n'
    'Medium shot: Will (image1) rises from the desk and takes three steps toward the '
    'window, camera holds fixed framing. Audio: chair legs scraping wood. '
    'Then cut to a close-up: Zeo (image2) narrows his eyes, Zeo says "Stay back" '
    "with a flat voice, camera pushes in slowly. Audio: a low wind gust.\n\n"
    "No on-screen text, no subtitles, no watermark, no logo. No music. "
    "4K, ultra HD, rich detail, sharp clarity, cinematic textures, stable picture."
)

DIALOGUE_LINES = ["Stay back"]

CHINESE_GOOD = (
    "完全匹配参考图像的美术风格。Wistoria 动画风格。"
    "蓝绿色头发的学生是 Will (image1) 。银发的对手是 Zeo (image2) 。"
    "中景：Will (image1) 从课桌旁站起，向窗户走三步，镜头保持固定构图。"
    "音频：椅子腿刮擦木地板声。切换到面部特写：Zeo (image2) 眯起双眼，"
    'Zeo 用平淡的语气说 "Stay back" ，镜头缓缓推近。音频：一阵低沉的风声。'
    "画面无文字、无字幕、无水印、无标志。无音乐。"
    "4K，超高清，细节丰富，清晰锐利，电影质感，画面稳定。"
)


class FakeLLM:
    """Seat double: returns a canned _ChinesePrompt or raises."""

    def __init__(self, output: str | None = None, error: Exception | None = None):
        self.output = output
        self.error = error
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return _ChinesePrompt(chinese_prompt=self.output or "")


def make_job(model_cli_id: str = "seedance_2_0", prompt: str = ENGLISH_PROMPT) -> RenderJob:
    return RenderJob(
        model_cli_id=model_cli_id,
        kind="multi_shot",
        prompt=prompt,
        aspect_ratio="9:16",
        shot_index=0,
        duration=10,
        reference_images=["refs/will/a.png", "refs/zeo/a.png"],
        covers_shots=[0, 1],
    )


@pytest.fixture(scope="module")
def rules() -> RenderRules:
    return RenderRules()


def test_noop_when_model_has_no_zh_leaf(rules):
    """kling3_0 has no prompt_language leaf — the stage must not touch the job."""
    job = make_job(model_cli_id="kling3_0")
    llm = FakeLLM(output=CHINESE_GOOD)

    out = translate_job(job, DIALOGUE_LINES, rules, llm)

    assert out is job
    assert out.translation_status == "not_attempted"
    assert out.prompt_english is None
    assert llm.calls == []


def test_happy_path_translates_and_mirrors(rules):
    job = make_job()
    out = translate_job(job, DIALOGUE_LINES, rules, FakeLLM(output=CHINESE_GOOD))

    assert out.translation_status == "translated"
    assert out.prompt == CHINESE_GOOD
    assert out.prompt_english == ENGLISH_PROMPT
    # original job untouched (model_copy semantics)
    assert job.prompt == ENGLISH_PROMPT
    assert job.translation_status == "not_attempted"


def test_happy_path_sets_explicit_max_tokens(rules):
    llm = FakeLLM(output=CHINESE_GOOD)
    translate_job(make_job(), DIALOGUE_LINES, rules, llm)

    # repo truncation trap: the call must carry its own budget, never the shared default
    assert llm.calls[0]["max_tokens"] >= 6000


@pytest.mark.parametrize(
    ("output", "error", "check"),
    [
        ("", None, "empty_output"),
        (None, RuntimeError("boom"), "llm_error"),
        # image2 token dropped by the translator
        (CHINESE_GOOD.replace("(image2)", ""), None, "image_token_missing"),
        # dialogue translated away
        (CHINESE_GOOD.replace("Stay back", "退后"), None, "dialogue_missing"),
        # half-translated: mostly English prose survives
        (ENGLISH_PROMPT + " 镜头缓缓推近。", None, "cjk_minority"),
        # over the 3000-char yaml ceiling
        (CHINESE_GOOD + "好" * 3000, None, "over_char_limit"),
    ],
)
def test_fallbacks_return_english_with_named_check(rules, caplog, output, error, check):
    job = make_job()
    llm = FakeLLM(output=output, error=error)

    with caplog.at_level(logging.WARNING):
        out = translate_job(job, DIALOGUE_LINES, rules, llm)

    assert out.translation_status == f"fallback:{check}"
    assert out.prompt == ENGLISH_PROMPT
    assert out.prompt_english is None
    assert any(check in rec.getMessage() for rec in caplog.records)


def test_fullwidth_image_parens_normalized_not_failed(rules):
    """Q4: （image1） fullwidth output is repaired, not discarded."""
    fullwidth = CHINESE_GOOD.replace("(image1)", "（image1）")
    out = translate_job(make_job(), DIALOGUE_LINES, rules, FakeLLM(output=fullwidth))

    assert out.translation_status == "translated"
    assert "(image1)" in out.prompt
    assert "（image1）" not in out.prompt


def test_cjk_majority_tolerates_latin_names_and_dialogue(rules):
    """Q3: Latin proper nouns + English dialogue must not trigger a false fallback."""
    out = translate_job(make_job(), DIALOGUE_LINES, rules, FakeLLM(output=CHINESE_GOOD))
    assert out.translation_status == "translated"


def test_chinese_survives_executor_sanitize():
    """Known Windows trap: the sent prompt passes _sanitize_prompt unmangled
    (CJK untouched; ASCII dialogue quotes become apostrophes by design)."""
    from src.generation.executor import _sanitize_prompt

    cleaned = _sanitize_prompt(CHINESE_GOOD)
    assert "镜头缓缓推近" in cleaned
    assert "(image1)" in cleaned
    assert "Stay back" in cleaned
