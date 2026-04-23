# Tool Calling Rules

Use this file when planning command execution and file-edit workflows.

## Workflow
1. Read current state before proposing edits.
2. State a short plan for non-trivial tasks.
3. Apply minimal scoped changes.
4. Verify with targeted commands/tests.
5. Summarize what changed and what was verified.

## Command Rules
- Prefer fast discovery tools (`rg`, targeted file reads).
- Avoid broad or destructive commands unless explicitly requested.
- If command output is large, extract only relevant lines.
- Run the smallest test/check that validates the change.

## Editing Rules
- Do not touch unrelated files.
- Preserve existing style and architecture patterns.
- Prefer small, reviewable diffs over sweeping rewrites.
- Update docs/config when behavior changes.

## Safety Rules
- Never run destructive repo commands without explicit approval.
- Confirm assumptions before major architectural edits.
- Keep secrets out of files and logs.

## Verification Rules
- Validate syntax/lint/tests relevant to changed area.
- If full test suite is skipped, state that explicitly.
- For bug fixes, include reproduction and proof of fix.

## Reporting Rules
- Report findings/issues first when asked for review.
- Include file references for changed areas.
- Keep summaries concise and action-oriented.
