# Executor passes LLM-written prompt text through cmd.exe (`shell=True`)

Status: ready-for-human (fix applied 2026-07-01 — awaiting paid-render validation)
Severity: Critical (AUD-C1, `docs/audits/2026-07-01-full-codebase-audit.md`)

`src/generation/executor.py:74-80` runs the Higgsfield CLI with `shell=(platform.system() == "Windows")` and a list argv containing `job.prompt` (raw LLM output; transitively Reddit-derived via pitch → premise → writer). On Windows, `list2cmdline` quoting does not neutralize cmd.exe's own metacharacter parser — a `"` inside the prompt closes the quoted region and any following `&`, `|`, `>`, `%VAR%` executes as shell syntax.

Fix direction:
1. Resolve the npm shim once via `shutil.which("higgsfield")` and call `subprocess.run(argv, shell=False)` — removes cmd.exe entirely (the standard fix for npm `.cmd` shims; `shutil.which` walks PATHEXT).
2. Defense in depth: strip `"` and cmd metacharacters from prompt strings in `_param_flags` — render prompts never legitimately need them.

Human decision needed: fix mechanism choice (which of the two, or both) + verify the resolved `.cmd` path actually executes via CreateProcess on this machine before relying on it.

## Comments

**2026-07-01 — BOTH mechanisms applied** (user-authorized "just write it"):
1. `_run_cli` now resolves the CLI via `shutil.which(argv[0])` and runs `shell=False`; raises a clear `FileNotFoundError` when the CLI isn't on PATH. `import platform` removed.
2. `_sanitize_prompt` added and wired into `_param_flags`: `"` → `'`, strips `&|<>^%`, collapses whitespace — because CreateProcess still routes `.cmd` files through cmd.exe internally ("BatBadBut" class), so `shell=False` alone is necessary but not sufficient; sanitization is the effective mitigation for the argument-parsing layer.

Validated: 111/111 tests (monitor+generation+cli), ruff + mypy clean on the file. REMAINING before closing: one real render on this machine to confirm the `which`-resolved `.cmd` executes and Higgsfield accepts the sanitized prompts (fold into the next paid render — no dedicated spend).