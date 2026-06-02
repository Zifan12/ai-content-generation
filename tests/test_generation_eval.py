import pytest

from src.evals.judges import JudgeVerdict
from src.schemas.generation import ContentPackage
from src.miner.schemas import MinerEvidence
from src.miner.schemas import BlueprintCandidate
from src.evals.generation_eval import generation_rag_win_rate

class FakeLLM():
     def parse(self, prompt, response_model, system=None, max_tokens=1024):
        package = ContentPackage(
        video_prompt="test",
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        grounding_hit_ids=[],
        )

        return package

class FakeJudge():
    def judge_pairwise(self, video_stats, rag_script, baseline_script):
        return JudgeVerdict(
            score=4,
            hook_strength="strong",
            reasoning="test",
            preferred="rag",
        )


def test_win_rate_computes_and_gates(llm=FakeLLM(), judge=FakeJudge()):

    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test"
    )

    
    candidate = BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "ITS2AMINTHEMORNING"},
        evidence=evidence,
        
    )

    targets = [candidate]

    result = generation_rag_win_rate(targets, db=None, judge=FakeJudge(), llm=FakeLLM(), seed=42)

    assert result["rag_win_rate"] == 1.0  and result["gate_passed"] == True

