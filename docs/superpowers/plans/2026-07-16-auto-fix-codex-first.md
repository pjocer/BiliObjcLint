# Auto Fix Codex-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagents are not authorized for this task.

**Goal:** Replace the Claude-specific direct-edit repair chain with a provider-neutral, Codex-first, validated structured-edit `auto_fix` module.

**Architecture:** Canonical lint violations are normalized once, converted into a provider-independent structured-repair prompt, and sent first to Codex then to Claude using read-only CLI modes. A local edit-plan layer validates exact files, violation IDs, ranges, and source snapshots before applying all changes atomically. The existing UI and ignore flows remain, while the old configurable Claude execution modes are deleted.

**Tech Stack:** Python 3.9+, standard library (`dataclasses`, `json`, `subprocess`, `tempfile`, `pathlib`), pytest, Bash/Xcode Build Phase integration.

## Global Constraints

- Do not commit, push, tag, or publish.
- Do not change lint rule behavior, git-diff discovery, local Pod discovery, or ignore semantics.
- Do not preserve compatibility for `scripts/claude`, `ClaudeFixer`, `claude_autofix`, legacy `file`/`rule` repair payloads, terminal mode, VSCode mode, or provider API configuration.
- Provider order is fixed: Codex CLI, then Claude CLI.
- Providers must not receive write permission.
- A provider process exit code is not repair success; at least one validated edit must be atomically applied.

---

### Task 1: Canonical repair targets and prompt contract

**Files:**
- Create: `scripts/auto_fix/models.py`
- Modify: `scripts/auto_fix/prompt_builder.py`
- Test: `tests/test_auto_fix_models.py`
- Test: `tests/test_auto_fix_prompt.py`

**Interfaces:**
- Produces: `FixViolation.from_dict(data: dict) -> FixViolation`
- Produces: `normalize_violations(items: List[dict]) -> Tuple[List[FixViolation], List[str]]`
- Produces: `build_fix_prompt(violations: Sequence[FixViolation]) -> str`

- [ ] Write tests proving canonical `file_path`/`rule_id` data is preserved, old `file`/`rule` data is rejected, invalid ranges are rejected, and a real prompt contains file, rule, violation ID, range, and context.
- [ ] Run `HOME=/tmp ./.venv/bin/python3 -m pytest tests/test_auto_fix_models.py tests/test_auto_fix_prompt.py -q` and confirm import/API failures.
- [ ] Implement the immutable target model and canonical structured-edit prompt.
- [ ] Re-run the focused tests and confirm they pass.
- [ ] Inspect `git diff` without committing.

### Task 2: Read-only Codex-first provider runner

**Files:**
- Create: `scripts/auto_fix/providers.py`
- Test: `tests/test_auto_fix_providers.py`

**Interfaces:**
- Produces: `ProviderResult(provider: str, plan: dict, diagnostics: str)`
- Produces: `AutoFixProviderRunner.run(prompt: str) -> ProviderResult`
- Consumes: `REPAIR_PLAN_SCHEMA` from `scripts/auto_fix/edit_plan.py`

- [ ] Write tests with fake executables/subprocess results proving Codex is selected first, Claude is used after missing/failed/timeout/invalid Codex output, neither provider returns a combined unavailable error, and both command lines are read-only.
- [ ] Run `HOME=/tmp ./.venv/bin/python3 -m pytest tests/test_auto_fix_providers.py -q` and confirm missing implementation failures.
- [ ] Implement executable discovery for common paths plus `PATH`, Codex stdin/schema/output-file invocation, Claude stdin/schema JSON invocation, and structured result parsing.
- [ ] Re-run the focused tests and confirm they pass.
- [ ] Inspect `git diff` without committing.

### Task 3: Validated atomic edit application

**Files:**
- Create: `scripts/auto_fix/edit_plan.py`
- Test: `tests/test_auto_fix_edit_plan.py`

**Interfaces:**
- Produces: `REPAIR_PLAN_SCHEMA: dict`
- Produces: `RepairSession(targets: Sequence[FixViolation])`
- Produces: `RepairSession.apply(plan: dict) -> ApplyResult`
- Produces: `RepairSession.rollback() -> None`
- Produces: `ApplyResult(applied_edits: int, affected_files: int, unfixed: int)`

- [ ] Write tests for allowed single-file replacement, same-file descending edits, external Local Pod targets, unknown files, unknown violation IDs, out-of-range edits, overlaps, stale snapshots, empty/no-op plans, mode preservation, multi-file application, and rollback after a simulated replacement failure.
- [ ] Run `HOME=/tmp ./.venv/bin/python3 -m pytest tests/test_auto_fix_edit_plan.py -q` and confirm missing implementation failures.
- [ ] Implement snapshots, plan validation, in-memory transformations, same-directory temporary writes, atomic replacement, and rollback.
- [ ] Re-run the focused tests and confirm they pass.
- [ ] Inspect `git diff` without committing.

### Task 4: Rename the package and integrate `AutoFixer`

**Files:**
- Rename: `scripts/claude/` to `scripts/auto_fix/`
- Modify: `scripts/auto_fix/__init__.py`
- Modify: `scripts/auto_fix/cli.py`
- Modify: `scripts/auto_fix/fixer.py`
- Modify: `scripts/auto_fix/http_server.py`
- Modify: `scripts/auto_fix/html_report.py`
- Modify: `scripts/auto_fix/dialogs.py`
- Modify: `scripts/auto_fix/utils.py`
- Test: `tests/test_auto_fix_fixer.py`
- Modify test: `tests/test_http_server.py`

**Interfaces:**
- Produces: `AutoFixer(config: dict, project_root: str, run_id=None, project=None)`
- Consumes: normalized targets, provider runner, and repair session from Tasks 1-3.

- [ ] Write tests proving `AutoFixer` reports unavailable when both CLIs are absent, applies and verifies a valid provider plan, rolls back failed verification, rejects invalid/no-op plans, records the selected provider, and single/batch HTTP paths forward canonical violation dictionaries including ranges and IDs.
- [ ] Run focused tests and confirm they fail against the Claude-specific implementation.
- [ ] Mechanically rename the package, imports, logger names, debug markers, and user-facing provider-specific copy.
- [ ] Remove configurable trigger/mode/API environment/terminal/VSCode code and integrate the fixed provider runner and edit plan.
- [ ] Re-run focused tests and confirm they pass.
- [ ] Inspect `git diff` without committing.

### Task 5: Remove the obsolete AI configuration chain

**Files:**
- Modify: `config/default.yaml`
- Modify: `scripts/core/lint/config.py`
- Modify: `scripts/core/lint/metrics.py`
- Modify: `LINTSERVER.md`
- Test: `tests/test_auto_fix_config_removal.py`
- Modify tests: config/metrics tests where present

**Interfaces:**
- `LintConfig` no longer exposes `claude_autofix`.
- Generic top-level `autofix` metrics remain with fixed `enabled=true`, `trigger=any`, and `mode=silent` values.

- [ ] Write a governance test asserting no runtime/default config references to `ClaudeAutofixConfig` or `claude_autofix` remain and generic autofix payloads still build.
- [ ] Run the focused test and confirm it fails.
- [ ] Remove the dataclass, loader/default config entries, secret scrubbing branch, and metrics dependency; replace metrics values with fixed behavior.
- [ ] Re-run focused config and metrics tests.
- [ ] Inspect `git diff` without committing.

### Task 6: Update the Xcode entry and active documentation

**Files:**
- Modify: `config/code_style_check.sh`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/DEVELOPMENT.md`
- Modify: `scripts/__init__.py`
- Test: `tests/test_auto_fix_governance.py`

**Interfaces:**
- Xcode entry invokes `scripts/auto_fix/cli.py` with the same violations/config/project-root arguments.

- [ ] Write a governance test asserting the active runtime contains no `scripts/claude`, `from claude`, `ClaudeFixer`, or `claude_autofix` references while historical `CHANGELOG.md` is excluded.
- [ ] Run the governance test and confirm it fails.
- [ ] Update the entry path and active documentation to describe Codex-first automatic repair and Claude fallback without configuration examples.
- [ ] Run `bash -n config/code_style_check.sh` and the governance test.
- [ ] Inspect `git diff` without committing.

### Task 7: Integration and regression verification

**Files:**
- All files changed above

**Interfaces:**
- End-to-end input is canonical lint JSON; output is either validated applied edits or a failure with no provider-written files.

- [ ] Run all new autofix tests together and confirm they pass.
- [ ] Run `HOME=/tmp PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python3 -m pytest tests -q` and record the exact pass/fail/warning count.
- [ ] Run `./.venv/bin/python3 -m py_compile` on every Python file under `scripts/auto_fix` plus changed core modules.
- [ ] Run `bash -n config/code_style_check.sh`.
- [ ] Search active runtime/docs for removed names and confirm only historical changelog references remain.
- [ ] Run a deterministic fake-provider integration test that applies a valid edit and rejects an out-of-range edit without invoking a real paid model.
- [ ] Check `git status --short` and `git diff --check`.
- [ ] Report results without committing or publishing.
