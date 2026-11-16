# satpam-commit

An Agent Skill that commits your work carefully: it reads the real diff, guards the
repository against the usual accidents, and leaves clean, reviewable commits.

It is a plain `SKILL.md` folder, so it works with any coding agent that supports Agent Skills.

*Satpam* is Indonesian for a security guard: it stands at the door of your commit and checks what goes in.

In Claude Code, run it as a slash command. In an agent without slash commands, ask by name
("use satpam-commit with --dry-run"); the flags mean the same.

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

## Requirements

- Git 2.23 or newer, and a POSIX shell (Git Bash or WSL on Windows).
- An agent that loads Agent Skills (a folder with `SKILL.md`) and can run shell commands.
- The agent needs permission to run `git` and read the working tree. Where it has a question
  tool the skill uses it; otherwise it asks in plain text and waits.

## Install

With the community `skills` CLI ([vercel-labs/skills](https://github.com/vercel-labs/skills)),
which places the skill for the agents it detects on your machine:

```bash
npx skills add drnhsproject/satpam-commit --list
npx skills add drnhsproject/satpam-commit --skill satpam-commit
npx skills add drnhsproject/satpam-commit --skill satpam-commit -g       # all your projects
```

The CLI collects anonymous usage data; set `DISABLE_TELEMETRY=1` to opt out. It is a
third-party tool, and skills run with your agent's permissions: read `SKILL.md` before
installing any skill, this one included.

Without the CLI, copy the `skills/satpam-commit` folder into your agent's skills directory
(see that agent's documentation for the path). For Claude Code:

```bash
cp -R skills/satpam-commit ~/.claude/skills/             # all projects
cp -R skills/satpam-commit <project>/.claude/skills/     # one project
```

A project skill with the same name overrides the personal one. Updates are manual; changes are
listed in `CHANGELOG.md`.

## Status

Latest release: `v0.1.2`. What has and has not been tested:

- **Install:** `npx skills add` succeeds and the installed copy is byte-identical to the repo.
- **Behavior:** throwaway repositories with planted traps (secret, build output, conflict
  markers, protected branch, rebase and push paths), plus a real repository run on a second
  agent runtime with tool calling. All 4 planted traps were caught, including a gitignored
  `.env`, and no destructive command ran.
- **Triggering, Claude Code only:** 16 queries x 6 runs (`evals/`): 15/16 pass. All 8 negative
  queries (push, merge, rebase, deploy, unrelated) stayed silent in all 48 runs; the 7 plain-
  language commit requests triggered 41 of 42 runs. The one failing query is the literal
  `/satpam-commit` sent through `claude -p`, which the headless runner does not treat as a
  slash command; this is probably a runner artifact, not measured beyond that.
- **Other agents:** the behavior run above is the only evidence. Triggering has not been
  measured on them; `evals/triggers-satpam-commit.json` is plain data you can reuse.

Tell the author what it got wrong.

## License

MIT
