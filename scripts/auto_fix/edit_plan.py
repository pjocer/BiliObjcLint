"""Validate and atomically apply provider-generated structured edits."""

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from auto_fix.models import FixViolation


REPAIR_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file_path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "replacement": {"type": "string"},
                    "violation_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "file_path",
                    "start_line",
                    "end_line",
                    "replacement",
                    "violation_ids",
                ],
            },
        },
        "unfixed": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "violation_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["violation_id", "reason"],
            },
        },
    },
    "required": ["edits", "unfixed"],
}


class EditPlanError(ValueError):
    """A structured plan failed the local safety policy."""


@dataclass(frozen=True)
class ApplyResult:
    applied_edits: int
    affected_files: int
    unfixed: int


@dataclass(frozen=True)
class _Edit:
    file_path: str
    start_line: int
    end_line: int
    replacement: str
    violation_ids: Tuple[str, ...]


@dataclass(frozen=True)
class _Snapshot:
    content: str
    mode: int


class RepairSession:
    """Own source snapshots and apply one validated repair plan."""

    def __init__(self, targets: Sequence[FixViolation]):
        if not targets:
            raise ValueError("targets must not be empty")
        self._targets = {target.violation_id: target for target in targets}
        if len(self._targets) != len(targets):
            raise ValueError("violation_id values must be unique")

        self._snapshots: Dict[str, _Snapshot] = {}
        self._applied_contents: Dict[str, str] = {}
        for file_path in sorted({target.file_path for target in targets}):
            path = Path(file_path)
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise ValueError(f"cannot snapshot source file {file_path}: {error}") from error
            mode = stat.S_IMODE(path.stat().st_mode)
            self._snapshots[file_path] = _Snapshot(content=content, mode=mode)

    def apply(self, plan: Dict[str, Any]) -> ApplyResult:
        edits, unfixed_ids = self._validate_plan(plan)
        if not edits:
            return ApplyResult(0, 0, len(unfixed_ids))

        prepared = self._prepare_files(edits)
        self._apply_atomically(prepared)
        self._applied_contents = dict(prepared)
        return ApplyResult(
            applied_edits=len(edits),
            affected_files=len(prepared),
            unfixed=len(unfixed_ids),
        )

    def rollback(self) -> None:
        """Restore every target file to the snapshot captured before repair."""
        prepared: Dict[str, str] = {}
        for file_path, applied_content in self._applied_contents.items():
            try:
                current = Path(file_path).read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise EditPlanError(f"cannot read source during rollback: {file_path}: {error}") from error
            if current != applied_content:
                raise EditPlanError(
                    f"source changed after automatic repair; refusing rollback: {file_path}"
                )
            prepared[file_path] = self._snapshots[file_path].content
        if prepared:
            self._apply_atomically(prepared)
            self._applied_contents = {}

    def _validate_plan(self, plan: Dict[str, Any]) -> Tuple[List[_Edit], Set[str]]:
        if not isinstance(plan, dict):
            raise EditPlanError("repair plan must be an object")
        if set(plan) != {"edits", "unfixed"}:
            raise EditPlanError("repair plan must contain only edits and unfixed")
        raw_edits = plan.get("edits")
        raw_unfixed = plan.get("unfixed")
        if not isinstance(raw_edits, list) or not isinstance(raw_unfixed, list):
            raise EditPlanError("edits and unfixed must be arrays")

        edits: List[_Edit] = []
        accounted: Set[str] = set()
        edited_ids: Set[str] = set()
        allowed_files = set(self._snapshots)

        for index, raw in enumerate(raw_edits):
            if not isinstance(raw, dict):
                raise EditPlanError(f"edit[{index}] must be an object")
            required = {"file_path", "start_line", "end_line", "replacement", "violation_ids"}
            if set(raw) != required:
                raise EditPlanError(f"edit[{index}] has invalid fields")

            file_value = raw.get("file_path")
            if not isinstance(file_value, str) or not file_value:
                raise EditPlanError(f"edit[{index}] file_path is required")
            file_path = str(Path(file_value).expanduser().resolve())
            if file_path not in allowed_files:
                raise EditPlanError(f"edit[{index}] targets {file_path}, which is not an allowed file")

            ids = raw.get("violation_ids")
            if not isinstance(ids, list) or not ids or not all(isinstance(item, str) for item in ids):
                raise EditPlanError(f"edit[{index}] violation_ids must be a non-empty string array")
            unknown_ids = [item for item in ids if item not in self._targets]
            if unknown_ids:
                raise EditPlanError(f"edit[{index}] has unknown violation_id: {unknown_ids[0]}")
            if any(self._targets[item].file_path != file_path for item in ids):
                raise EditPlanError(f"edit[{index}] violation_id belongs to another file")

            try:
                start = int(raw.get("start_line"))
                end = int(raw.get("end_line"))
            except (TypeError, ValueError) as error:
                raise EditPlanError(f"edit[{index}] line range must contain integers") from error
            if start < 1 or end < start:
                raise EditPlanError(f"edit[{index}] has an invalid line range")

            covered_lines: Set[int] = set()
            for violation_id in ids:
                target = self._targets[violation_id]
                for allowed_start, allowed_end in target.allowed_ranges or (target.related_lines,):
                    covered_lines.update(range(allowed_start, allowed_end + 1))
            if any(line not in covered_lines for line in range(start, end + 1)):
                raise EditPlanError(f"edit[{index}] is outside allowed range")

            replacement = raw.get("replacement")
            if not isinstance(replacement, str):
                raise EditPlanError(f"edit[{index}] replacement must be text")

            edits.append(_Edit(file_path, start, end, replacement, tuple(ids)))
            accounted.update(ids)
            edited_ids.update(ids)

        unfixed_ids: Set[str] = set()
        for index, raw in enumerate(raw_unfixed):
            if not isinstance(raw, dict) or set(raw) != {"violation_id", "reason"}:
                raise EditPlanError(f"unfixed[{index}] has invalid fields")
            violation_id = raw.get("violation_id")
            reason = raw.get("reason")
            if violation_id not in self._targets:
                raise EditPlanError(f"unfixed[{index}] has unknown violation_id")
            if violation_id in edited_ids or violation_id in unfixed_ids:
                raise EditPlanError(f"violation_id is accounted for more than once: {violation_id}")
            if not isinstance(reason, str) or not reason.strip():
                raise EditPlanError(f"unfixed[{index}] reason is required")
            unfixed_ids.add(violation_id)
            accounted.add(violation_id)

        missing = set(self._targets) - accounted
        if missing:
            raise EditPlanError(
                "repair plan does not account for every violation: " + ", ".join(sorted(missing))
            )

        self._reject_overlaps(edits)
        return edits, unfixed_ids

    @staticmethod
    def _reject_overlaps(edits: Iterable[_Edit]) -> None:
        by_file: Dict[str, List[_Edit]] = {}
        for item in edits:
            by_file.setdefault(item.file_path, []).append(item)
        for file_path, file_edits in by_file.items():
            ordered = sorted(file_edits, key=lambda item: (item.start_line, item.end_line))
            for previous, current in zip(ordered, ordered[1:]):
                if current.start_line <= previous.end_line:
                    raise EditPlanError(f"edit ranges overlap in {file_path}")

    def _prepare_files(self, edits: Sequence[_Edit]) -> Dict[str, str]:
        by_file: Dict[str, List[_Edit]] = {}
        for item in edits:
            by_file.setdefault(item.file_path, []).append(item)

        prepared: Dict[str, str] = {}
        for file_path, file_edits in by_file.items():
            path = Path(file_path)
            current = path.read_text(encoding="utf-8")
            snapshot = self._snapshots[file_path]
            if current != snapshot.content:
                raise EditPlanError(f"source changed after lint: {file_path}")

            updated = self._apply_to_text(current, file_edits)
            if not updated:
                raise EditPlanError(f"repair would empty source file: {file_path}")
            if updated == current:
                raise EditPlanError(f"repair plan makes no changes: {file_path}")
            prepared[file_path] = updated
        return prepared

    @staticmethod
    def _apply_to_text(content: str, edits: Sequence[_Edit]) -> str:
        newline = "\r\n" if "\r\n" in content else "\n"
        has_final_newline = content.endswith(("\n", "\r"))
        lines = content.splitlines()
        for item in sorted(edits, key=lambda edit: edit.start_line, reverse=True):
            replacement_lines = item.replacement.replace("\r\n", "\n").split("\n")
            if replacement_lines and replacement_lines[-1] == "":
                replacement_lines.pop()
            lines[item.start_line - 1:item.end_line] = replacement_lines
        result = newline.join(lines)
        if has_final_newline:
            result += newline
        return result

    def _apply_atomically(self, prepared: Dict[str, str]) -> None:
        staged: Dict[str, str] = {}
        replaced: List[str] = []
        try:
            for file_path in sorted(prepared):
                staged[file_path] = self._stage(file_path, prepared[file_path])
            for file_path in sorted(prepared):
                os.replace(staged[file_path], file_path)
                staged.pop(file_path, None)
                replaced.append(file_path)
        except Exception as error:
            rollback_errors = []
            for file_path in reversed(replaced):
                try:
                    restore_path = self._stage(file_path, self._snapshots[file_path].content)
                    os.replace(restore_path, file_path)
                except Exception as rollback_error:
                    rollback_errors.append(f"{file_path}: {rollback_error}")
            detail = "; rollback failed: " + "; ".join(rollback_errors) if rollback_errors else "; changes rolled back"
            raise EditPlanError(f"atomic apply failed: {error}{detail}") from error
        finally:
            for temp_path in staged.values():
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _stage(self, file_path: str, content: str) -> str:
        destination = Path(file_path)
        fd, temp_path = tempfile.mkstemp(
            prefix=".biliobjclint-auto-fix-",
            dir=str(destination.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            os.chmod(temp_path, self._snapshots[file_path].mode)
            return temp_path
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
