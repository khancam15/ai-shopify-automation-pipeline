from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from security_policy import contains_destructive_terms, validate_bash_command


def test_validate_bash_command_allows_safe_pwd() -> None:
    allowed, reason, tokens = validate_bash_command("pwd", Path.cwd())
    assert allowed
    assert reason == "allowed"
    assert tokens == ["pwd"]


def test_validate_bash_command_blocks_non_allowlisted_command() -> None:
    allowed, reason, _ = validate_bash_command("open https://etsy.com", Path.cwd())
    assert not allowed
    assert "not in allowlist" in reason


def test_validate_bash_command_blocks_env_file_access() -> None:
    allowed, reason, _ = validate_bash_command("cat .env", Path.cwd())
    assert not allowed
    assert "disallowed path" in reason


def test_validate_bash_command_blocks_metacharacters() -> None:
    allowed, reason, _ = validate_bash_command("ls && cat outputs/week_log.md", Path.cwd())
    assert not allowed
    assert "metacharacters" in reason


def test_contains_destructive_terms_detects_high_risk_text() -> None:
    payload = "Click publish and proceed to checkout payment"
    assert contains_destructive_terms(payload)
