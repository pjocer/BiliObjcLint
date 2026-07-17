# Auto Fix Codex-First Design

## Goal

Replace the Claude-specific repair package with a provider-neutral `auto_fix` module. The module always attempts a safe, silent repair with Codex CLI first, falls back to Claude CLI only when Codex cannot be launched or cannot return a structured result, and uses the existing unavailable flow when neither provider is usable.

## Scope

- Rename `scripts/claude/` to `scripts/auto_fix/` and replace Claude-specific internal names with provider-neutral names.
- Update only the necessary Xcode entry, imports, documentation, and metrics/config references required by that rename.
- Remove the complete `claude_autofix` configuration chain. There is no legacy parsing or runtime compatibility.
- Preserve lint rules, incremental discovery, local Pod discovery, ignore behavior, server storage, and non-autofix dashboard behavior.
- Do not commit, push, tag, or publish this work.

## Fixed Runtime Behavior

- Trigger: every non-empty lint result.
- Interaction: retain the existing initial review dialog and HTML details page.
- Execution: silent background repair only.
- Timeout: 120 seconds per provider attempt.
- Provider order: Codex CLI, then Claude CLI.
- Provider configuration: none. Each CLI uses its own existing installation, authentication, and environment.

The removed configuration includes trigger, mode, API base URL, tokens, API key, model, nonessential-traffic flags, terminal mode, and VSCode mode.

## Components

### `auto_fix.models`

Normalize the canonical lint JSON fields into immutable repair targets. Only `file_path`, `rule_id`, `line`, `column`, `related_lines`, `context`, `code_hash`, `sub_type`, `message`, `severity`, and `violation_id` are accepted. Legacy `file` and `rule` fields are rejected.

Each target records an exact allowed file and inclusive edit range. Targets without a valid existing file or valid `related_lines` are not sent for automatic repair.

### `auto_fix.providers`

Discover and invoke providers in fixed order:

1. `codex exec --sandbox read-only --ephemeral`
2. `claude --print --permission-mode plan --tools Read`

Both providers receive the same prompt and JSON Schema. Providers are read-only and return a structured repair plan instead of editing files directly. Codex receives the prompt on stdin and uses `--output-schema`; Claude uses `--json-schema` and structured JSON output.

Provider fallback is allowed after executable discovery failure, launch failure, timeout, non-zero exit, or invalid structured output because neither provider has write access. A structurally valid but policy-invalid repair plan fails the repair instead of being sent to another provider.

### `auto_fix.edit_plan`

The repair plan contains:

```json
{
  "edits": [
    {
      "file_path": "/absolute/path/File.m",
      "start_line": 10,
      "end_line": 12,
      "replacement": "replacement source",
      "violation_ids": ["stable-id"]
    }
  ],
  "unfixed": [
    {
      "violation_id": "stable-id",
      "reason": "manual design decision required"
    }
  ]
}
```

Validation requires:

- Every edited file exactly matches a file present in the requested violations.
- Every edit names at least one requested violation in the same file.
- The edit range is contained by the union of the named violations' `related_lines` ranges.
- Ranges in one file do not overlap.
- The source file has not changed since the repair session snapshot.
- The replacement is valid UTF-8 text and the resulting file remains non-empty.

### `auto_fix.scope`

`related_lines` remains the lint review range; it is not assumed to be the complete repair range. For a supported symbol rename, `auto_fix.scope` derives additional exact code-reference lines before the provider runs. The `method_naming/uppercase_start` resolver currently authorizes same-file Objective-C selector declarations and call sites, while excluding comments and string literals.

The provider receives the original violation range, every derived repair range, and the deterministic old/new selector names. After edits are applied, a local postcondition requires the old selector to be absent from every discovered code reference. Missing a call site causes rollback before lint verification.

All edits are prepared in memory first. Files are replaced atomically using same-directory temporary files, preserving file mode. If any replacement fails, files already replaced by this session are restored from their snapshots.

Repair requests are serialized per `AutoFixer` instance. Rollback only touches files actually written by that session and refuses to overwrite a file changed again after the automatic edit.

### `auto_fix.fixer`

`AutoFixer` coordinates UI actions, target normalization, prompt generation, provider fallback, plan validation/application, and reporting. The existing ignore and HTML review flows remain intact.

The fixer reports success only when at least one validated edit is applied. Provider exit code alone is never considered a successful repair. The result includes provider name, applied edit count, affected file count, and unfixed count.

## Data Flow

1. The existing lint command writes canonical JSON.
2. `auto_fix.cli` loads JSON and constructs `AutoFixer`.
3. The user opens details and requests a single or batch repair.
4. The fixer normalizes targets and snapshots all allowed source files.
5. The scope resolver distinguishes the review range from any additional exact repair ranges; prompt builder emits only those permitted ranges.
6. Codex or Claude returns a structured repair plan without write access.
7. The edit-plan validator rejects out-of-scope or stale edits.
8. Valid edits are applied atomically.
9. The existing lint CLI rechecks the target files. If a target violation remains or verification cannot complete, the session restores every applied file from its snapshot.
10. The UI displays verified applied and unfixed counts. Invalid/no-op/unverified plans are failures.

## Configuration and Metrics Cleanup

- Delete `ClaudeAutofixConfig` and `LintConfig.claude_autofix`.
- Delete the `claude_autofix` default YAML block and loader parsing.
- Remove `claude_autofix` from sanitized config snapshots and documentation examples.
- Autofix metrics remain under the existing generic top-level `autofix` payload, but use fixed values (`enabled=true`, `trigger=any`, `mode=silent`) and include the selected provider when available.
- Historical changelog entries are not rewritten.

## Error Handling

- Neither CLI found: existing unavailable dialog/exit path with a provider-neutral message.
- Provider timeout or launch failure: try the next provider.
- Both providers fail: report the combined failure without modifying files.
- Invalid or out-of-scope plan: fail without fallback and without modifying files.
- No edits returned: report that no automatic repair was produced.
- Concurrent source change: reject the plan as stale.
- Concurrent repair request: serialize it behind the active repair session.
- Partial apply failure: restore all files touched by the session.
- Target lint verification failure: restore all files touched by the session.
- User edit after automatic apply: preserve the user edit and report that rollback was refused.

## Testing

Tests cover:

- Canonical lint JSON normalization and rejection of legacy fields.
- Prompt generation with non-empty file paths, rule IDs, ranges, and context.
- Method rename scope expansion across same-file call sites, excluding comments and strings.
- Rollback when a provider renames a declaration but misses an authorized call site.
- Codex-first discovery and Claude fallback.
- Exact Codex and Claude command construction with read-only permissions.
- Structured output parsing and invalid-output fallback.
- File/range/violation validation, overlapping ranges, stale snapshots, no-op plans, atomic multi-file application, and rollback.
- Single and batch HTTP endpoints forwarding canonical violations.
- Removal of `claude_autofix` configuration and `scripts/claude` references.
- Existing full test suite.

## Non-Goals

- Changing lint rules or their range detection.
- Changing local Pod or git-diff discovery.
- Adding provider configuration or model selection.
- Adding terminal or editor-assisted repair modes.
- Changing ignore-cache semantics.
- Reworking dashboard storage beyond removing the deleted configuration dependency.
