# PRD: POV Pipeline — slice ① (generic-topic path)

Status: ready-for-agent
Date: 2026-07-17
Evidence base: probe renders `render_taste_test/pov_probe/PROBE_SHEET.md` (2 paid probes, user-watch PASS), 6-agent corpus sweep + 3 video-researcher runs + Second Brain (Norman/Cooper) consult, all 2026-07-17. Grilling session resolved every fork; decisions below are user-ratified.

## Problem Statement

The operator wants a new content lane: high-quality first-person POV (camera-as-eyes) short narrative videos for TikTok, made from either a bare topic ("deep sea") or a fully-formed idea ("transform into Ultraman, fire the spacium beam"). The existing pipelines (Exilus front-end, staged director) are built for third-person character stories and are paused. There is currently no repeatable path from a topic to a rendered POV video: the register was just proven by hand-built probe prompts, but every new story would mean hand-crafting prompts from scratch, re-remembering the fragile POV grammar rules each time, and risking the documented failure classes (angle-switch, body leak, beat-free actions, banned words) that the corpus says kill POV renders.

## Solution

A slim pipeline: the operator runs one command with either `--topic` (pipeline generates 3-5 POV story pitches, operator picks one) or `--idea` (operator's text IS the pitch, slate skipped). The picked pitch is developed by an LLM stage into a countable-beat POV script with world-in-prose and diegetic audio. A code compiler — not the LLM — slots the script into the probe-proven POV prompt skeleton, scrubs banned vocabulary, and emits a render sheet containing the final prompt, a copy-paste CLI render command, and a watch checklist. The operator renders manually (480p sanity pass is mandatory, then 720p/1080p), watches, and verdicts. Every proven POV grammar rule lives in versioned config with evidence tags, not in anyone's memory.

Slice ① covers invented (generic) worlds only — text-only prompts, no reference images, which is exactly what the probes proved. Recognizable-IP topics (which need research + reference assets) are slice ②.

## User Stories

1. As the operator, I want to run one command with `--topic "<seed>"`, so that I get 3-5 distinct POV story pitches to choose from without authoring them myself.
2. As the operator, I want to run the same command with `--idea "<full concept>"`, so that my already-formed story goes straight to script development without a redundant pitch slate.
3. As the operator, I want each pitch to state who I am, where I am, what happens, and the turn, so that I can judge a pitch in seconds.
4. As the operator, I want to pick one pitch interactively, so that no story is developed without my taste call.
5. As the operator, I want the picked pitch developed into 4-8 countable action beats, so that the render never receives the beat-free action lines that measurably render in zero frames.
6. As the operator, I want each beat limited to 1-2 physical actions, so that beats don't dilute into un-renderable laundry lists.
7. As the operator, I want the script to target Setup → Turn → Button and be allowed to collapse the button into the climax, so that a ≤15s clip is never forced into a rushed resolution beat.
8. As the operator, I want emotion expressed only as physical tells, so that the story reads on screen without a narrator.
9. As the operator, I want the world described in concrete prose (named light source, depth-layered nouns, particulates), so that text-only worlds hit the quality bar the probes demonstrated.
10. As the operator, I want the script stage to choose 10s or 15s from the beat count, so that duration follows the story instead of a fixed default.
11. As the operator, I want in-scene audio authored as diegetic events per beat, so that sound carries the story without voiceover.
12. As the operator, I want any spoken line placed on a non-final beat and sized to its seconds, so that dialogue avoids the documented end-of-clip video-degradation and audio-artifact zones.
13. As the operator, I want the final prompt assembled by code around fixed verbatim POV clauses, so that the load-bearing grammar (camera-IS-eyes, unseen protagonist, hands visible, "No cuts, no zooms, natural head movement only", constraints block) can never drift with LLM phrasing.
14. As the operator, I want banned vocabulary scrubbed from the compiled prompt, so that documented quality-killers (dead intensifiers, "cinematic" alone, glow/glimmer flicker words) never reach a paid render.
15. As the operator, I want a render sheet with the prompt, a copy-paste CLI command, cost statement, and watch checklist, so that nothing is retyped between pipeline and render (transcription slips eliminated).
16. As the operator, I want the 480p sanity render stated as a mandatory step on every sheet, so that "the prompt looked fine" can never justify skipping the only gate that sees reality.
17. As the operator, I want the watch checklist to name the POV-specific failure modes (angle switch, body leak, beat teleport, text leak), so that my watch verdict checks the right things.
18. As the operator, I want every POV grammar rule stored in versioned render config with an evidence tag, so that future sessions inherit proven rules instead of re-deriving them.
19. As the operator, I want pipeline artifacts saved as plain files per run, so that any run can be re-read, re-rendered, or post-mortemed without a database.
20. As the operator, I want LLM seats resolved through the existing provider config, so that model swaps stay a YAML edit.
21. As the operator, I want LLM calls traced in the existing observability stack, so that per-seat cost is measurable.
22. As the operator, I want pitch fields code-copied into downstream artifacts rather than LLM-echoed, so that story facts cannot mutate between stages.
23. As the operator, I want the location-still escalation lever documented on the render sheet (eye-vantage framing, role-named in prose, A/B against text-only), so that a bland world has a pre-registered fix that doesn't repeat the pitch-51 camera-hijack.
24. As the operator, I want posted videos recorded with the existing manual bookkeeping scripts, so that the 30-post experiment discipline carries over with zero new plumbing.

## Implementation Decisions

- **One new driver script with two mutually exclusive entry flags** (`--topic`, `--idea`). Topic mode: pitcher seat generates a 3-5 pitch slate, operator picks by number. Idea mode: the operator's text is wrapped as the picked pitch verbatim; no slate, no pitcher call.
- **Two LLM seats** (pitcher, script), resolved via the existing per-seat provider factory; creative seats stay on the Pro-tier model per standing cost decision. Per-caller `max_tokens` overrides (the repo's most-repeated truncation bug class). Both seats traced with the existing tracing decorator.
- **Script stage contract:** input = picked pitch; output = scene setting, duration choice (10 or 15), ordered beats (each: 1-2 physical actions, optional dialogue line with speaker, diegetic audio events), world prose block. Beat budget: 4-6 beats at 10s (interpolated from corpus, labeled as such), 5-8 at 15s (counted from worked corpus examples). Dialogue constraints enforced at this stage: never on the final beat; line length sized to beat seconds; plain quoted prose (the native-platform `()/<>/{}` audio symbols are unverified on Higgsfield and not used). Structural violations (dialogue on final beat, beat budget breach) trigger ONE bounded repair re-call with the violation named, then hard fail — the house bounded-retry convention.
- **Compiler is deterministic code, not an LLM.** It composes: fixed POV skeleton clauses verbatim (single-continuous-shot camera-as-eyes clause, unseen-protagonist device, hands-visible line, the mandatory anti-drift constraint "No cuts, no zooms, natural head movement only", constraints block including no-watermark/logo/text/subtitles and no-extra-hands) + the script's beats as prose-chained action + `Audio:` prose lines. It scrubs the kill-list (dead intensifiers; "cinematic" without specifics; glow/glimmer replaced by steady-intensity/diffuse wording — candidate-strength, evidence-tagged). Body target 60-100 words excluding fixed clauses. No bracketed timestamps ever.
- **Story facts are code-copied** from pitch → script → sheet (same trust-code-over-LLM doctrine as StoryArchitect and content_writer).
- **Render sheet artifact** per run: final prompt, English mirror only (slice ① probes replicated proven English showcase prompts; the Chinese-translation gate is a separate untested decision and does not apply to this lane yet), copy-paste CLI command with params (seedance_2_0, 9:16, chosen duration, 480p), cost statement from measured rates, mandatory-ladder wording (480p sanity → 720p → 1080p finals), watch checklist naming POV failure modes, and the location-still escalation lever instructions.
- **New POV grammar block in the render rules config**, every line carrying an evidence tag (probe artifact, corpus file:line, or candidate marker). First-person camera vocabulary promoted from corpus-only to validated-by-probe status.
- **Artifacts are plain files** under a per-run output directory (slug-named): pitch slate, picked pitch, script, prompt, render sheet. No new DB tables, no migrations.
- **Human gates only:** pitch pick and watch verdict. No LLM craft judge in slice ① — one is added only when real runs show a recurring defect pattern. Rationale is Norman's slip/mistake split: prompt eyeballing catches slips; only the 480p render catches mistakes, hence the mandatory ladder.
- **Product constants:** 9:16 vertical; native in-scene audio always on; sparing in-scene character dialogue allowed; NO narrator voiceover; no on-screen text of any kind (native-quality-v2 carried over).
- **Assets verdict:** text-only worlds by default (probe-proven). References are for accuracy, not quality — required only for recognizable canon subjects, which are slice ② by definition. The single documented lever for a bland world is one location still: eye-vantage framed, role-named in prose per positional binding convention, never re-described in text, first use A/B'd against text-only.

## Testing Decisions

- Good tests assert external behavior at two seams only; no implementation-detail assertions.
- **Seam 1 — pipeline driver with fake LLM seats** (house pattern; prior art: Exilus orchestration tests, StoryArchitect tests). Asserts: topic mode produces a slate then honors the pick; idea mode skips the pitcher entirely (fake records zero pitcher calls); artifacts written per run; beat budgets enforced; duration choice ∈ {10, 15}; pitch fields byte-identical between input pitch and sheet (code-copy proof); dialogue-on-final-beat input from the fake triggers the bounded repair/rejection path.
- **Seam 2 — compiler as a pure function.** Asserts: fixed skeleton clauses present verbatim; kill-list words absent from output regardless of input prose; no bracketed timestamps; word budget respected; CLI command matches chosen params; cost line matches measured rate table.
- Render quality, watch verdicts, and paid-CLI behavior are deliberately untested in CI — they are manual gates by design.

## Out of Scope

- **Slice ② (IP topics):** canon research, reference-asset sourcing/building (character key-art, prop sheets, canon-costumed POV limbs), the character-speaks-into-lens render gate and its documented one-discrete-eye-beat technique. Separate PRD when slice ① is done.
- Narrator/voiceover of any kind; on-screen text.
- Automated LLM quality judges (trigger: recurring defect pattern in real runs).
- Render executor automation; posting automation; new closed-loop plumbing (existing manual recording scripts are used as-is).
- Chinese prompt translation for this lane (separate unvalidated gate).
- Long-form / multi-generation POV; DB persistence of runs.
- Seedance 2.5 anything.

## Further Notes

- Probe evidence (Tier-1-grade: paid renders + user watch, 2026-07-17): POV register holds 10s continuous; the BUG-031 motion class (vertical lift toward viewer) animates beat-by-beat in POV register; text-only worlds pass the quality bar; 60cr total, billing-verified.
- Open corpus tensions, flagged not resolved: (1) whether 15s single generations degrade in their final seconds — one doc claims yes, another demonstrates a 15s one-take as a capability; our own 15s renders passed on a different lane. Treat 15s + dialogue-near-end as the risky combination (hence the dialogue-placement rule). (2) Seedance 2.0 audio architecture (joint vs post-hoc) is contested between two corpus sources; does not change any slice ① decision.
- The corpus has no worked example of a QUIET (non-action) single-take POV narrative. First calm story rendered through this pipeline is its own informal gate; if it underdelivers, that is new evidence, not a pipeline defect.
- Known corpus-integrity side-finding from the research sweep (not blocking): two POV prompts in the happyhorse README are orphaned from `all-prompts.json` (ID collision with unrelated content) — worth a one-line INDEX.md caveat someday.
