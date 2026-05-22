import math
import statistics
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy.orm import Session

from src.models.blueprint import BlueprintRecord
from src.models.trend import RawContentItem
from src.miner.schemas import BlueprintCandidate, MinerEvidence

def _score_groups(group: dict[tuple, list], min_matching_items: int, recency_weeks: int, field_names: tuple) -> list:

    result = []
    for combo, items_list in group.items():
        if len(items_list) < min_matching_items:
            continue

        median_views = statistics.median([item.views for item in items_list])
        p90_views = statistics.quantiles([item.views for item in items_list], n=10)[8]
        
        mid_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(weeks=recency_weeks // 2)


        recent_bucket = [item for item in items_list if item.published_at >= mid_cutoff]
        prior_bucket = [item for item in items_list if item.published_at < mid_cutoff]


        if not prior_bucket:
            trend_slope_4wk_pct = 0.0
        else:
            recent_median = statistics.median([recent.views for recent in recent_bucket])
            prior_median = statistics.median([prior.views for prior in prior_bucket])
            trend_slope_4wk_pct = (recent_median / prior_median) - 1

        score = math.log10(len(items_list)) * math.log10(max(median_views, 1)) * (1 + max(trend_slope_4wk_pct, -0.9))

        result.append((score, combo, len(items_list), median_views, p90_views, trend_slope_4wk_pct, field_names))
    
    return result

def rank_candidates(db: Session, niche_label: str, recency_weeks: int=4, min_matching_items: int=5, top_n: int=10) -> list[BlueprintCandidate]:
    cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=recency_weeks) 
    rows = (
        db.query(BlueprintRecord, RawContentItem)
        .join(RawContentItem, BlueprintRecord.content_item_id == RawContentItem.id)
        .filter(BlueprintRecord.extractor_version == "v3.1")
        .filter(RawContentItem.published_at >= cutoff_date)
        .filter(BlueprintRecord.blueprint_data["niche_label"].as_string() == niche_label)
        .all()
    )

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

        