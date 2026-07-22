# 02 — `--object` declaration + gate role

**What to build:** The operator can declare invented world elements with repeatable `--object <slug>` arguments alongside `--character`. The asset gate validates object reference directories with the character rules (missing/empty → halt with guidance; present-but-invalid → loud error) plus two object-specific rules: a `candidates/` subdirectory is ignored by validation, and upload order is characters first then objects, declaration order within each — the `imageN` numbering contract.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `--object <slug>` parsed with the lane's slug rules; duplicates rejected
- [ ] Object role validated by the gate: missing/empty dir halts before any LLM spend; invalid contents fail loud
- [ ] `candidates/` subdirectory never counts as promoted references
- [ ] Upload order deterministic: characters (declaration order) then objects (declaration order), files sorted within each
- [ ] Character behavior byte-identical to slice ② (regression)
