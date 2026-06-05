"""
THROWAWAY smoke test for ContentWriter.write() (P3 Task 5).

Runs write() once per premise in PREMISES (4 stratified what-if premises, one
per axis: creature / environment / transformation / scale) against real DB rows
+ a real Sonnet call each, and prints a human-readable arc dump per premise for
eyeballing against the 4-failure rubric. Not an eval, not a gate — just "does it
produce coherent montages across premises, and where does it fail". Delete after
use.

Stratifying across 4 premises (not 1) is deliberate: a single premise cannot
reveal whether the writer overfits one template — only a spread exposes
cross-premise monotony.

Picks the most common niche among v3 blueprints, uses 3 of those blueprints as
the retrieved "winners" (hits), hand-builds a plausible target candidate from
the first one's grouped mechanics, and asks the writer to generate around each
premise.
"""

from collections import Counter

from dotenv import load_dotenv

# Load secrets BEFORE importing src.database (it reads DATABASE_URL at import).
load_dotenv("config/.env")

from sqlalchemy import select  # noqa: E402

from src.database import SessionLocal  # noqa: E402
from src.models.blueprint import BlueprintRecord  # noqa: E402
from src.miner.schemas import BlueprintCandidate, MinerEvidence  # noqa: E402
from src.rag.schemas import RetrievalHit  # noqa: E402
from src.generation.content_writer import ContentWriter  # noqa: E402

PREMISES = [
    "Footage of Kraken appearing in the pacific ocean",
    "POV: Someone exploring and found the Yggdrasil",
    "Human transforming into an angel",
    "Life as an ant"
]


def main() -> None:
    db = SessionLocal()
    try:
        v3 = db.scalars(
            select(BlueprintRecord).where(BlueprintRecord.extractor_version == "v3")
        ).all()
        if len(v3) < 3:
            raise SystemExit(f"Need >=3 v3 blueprints, found {len(v3)}.")

        niches = Counter(b.blueprint_data.get("niche_label", "unknown") for b in v3)
        top_niche, _ = niches.most_common(1)[0]
        print(f"niche distribution (v3): {niches.most_common()}")
        print(f"using niche: {top_niche}\n")

        chosen = [b for b in v3 if b.blueprint_data.get("niche_label") == top_niche][:3]

        hits = [
            RetrievalHit(
                content_item_id=b.content_item_id,
                blueprint_id=b.id,
                score=0.90 - i * 0.05,
                blueprint_data=b.blueprint_data,
                niche_label=b.blueprint_data.get("niche_label", "unknown"),
            )
            for i, b in enumerate(chosen)
        ]

        # Hand-build a target candidate from the first winner's grouped mechanics.
        seed = chosen[0].blueprint_data
        template = {
            k: seed[k]
            for k in ("hook_type", "pacing", "audio_type")
            if k in seed
        }
        candidate = BlueprintCandidate(
            rank=1,
            niche_label=top_niche,
            blueprint_template=template,
            evidence=MinerEvidence(
                matching_items=len(chosen),
                median_views=250_000,
                p90_views=1_200_000,
                trend_slope_4wk_pct=12.5,
                rationale="smoke-test synthetic evidence",
            ),
        )
        print(f"candidate template: {template}")
        print(f"hit content_item_ids: {[h.content_item_id for h in hits]}\n")

        writer = ContentWriter()

        for premise in PREMISES:
            package = writer.write(candidate, hits, db, premise)

            # Human-readable arc dump — surface only the fields the 4-failure
            # rubric needs (3 labeled shots + the shared mood-anchor + overlays
            # + caption). Skip braces/hashtags/grounding_ids/rationale: noise for
            # the read. mood_anchor is contracted identical across shots, so it
            # prints once.
            print("=" * 70)
            print(f"PREMISE: {premise}")
            print(f"MOOD-ANCHOR: {package.shots[0].mood_anchor}")
            print("-" * 70)
            for shot in package.shots:
                print(f"[{shot.arc_role.upper()}] {shot.cinematic_prompt}\n")
            print(f"OVERLAYS: {package.onscreen_text}")
            print(f"CAPTION:  {package.caption}")
            print("=" * 70 + "\n")

    
    finally:
        db.close()


if __name__ == "__main__":
    main()
