# Contributing

This repository follows a simple workflow so the history stays clean and easy to scan.

## Workflow

1. Create a branch from `main` named `type/short-description`, for example `docs/update-readme` or `fix/contrast-audit`.
2. Commit your changes on that branch.
3. Open a pull request into `main` with a Conventional Commits title.
4. Squash merge the pull request. The commit on `main` takes the pull request title plus its number, for example `docs: update README (#12)`.

## Commit and pull request titles

Use the [Conventional Commits](https://www.conventionalcommits.org) format: `type: short summary in the imperative mood`.

| Type | Use it for |
|---|---|
| `feat` | A new feature or capability |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `style` | Formatting or visual polish with no change in behavior |
| `refactor` | Code restructuring with no change in behavior |
| `test` | Adding or updating tests |
| `ci` | GitHub Actions and other automation |
| `chore` | Maintenance, dependencies, and configuration |
| `security` | Security hardening or fixes |

Guidelines:

- Keep the summary under 72 characters, in lowercase after the colon, with no trailing period.
- Describe what changed, not how you felt about it: `fix: correct DNS record example`, not `fixed stuff`.
- Never include passwords, tokens, personal email addresses, or other private details in titles or messages.

## Commit identity

Commit with GitHub's private noreply address so a personal email address never appears in the history:

```bash
git config user.email "60675702+khancam15@users.noreply.github.com"
```
