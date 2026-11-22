# SKILL: How to make a change in IPO-Analysis

This file is the working procedure for any AI agent or developer changing this repository. Read it before the first edit. `handoff.md` holds the project state; this file holds the process.

## 1. Start from a clean, current main

```powershell
git switch main
git pull origin main
git status            # must be clean before starting
```

If the working tree has changes you did not make, stop and ask the owner. Do not stash or discard them.

## 2. Branch for every change

- One branch per change. Never commit directly to `main`.
- Name it by type: `feat/...`, `fix/...`, `docs/...`, `chore/...`, e.g. `fix/neon-database-url`.
- Start the branch from the latest `main`.

```powershell
git switch -c fix/short-description
```

## 3. Make the change and test it

- Add or update tests with the change. Keep changes small and reviewable.
- Run the relevant tests, then the full suite before opening a PR.

```powershell
.venv\Scripts\python -m pytest -q                       # full Python suite
cd relay; node --test test/relay.test.mjs; cd ..        # Telegram relay
```

Known local-only failures on Windows: `tests/unit/test_official_prospectus_validation.py` (2 tests, "Broken xref table"). They also fail on unchanged `main` locally and pass in CI. Report them; do not hide them.

## 4. Update handoff.md for every change

Every change adds an entry to section 14, **Change log**, in `handoff.md`:

- Date, branch, and PR number
- What changed, in one or two sentences
- Tests run and their result
- What is still not done or not verified

Also update section 1 or 2 of `handoff.md` if the change affects current state, open PRs, schedules, secrets, or known gaps. Keep `README.md` and `OPERATIONS.md` consistent with the behaviour.

## 5. Commit

Use a conventional message with the attribution line required by this project:

```powershell
git add <files>
git commit -F message.txt
```

```
feat(scope): short summary

Why and what changed, in a few lines.

Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>
```

Do not commit secrets, `.env` files, tokens, chat IDs, connection strings, or runtime databases.

## 6. Open a pull request

```powershell
git push -u origin <branch>
gh pr create --base main --head <branch> --title "..." --body-file pr.md
```

The PR body has a Summary, what is not in the PR, and Testing. End it with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## 7. Wait for checks, then merge into main

- Check the status with `gh pr checks <number>` until every required check has finished.
- **Merge rule (owner decision, 2026-11-22):** Cloudflare preview builds for non-production branches are turned off, so PRs have no Cloudflare check. Merge when the `test` (GitHub Actions) check passes and the PR is mergeable.
- **Never merge while a `test` check is failing or still pending.** Read the failing log (`gh run view <id> --log-failed`), fix the root cause, push, and wait again.
- If a failing check is one the owner has turned off or does not run on PRs, say so in the PR and the handoff entry; do not treat it as a blocker.
- Do not bypass checks, use admin override, or skip hooks.
- When every check passes and the PR is mergeable:

```powershell
gh pr merge <number> --squash
git switch main
git pull origin main
```

Then confirm `main` contains the change.

## 8. Things that are never done without explicit owner approval

- Running `workflow_dispatch` or any scheduled job that sends real email, Telegram or WhatsApp messages. A manual run counts as a real send.
- Changing recipients, SMTP settings, Telegram or Neon credentials, or GitHub secrets.
- Clearing the event ledger or database.
- Publishing an APPLY, AVOID, or buy/sell verdict from unverified data. Opinions must be labelled **Indicative** (from extracted filings) or **Verified** (reviewer-approved).
- Stating that an email or Telegram message was delivered because a workflow was green. A green run only means the code ran; SMTP acceptance is not inbox delivery.

Merging a reviewed, passing PR is covered by the standing instruction above. Deploys, sends and data changes are not.

## 9. After the merge

- The change-log entry in `handoff.md` should name the PR number. The merge commit can be added in the next change's entry.
- Delete the merged branch on GitHub if it is no longer needed (`gh pr merge <number> --squash --delete-branch`).

## Quick checklist

- [ ] Branch from latest `main`, named by type
- [ ] Tests added or updated; relevant tests and full suite run
- [ ] `handoff.md` change-log entry added
- [ ] Commit message with the Co-Authored-By line; no secrets
- [ ] PR opened with Summary, not-in-PR and Testing
- [ ] Every check green, PR mergeable
- [ ] Squash-merged; `main` confirmed to contain the change
