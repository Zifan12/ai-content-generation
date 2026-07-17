# 04 — Script craft enforcement + bounded repair

**What to build:** structural validation of the script seat's output, in code: dialogue never on the final beat; per-beat action count ≤2; beat count within the duration's budget (4-6 @10s, 5-8 @15s); duration ∈ {10, 15}. A violation triggers ONE bounded repair re-call with the violation named to the model (house bounded-retry convention, same shape as the craft gate → architect repair loop), then hard fail loud — never a silent pass-through. Repair prompts re-target the script seat only; the pitch is never regenerated.

**Blocked by:** 03 — Idea mode end-to-end.

**Status:** closed

- [x] Each violation class has a test: fake seat returns a violating script, repair path fires exactly once, repaired output accepted
- [x] Unrepairable output (violation persists after one repair) fails loud with the violation in the error
- [x] Valid scripts pass through with zero repair calls (fake proves it)
- [x] Tests green; ruff/mypy clean
