"""Security policy helpers for autonomous execution."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

DISALLOWED_META_CHARS = re.compile(r"[;&|><`$]")
DISALLOWED_PATH_SNIPPETS = ("..", "~", "*", "?", "[")
BLOCKED_FILENAMES = (".env",)
READ_ONLY_COMMANDS = {"pwd", "date", "ls", "cat", "grep", "head", "tail", "wc"}
LS_ALLOWED_OPTIONS = {"-a", "-l", "-la", "-al"}


def _is_blocked_path(path_value: str) -> bool:
    lowered = path_value.lower().strip()
    if not lowered:
        return False
    return any(lowered == name or lowered.startswith(f"{name}.") for name in BLOCKED_FILENAMES)


def _is_safe_read_path(raw_path: str, workspace_root: Path) -> bool:
    if not raw_path or raw_path.startswith("-"):
        return True
    if any(snippet in raw_path for snippet in DISALLOWED_PATH_SNIPPETS):
        return False
    if _is_blocked_path(Path(raw_path).name):
        return False

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate

    try:
        resolved = candidate.resolve()
        root_resolved = workspace_root.resolve()
    except Exception:
        return False

    return resolved == root_resolved or root_resolved in resolved.parents


def _extract_command_paths(command: str, tokens: list[str]) -> list[str]:
    if command in {"pwd", "date"}:
        return []

    if command == "ls":
        return [token for token in tokens[1:] if not token.startswith("-")]

    if command in {"cat", "head", "tail", "wc"}:
        return [token for token in tokens[1:] if not token.startswith("-") and not token.isdigit()]

    if command == "grep":
        # grep [options] PATTERN [FILE...]
        non_option_tokens = [token for token in tokens[1:] if not token.startswith("-")]
        if len(non_option_tokens) <= 1:
            return []
        return non_option_tokens[1:]

    return []


def validate_bash_command(command_text: str, workspace_root: Path) -> tuple[bool, str, list[str]]:
    """
    Validate a bash command against a strict read-only allowlist.
    Returns: (is_allowed, reason, parsed_tokens)
    """
    command_text = command_text.strip()
    if not command_text:
        return False, "empty command", []

    if DISALLOWED_META_CHARS.search(command_text):
        return False, "shell metacharacters are not allowed", []

    try:
        tokens = shlex.split(command_text)
    except ValueError:
        return False, "command could not be parsed", []

    if not tokens:
        return False, "empty command", []

    command = tokens[0]
    if command not in READ_ONLY_COMMANDS:
        return False, f"command '{command}' is not in allowlist", tokens

    if command in {"pwd", "date"} and len(tokens) > 1:
        return False, f"command '{command}' does not accept arguments", tokens

    if command == "ls":
        for token in tokens[1:]:
            if token.startswith("-") and token not in LS_ALLOWED_OPTIONS:
                return False, f"unsupported ls option: {token}", tokens

    for raw_path in _extract_command_paths(command, tokens):
        if not _is_safe_read_path(raw_path, workspace_root):
            return False, f"disallowed path: {raw_path}", tokens

    return True, "allowed", tokens


def contains_destructive_terms(payload: str) -> bool:
    destructive_terms = (
        "publish",
        "purchase",
        "checkout",
        "payment",
        "pay now",
        "place order",
        "submit order",
        "buy now",
        "billing",
        "credit card",
        "cvv",
        "password",
        "security",
        "delete",
        "close account",
        "account settings",
        "bank",
        "payout",
    )
    lowered = payload.lower()
    return any(term in lowered for term in destructive_terms)
