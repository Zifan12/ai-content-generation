# 03 — Structured world elements + motion-only compile

**What to build:** The script seat receives the declared object list and writes each object's world description in its own structured field (slug + description). When an object has promoted references, the compiler drops that description from the body and substitutes exactly one positional binding sentence ("the X shown in imageN"); action/camera/style/audio prose compiles untouched. Binding sentences are word-budget exempt; the floor applies to the post-drop body. The render sheet gains the object-reference watch items (static-hijack / style-coherence checks). A story with no declared objects compiles byte-identical to today.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] Script schema carries per-object world-element entries (slug + description) populated by the seat
- [ ] Bound object: description dropped, one binding sentence emitted, `imageN` matches upload order
- [ ] Both-descriptions-on-screen impossible by construction (field drop, no prose surgery)
- [ ] Binding sentences exempt from authored-body word budget; floor applies post-drop
- [ ] Sheet watch items: motion present (not an animated painting), cross-object style coherence (first-use gate), fallback note (composed still + crops)
- [ ] No-object run: compiled output byte-identical (regression test)
