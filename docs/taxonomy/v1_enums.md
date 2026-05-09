# v1 Blueprint Enums

Source of truth for `format`, `hook_type`, `payoff_type` Literal values in `src/blueprints/schema.py`.

Locked: 2026-05-09
Bootstrapped from: 120 v0 BlueprintRecord rows
Source data: `data/taxonomy/{format,hook,payoff}_clusters.json`

## format (11 values)

```
ai_generated
tutorial
talking_head
storytime_narration
horror_story
meme_remix
compilation
aesthetic_showcase
animation
reaction
transformation
```

### Cluster mapping (v0 → v1)

| v1 enum | v0 strings absorbed |
|---|---|
| `ai_generated` | ai_generated, ai_generated_art, ai_generated_content, ai_generated_meme, ai_generated_showcase, ai_generated_story, ai_generated_visual, ai_generated_animation, ai_art_showcase, ai_story, ai_animated_story, ai_animation, ai_animation_narration, ai_animation_narrative, ai_animation_story, brainrot_animation |
| `tutorial` | tutorial, tutorial_cta, tutorial_demo, tutorial_walkthrough, listicle_tutorial, explainer |
| `talking_head` | talking_head, storytime_monologue, narrative_confession, news_report |
| `storytime_narration` | storytelling_narration, storytime_narration, narrated_storytime, compilation_narration |
| `horror_story` | narrated_horror_story, analog_horror, ambient_creepy_clip, educational_horror |
| `meme_remix` | brainrot_meme, meme_compilation, meme_remix, fan_edit, capcut_template_promo |
| `compilation` | compilation, compilation_or_clip, short_clip, listicle, movie_explained |
| `aesthetic_showcase` | aesthetic_compilation, aesthetic_montage, aesthetic_showcase, aesthetic_slideshow, showcase, filter_showcase, fashion_showcase, outfit_showcase, outfit_roundup |
| `animation` | animation, anime_clip, anime_edit |
| `reaction` | reaction, stitch_reaction, skit |
| `transformation` | process_timelapse, speedpaint, transformation |

### Notes
- `movie_explained` (singleton in v0) folded into `compilation`. Re-evaluate v2 if scrape volume grows.
- `fan_and_remix_edit` (2 members) folded into `meme_remix`.
- `ai_generated_content` and `ai_animation_narrative` clusters merged: distinction was too fuzzy.

---

## hook_type (8 values)

```
shocking_claim
curiosity_gap
visual_pattern_break
visual_aesthetic
character_intro
emotional_hook
direct_promise
pattern_interrupt
```

### Cluster mapping (v0 → v1)

| v1 enum | v0 strings absorbed |
|---|---|
| `shocking_claim` | shocking_claim, bold_claim, provocative_claim, urgency_claim, warning_statement, exclusive_reveal |
| `curiosity_gap` | curiosity_gap, curiosity_bait, curiosity_question, curiosity_statement, curiosity_title, question_hook, rhetorical_question, rhetorical_challenge |
| `visual_pattern_break` | visual_spectacle, visual_impact, visual_hook, visual_demonstration, visual_chaos, visual_novelty, visual_intrigue, visual_curiosity, visual_surprise, visual_transformation, visual_absurdity, visual_meme, absurdist_premise |
| `visual_aesthetic` | visual_aesthetic, visual_appeal, visual_atmosphere, visual_identity |
| `character_intro` | character_intro, character_introduction, character_action, character_problem |
| `emotional_hook` | emotional_mystery, emotional_premise, mystery_reveal, nostalgia_bait, collective_memory_prompt |
| `pattern_interrupt` | pattern_interrupt, shocking_action, shocking_visual, action_sequence |
| `direct_promise` | instructional_command, direct_promise, rule_list |

### Notes
- Three "visual_*" clusters from v0 (spectacle/novelty/absurdist) merged into `visual_pattern_break`. All share "look at this unusual thing" mechanic.
- `pattern_interrupt` kept separate from `visual_pattern_break` — pattern_interrupt covers non-visual disruptions (audio, text overlays). Borderline; reconsider v2.
- `visual_aesthetic` kept distinct — mood/atmosphere ≠ spectacle.

---

## payoff_type (7 values)

```
reveal
twist
humor
emotional_resolution
aesthetic_satisfaction
informational
call_to_action
```

### Cluster mapping (v0 → v1)

| v1 enum | v0 strings absorbed |
|---|---|
| `reveal` | reveal, creature_reveal, visual_reveal, practical_reveal, skill_reveal, style_reveal, tool_reveal, humor_reveal, comedic_reveal, emotional_reveal, twist_reveal |
| `twist` | twist, emotional_twist, cliffhanger, unresolved_mystery, open_question, narrative_tension, serialized_drama, escalating_revenge, vindication_and_opportunity, entertainment |
| `humor` | humor, humor_payoff, humor_release, absurdist_humor, comedic_absurdism, comedic_resolution |
| `emotional_resolution` | emotional_resolution, emotional_climax, emotional_peak, emotional_resonance, emotional_plea, emotional_tribute |
| `aesthetic_satisfaction` | aesthetic_satisfaction, aesthetic_payoff, aesthetic_reveal, aesthetic_loop, aesthetic_spectacle, mood_immersion, mood_satisfaction |
| `informational` | informational, actionable_resource, actionable_result, context_and_implications, recommendation, warning, skill_unlock, tutorial_tease, lore_expansion |
| `call_to_action` | call_to_action, community_decision, moral_argument |

### Notes
- `serialized_narrative_tension` cluster from v0 folded into `twist` (cliffhanger-style payoffs).
- `skill_and_tutorial` cluster from v0 split: tutorial-related members merged into `informational`; `lore_expansion` (singleton) also folded into `informational`.

---

## Total v1 enum count

- format: 11
- hook_type: 8
- payoff_type: 7
- **Sum: 26**

Below plan's 8-15 per field target on hook_type/payoff_type — data concentration justifies fewer.
