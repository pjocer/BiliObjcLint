"""Read-only Codex-first provider execution for automatic repair."""

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from auto_fix.edit_plan import REPAIR_PLAN_SCHEMA


class AutoFixUnavailableError(RuntimeError):
    """No configured provider could produce a structured repair plan."""


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    plan: Dict[str, Any]
    diagnostics: str = ""


_COMMON_PATHS = {
    "codex": [
        "/Applications/ChatGPT.app/Contents/Resources/codex",
        "~/.local/bin/codex",
        "/usr/local/bin/codex",
        "/opt/homebrew/bin/codex",
        "~/bin/codex",
    ],
    "claude": [
        "~/.local/bin/claude",
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
        "~/bin/claude",
    ],
}


def find_provider_executable(name: str) -> Optional[str]:
    """Find a supported CLI without executing it."""
    for candidate in _COMMON_PATHS.get(name, []):
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which(name)


class AutoFixProviderRunner:
    """Ask Codex, then Claude, for a schema-constrained read-only plan."""

    def __init__(
        self,
        project_root: Path,
        timeout: int = 120,
        executable_locator: Callable[[str], Optional[str]] = find_provider_executable,
        process_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.project_root = Path(project_root).resolve()
        self.timeout = timeout
        self._locate = executable_locator
        self._run_process = process_runner

    def preferred_provider(self) -> Optional[str]:
        """Return the provider that would be attempted first, without executing it."""
        if self._locate("codex"):
            return "codex"
        if self._locate("claude"):
            return "claude"
        return None

    def run(self, prompt: str) -> ProviderResult:
        diagnostics = []

        codex_path = self._locate("codex")
        if codex_path:
            try:
                plan = self._run_codex(codex_path, prompt)
                return ProviderResult("codex", plan, "; ".join(diagnostics))
            except Exception as error:
                diagnostics.append(f"codex: {self._describe_error(error)}")
        else:
            diagnostics.append("codex: Codex CLI not found")

        claude_path = self._locate("claude")
        if claude_path:
            try:
                plan = self._run_claude(claude_path, prompt)
                return ProviderResult("claude", plan, "; ".join(diagnostics))
            except Exception as error:
                diagnostics.append(f"Claude: {self._describe_error(error)}")
        else:
            diagnostics.append("Claude: Claude Code CLI not found")

        raise AutoFixUnavailableError(
            "Codex CLI and Claude Code CLI are unavailable: " + "; ".join(diagnostics)
        )

    def _run_codex(self, executable: str, prompt: str) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="biliobjclint-auto-fix-") as temp_dir:
            schema_path = Path(temp_dir) / "repair-plan.schema.json"
            output_path = Path(temp_dir) / "repair-plan.json"
            schema_path.write_text(
                json.dumps(REPAIR_PLAN_SCHEMA, ensure_ascii=False), encoding="utf-8"
            )
            command = [
                executable,
                "exec",
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--color",
                "never",
                "-C",
                str(self.project_root),
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "-",
            ]
            result = self._run_process(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.project_root),
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "unknown error").strip()
                raise RuntimeError(f"exit {result.returncode}: {detail}")
            if not output_path.is_file():
                raise RuntimeError("Codex did not produce an output file")
            return self._parse_plan(output_path.read_text(encoding="utf-8"))

    def _run_claude(self, executable: str, prompt: str) -> Dict[str, Any]:
        command = [
            executable,
            "--print",
            "--permission-mode",
            "plan",
            "--tools",
            "Read",
            "--no-session-persistence",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(REPAIR_PLAN_SCHEMA, ensure_ascii=False, separators=(",", ":")),
        ]
        result = self._run_process(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=str(self.project_root),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"exit {result.returncode}: {detail}")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid Claude JSON: {error}") from error

        if self._is_plan(payload):
            return payload
        structured = payload.get("structured_output") if isinstance(payload, dict) else None
        if self._is_plan(structured):
            return structured
        result_value = payload.get("result") if isinstance(payload, dict) else None
        if self._is_plan(result_value):
            return result_value
        if isinstance(result_value, str):
            return self._parse_plan(result_value)
        raise ValueError("Claude response did not contain structured_output")

    @classmethod
    def _parse_plan(cls, text: str) -> Dict[str, Any]:
        try:
            plan = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid repair plan JSON: {error}") from error
        if not cls._is_plan(plan):
            raise ValueError("repair plan must contain edits and unfixed arrays")
        return plan

    @staticmethod
    def _is_plan(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and set(value) == {"edits", "unfixed"}
            and isinstance(value.get("edits"), list)
            and isinstance(value.get("unfixed"), list)
        )

    @staticmethod
    def _describe_error(error: Exception) -> str:
        if isinstance(error, subprocess.TimeoutExpired):
            return "timed out"
        return str(error) or error.__class__.__name__
