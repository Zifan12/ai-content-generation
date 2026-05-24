"""Rule-based mechanic ranker: groups BlueprintRecord rows by mechanic combos, scores each
group by views + trend slope, returns top-N BlueprintCandidates for RAG query generation."""
import math
import statistics
import argparse
import json

from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import cast, String, select

from src.models.blueprint import BlueprintRecord
from src.models.trend import RawContentItem
from src.miner.schemas import BlueprintCandidate, MinerEvidence
from src.miner.storage import persist_run  # noqa: E402
from src.database import SessionLocal  # noqa: E402

def _score_groups(group: dict[tuple, list], min_matching_items: int, recency_weeks: int, field_names: tuple) -> list:
    """Score one group dict (keyed by combo tuple) and return scored tuples.

    Each surviving combo (len >= min_matching_items) produces one tuple:
    (score, combo, matching_items, median_views, p90_views, trend_slope_4wk_pct, field_names).
    Slope is 0.0 when prior half-window is empty (all items are recent).
    """
    result = []
    for combo, items_list in group.items():
        if len(items_list) < min_matching_items:
            continue

        median_views = int(statistics.median([item.views for item in items_list]))
        p90_views = int(statistics.quantiles([item.views for item in items_list], n=10)[8])
        
        mid_cutoff = datetime.now(timezone.utc) - timedelta(weeks=recency_weeks // 2)


        recent_bucket = [item for item in items_list if (item.published_at if item.published_at.tzinfo else item.published_at.replace(tzinfo=timezone.utc)) >= mid_cutoff]
        prior_bucket  = [item for item in items_list if (item.published_at if item.published_at.tzinfo else item.published_at.replace(tzinfo=timezone.utc)) < mid_cutoff]


        if not prior_bucket or not recent_bucket:
            trend_slope_4wk_pct = 0.0
        else:
            recent_median = statistics.median([recent.views for recent in recent_bucket])
            prior_median = statistics.median([prior.views for prior in prior_bucket])
            trend_slope_4wk_pct = (recent_median / prior_median) - 1

        score = math.log10(len(items_list)) * math.log10(max(median_views, 1)) * (1 + max(trend_slope_4wk_pct, -0.9))

        result.append((score, combo, len(items_list), median_views, p90_views, trend_slope_4wk_pct, field_names))
    
    return result

def rank_candidates(db: Session, niche_label: str, recency_weeks: int=4, min_matching_items: int=5, top_n: int=10) -> list[BlueprintCandidate]:
    """Rank mechanic combos by composite score for a given niche.

    Filters to extractor_version v3.1 rows published within recency_weeks.
    Groups by three combo dimensions, scores each, returns top_n BlueprintCandidates sorted desc.
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=recency_weeks) 
    stmt = (
        select(BlueprintRecord, RawContentItem)
        .join(RawContentItem, BlueprintRecord.content_item_id == RawContentItem.id)
        .where(BlueprintRecord.extractor_version == "v3.1")
        .where(RawContentItem.published_at >= cutoff_date)
        .where(cast(BlueprintRecord.blueprint_data["niche_label"], String) == f'"{niche_label}"')
    )
    rows = db.execute(stmt).all()

    group3 = defaultdict(list)
    group2 = defaultdict(list)
    group_aesthetic = defaultdict(list)

    for blueprint, item in rows:
        group3[(blueprint.blueprint_data["hook_type"], blueprint.blueprint_data["pacing"], blueprint.blueprint_data["audio_type"])].append(item)
        group2[(blueprint.blueprint_data['primary_emotion'], blueprint.blueprint_data['loop_type'])].append(item)
        group_aesthetic[(tuple(blueprint.blueprint_data['aesthetic_descriptors'][:2])), blueprint.blueprint_data['hook_type']].append(item)
    
    result3 = _score_groups(group3, min_matching_items, recency_weeks, field_names=("hook_type", "pacing", "audio_type"))
    result2= _score_groups(group2, min_matching_items, recency_weeks, field_names=("primary_emotion", "loop_type"))
    result_aes = _score_groups(group_aesthetic, min_matching_items, recency_weeks, field_names=("aesthetic_descriptors", "hook_type"))

    all_result = result3 + result2 + result_aes

    all_result.sort(key=lambda x: x[0], reverse=True)

    candidates = []
    for index, (score, combo, matching, median_views, p90, slope, fields) in enumerate(all_result[:top_n]):

        blueprint_template = dict(zip(fields, combo))
       
        candidate = BlueprintCandidate(
            rank=index + 1,
            niche_label=niche_label,
            blueprint_template=blueprint_template,
            evidence=MinerEvidence(
                matching_items=matching, 
                median_views=median_views,
                p90_views=p90,
                trend_slope_4wk_pct=slope,
                rationale=f"{blueprint_template} (n={matching}, median={median_views})"
            )
        )

        candidates.append(candidate)

    return candidates



def main():
    """Parse CLI args, run ranker against the configured DB, emit JSON to stdout or file.

    Optionally persists the run to miner_rankings when --persist is passed.
    """
    parser = argparse.ArgumentParser(description="Rank viral mechanic combos for a niche using rule-based scoring.")

    parser.add_argument("--niche", required=True)
    parser.add_argument("--recency-weeks", type=int, default=4)
    parser.add_argument("--min-items", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", required=False)
    parser.add_argument("--persist", action="store_true")

    args = parser.parse_args()

    db = SessionLocal()

    candidates = rank_candidates(db, niche_label=args.niche, recency_weeks=args.recency_weeks, min_matching_items=args.min_items, top_n=args.top_n)
    output_json = json.dumps([c.model_dump() for c in candidates], indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
    else:
        print(output_json)

    if args.persist:
        persist_run(db, candidates, args.niche)


if __name__ == "__main__": main()