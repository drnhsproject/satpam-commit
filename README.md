# satpam-commit

An Agent Skill that commits your work carefully: it reads the real diff, guards the
repository against the usual accidents, and leaves clean, reviewable commits.

*Satpam* is Indonesian for a security guard: it stands at the door of your commit and checks what goes in.

```
/satpam-commit                    review → guard → stage → gate → commit
/satpam-commit --dry-run          propose everything, change nothing
/satpam-commit --quick            skip format, lint, typecheck, tests (guards still run)
/satpam-commit --split | --single preselect the split proposal, or force one commit
/satpam-commit --amend            fold staged work into the last local commit
/satpam-commit --push             after committing: pull with rebase, re-scan, push upstream
```

## What it does

- **Reviews by area**, not by extension: file counts and `+/-` per area, and an explicit list
  of deleted, renamed, untracked and unmerged files, which a stat line hides.
- **Guards, and no flag skips them**: unresolved merge conflicts and leftover markers
  (lockfiles included), secrets in file names and in added lines, build output and junk,
  commits on protected branches or a detached HEAD, a rebase or cherry-pick in progress.
  Warns about removed or skipped tests, leftover debug output, a lockfile that moved without
  its manifest, and unrelated files.
- **Proposes a split** when the work holds more than one concern (a fix plus a refactor plus
  docs), ordered so every commit stands on its own. You choose: as proposed, one commit,
  or your own grouping.
- **Runs the project's own gate**: formatter, lint, typecheck, related tests. It detects the
  tools instead of assuming them, and logs `not run` when none exist.
- **Writes a Conventional Commit from the actual diff**, shows it, and waits for your OK.

## What it never does

Stage with `git add -A` or `.`, skip hooks, force-push, rewrite published history, push without
`--push`, or run a destructive command without your approval of that exact command. Secrets are
reported by file and line only, never printed.

The skill is instructions to the agent, not a sandbox. Keep your normal permission prompts on.

## Install

With the community `skills` CLI ([vercel-labs/skills](https://github.com/vercel-labs/skills)):

```bash
npx skills add drnhsproject/satpam-commit --list
npx skills add drnhsproject/satpam-commit --skill satpam-commit
npx skills add drnhsproject/satpam-commit --skill satpam-commit -g       # all your projects
```

The CLI collects anonymous usage data; set `DISABLE_TELEMETRY=1` to opt out. It is a
third-party tool, and skills run with your agent's permissions: read `SKILL.md` before
installing any skill, this one included.

Without the CLI, copy the folder:

```bash
cp -R skills/satpam-commit ~/.claude/skills/             # all projects
cp -R skills/satpam-commit <project>/.claude/skills/     # one project
```

A project skill with the same name overrides the personal one. Updates are manual; changes are
listed in `CHANGELOG.md`.

## Status

Published as `v0.1.1`; install verified via `npx skills add drnhsproject/satpam-commit`
(byte-identical to the repo). Trials: throwaway repositories with planted traps, plus two real
repository trials (an agent simulating the SKILL.md flow, and an adaCODE tool-calling run in
`mvp-react`): 4/4 planted traps caught, including the gitignored `.env` secret that earlier
trials missed. Trigger-tested on 16 queries (2-run `claude -p` evals: 13/16; description-only
proxy on the adaCODE backend: 16/16 stable, 6 runs each; see `evals/` and `CHANGELOG.md`).
Tell the author what it got wrong.

## License

MIT
