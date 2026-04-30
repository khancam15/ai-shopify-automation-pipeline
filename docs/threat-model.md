# Threat Model

## Scope
This document covers the security model for the autonomous Etsy executor in scripts/etsy_autonomous.py.

## Assets
- Etsy seller account access and storefront state.
- Anthropic API credentials from .env.
- Generated execution outputs in outputs/.

## Trust Boundaries
- LLM output is untrusted input.
- Browser page content is untrusted input.
- Local filesystem and shell execution are privileged surfaces.

## Primary Threats
- Prompt injection causing unauthorized browser actions.
- Unauthorized publish/purchase/payment clicks.
- Secret exposure through file reads, logs, or command execution.
- Supply-chain risk from vulnerable dependencies.

## Implemented Controls
- Fail-closed click blocking when trusted domain cannot be verified.
- Manual approval gates for Etsy clicks and destructive actions.
- Strict read-only bash command allowlist with per-command argument validation.
- Restricted editor file access to outputs/.
- Secret scan in CI via gitleaks and dependency audit in CI via pip-audit.
- Version-pinned runtime dependencies.

## Residual Risks
- Human approval prompts can still allow risky actions if misused.
- Browser URL trust depends on AppleScript front-app introspection.
- LLM output quality can degrade automation reliability.

## Operational Guidance
- Keep autonomous runs supervised.
- Rotate API keys if suspicious behavior occurs.
- Review outputs/security_events.jsonl after each run for blocked/approved actions.
