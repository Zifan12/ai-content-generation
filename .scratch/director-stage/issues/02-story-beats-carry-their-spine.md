# 02 — Story beats carry their own spine

**What to build:** Every story beat states its own non-negotiables as structured data, not only as prose.
A beat that drives toward a place names that place; a beat whose point is a physical event names that
event. Downstream stages can then be held to them by code instead of by hope.

Re-pitching pitch 47's payoff beat should come back as roughly:

    visual_line:     "Elfie lifts Will onto the bed and cradles him against her, his head lolling..."
    destination:     "the bed"
    required_action: "lifts Will onto the bed and cradles him"

Note `required_action` holds **one continuous move**, not one verb. That is the point of this ticket.

**Why the two halves are inseparable:** adding `required_action` while the pitcher's rule still says "ONE
action per beat: never three micro-motions crammed into one beat — split them across beats" forces the
pitcher to choose `lifts` **or** `cradles` for that beat. The field would be born already broken, and the
downstream check would protect one half of the move while the other half vanishes — which is the exact
bug this whole feature exists to kill.

**The rule conflict being resolved.** `ai_video_resources/Dan Kieft Cinematic Seedance Updated.md:471`,
verbatim: *"**One flowing motion per shot.** Write 'he speaks and immediately whips his head around in
panic' as one continuous action, not a setup sentence + an 'after he finishes…' block (that reads as two
shots)."*

Our pitcher's grain is finer — one sub-motion per beat — and since **every beat becomes a cut**, that
finer grain manufactures cuts in the middle of continuous actions, which L471 says reads as two shots.
The user watched pitch 47 do exactly this: it cuts from Will being dragged straight to Will lying on her
chest, because the lift was split off and then lost. A continuous move is ONE action however many
sub-motions it takes.

**Cite L471 only.** An earlier draft cited "Dan Kieft:51,471" and claimed the corpus "warns never to let
a continuous action span an unshown gap." Both wrong: L51 is a 6-SHOT CEILING (economy — merge actions so
you don't over-shoot), and L471's actual reason is that a split flowing move *reads as two shots*, a
prose-structure claim. Conclusion unchanged; support narrower than advertised.

**[inference]** L471 is from the OpenArt-frontend playbook `INDEX.md` flags "cherry-pick claims, never
adopt wholesale" — the same file whose Chinese-prompt rule ticket 01 deleted. Defensible to cherry-pick
here (it gives its reason, and concerns prose structure not frontend mechanics) but **untested on the
Higgsfield CLI**. If flowing-motion beats ever render worse, this is the assumption to pull.

**Schema decision (encodes the nullable call — user, 2026-07-15):**

    destination:     str | None = None   # not every story has one; the check skips when None
    required_action: str | None = None   # nullable ONLY for backwards compatibility, see below

`required_action` is nullable **solely** because `story_json` rows already exist in Postgres — including
pitch 47, the only real evidence we have. A required field would make every legacy pitch unloadable and
destroy the validation plan. New pitches must always populate it.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The beat schema carries `destination` and `required_action` as above; both optional, both documented as to why.
- [ ] Existing `story_json` rows in Postgres still load and validate unchanged — verify against pitch 47 specifically.
- [ ] The pitcher prompt instructs both fields, and instructs `required_action` as one continuous move.
- [ ] The pitcher's "one action per beat" rule is re-scoped to one continuous move; the wording no longer forbids sub-motions within a single move.
- [ ] The craft gate's one-action check agrees with the new grain — a lift-and-cradle beat passes, a beat chaining unrelated actions still fails.
- [ ] A live re-pitch of pitch 47's event produces a payoff beat whose `required_action` contains the lift AND the cradle.
- [ ] Schema tests cover: both fields absent (legacy row loads), destination present, destination genuinely absent for a story with no destination.
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run mypy src/` all pass.
