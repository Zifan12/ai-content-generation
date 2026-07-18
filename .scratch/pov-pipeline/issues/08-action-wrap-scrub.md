# 08 — Action-wrap scrub gap-close in the POV compiler

**What to build:** A POV script whose prose contains documented filter-risk action
vocabulary (fight/battle/destroy, kill/brutal/attack, punch/slash, blood) compiles into a
prompt carrying the corpus substitution phrases instead — the same doc-19 §3 table the
scene lane already declares — so a combat payoff beat can never reach a paid render
wearing a word the filter is documented to kill. The age-word row of that table
(boy/girl/child/kid/young → role description) is NOT a mechanical substitution and stays
out of the compiler; it is script-seat authoring guidance, revisit with ticket 11's craft
rule if a real script ever emits one.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Compiled prompt never contains a listed filter-risk action word from any
      script-authored field (actions, dialogue, audio, world/scene/protagonist prose)
- [ ] Each listed word is replaced by its table substitution phrase, word-boundary,
      case-insensitive — same semantics as the existing glow/glimmer pass
- [ ] Substitution rows live in the POV grammar config block with an evidence tag,
      following the existing duplicate-don't-cross-read precedent
- [ ] Existing kill-list behavior (intensifiers, cinematic, glow/glimmer, brackets)
      unchanged — full existing compiler test file still green
