# Changelog

## 0.1.4 — 2026-11-23

- New "Reply style" block in `SKILL.md`: the reply leads with the answer, with no greeting, announcement or recap; complete short sentences; negations, numbers and units are never shortened; warnings and questions to the user keep full wording. Text saved to files still follows the skill's own file rules.

## 0.1.3 — 2026-11-23

- `--quick` is refused together with `--push`, because a push has to go through the Gate. Before,
  `--quick --push` committed and pushed with no checks (the baseline run recorded the remote ref
  moving; per-run counts were not kept). `--push` now runs the whole test suite (implies
  `--full`); a red Gate stops the push, a missing tool or no test command is a warning. Before a
  push the formatter is check-only, and the second full run is skipped when the pull changed
  nothing. Behaviour change: pushes are slower on large suites.
- A project with no test command now gets a separate first line in the final summary saying no
  tests ran (the commit is still allowed).
- New Gate eval, `evals/run-gate.py` + `evals/gate-scenarios.json` + `evals/fixtures/gate-ts/`:
  7 scenarios x 3 runs, judged from git state and executed commands. Baseline 5/7 (S3 1/3,
  S7 0/3); after 7/7 pass 3/3. S7 was redefined (refusal instead of Gate-before-push) and S4/S6
  already passed before, so only S3 and S7 changed. `--setup-only` checks every precondition without an agent
  session; `--verbose` prints failing runs.
- Eval finding: a skill installed globally shadows the copy in the temporary project, so runs
  measured the old rules. `run-gate.py` passes `--setting-sources project`. `run-triggers.py`
  has the same exposure and was not changed here: its 6-run result may have measured an
  installed copy rather than the repo copy.

## 0.1.2 — 2026-11-16

- Works across agents: `SKILL.md` now says what to do where there are no slash commands or no
  question tool, and states its requirements (git 2.23+, POSIX shell). README gains a
  Requirements section and agent-neutral install notes.
- Trigger eval, 16 queries x 6 runs (Claude Code, `claude -p`, only this skill installed):
  15/16 pass. 8/8 negatives silent in 48/48 runs; 7 plain-language commit requests triggered
  41/42 runs. The one failure is the literal `/satpam-commit`, which `claude -p` did not run as a
  slash command (it fell through to Glob 6/6 times): probably a runner artifact. The earlier
  13/16 came from only 2 runs per query and was noise, not a description problem.
- Removed `evals/trigger-proxy.py`. It was a description-only stand-in that ran on one
  maintainer's private model backend; its 16/16 was not a real trigger measurement and could not
  be reproduced by anyone else. `evals/run-triggers.py` and the query file remain.
- Docs: the README Status section states exactly what was tested and what was not (other agents:
  behavior run only, triggering not measured).

## 0.1.1 — 2026-11-16

- Guards now see gitignored files: Step 1 lists them with `git ls-files --others --ignored --exclude-standard`
  and passes the list through Step 2 (conflict markers, secret names, secret content, build-output
  junk) with plain `grep`/`case` loops, because every git command skips ignored paths.
  Verified in a scratch repository against both trials' trap sets: `.env` with a `sk-test-`
  value, `dist/bundle.js`, `.DS_Store` and conflict markers in a gitignored new file are all
  caught.
- Behavior trial on a second agent runtime (tool calling, real repository): all 4 gitignored
  traps caught live (`.env` via `git check-ignore -v` plus a `sk-` content scan, `dist/bundle.js`
  and `.DS_Store` via the junk loop, conflict markers in a new file via the untracked scan);
  split proposal and commit refusal without approval behaved per SKILL.md; no destructive
  command ran; the working tree was restored byte-exact. Minor: the model sampled 5 of the
  `dist/*` files in the junk loop, so thoroughness there depends on model sampling.

## 0.1.0 — 2026-11-16

- First version. Review by area, guards (conflicts, secrets, build output, protected branches,
  operations in progress), split proposal, the project's own gate, Conventional Commit from
  the real diff, opt-in `--push`. Written from scratch.
- Renamed from `rapi-commit` to `satpam-commit` before any release (the old name sounded like a
  tidy-up tool; the skill is a guard in front of the commit). Description unchanged.
- Published at `github.com/drnhsproject/satpam-commit`. The first push exposed a YAML bug: an
  unquoted `description` containing `: ` failed the skills CLI's front-matter parse; fixed by
  quoting it (single-quoted inner examples). `npx skills add` then succeeded and the installed
  copy matched the repo.
- Trial 1, throwaway repository with deliberate traps (on `main`, a `.env`, conflict markers in
  a new file, `node_modules/`, debug output). Found and fixed: the conflict and secret scans used
  `git grep` without `--untracked`, so they missed new files.
- Trial 2, throwaway repository with a local bare remote and a lint/test setup: red lint stopped
  the commit and the one-line fix turned it green; `--amend` worked on an unpushed commit;
  `--push` rebased onto a remote commit, re-scanned and pushed; a conflicting remote change left
  the repository mid-rebase and the skill handed back instead of forcing.
- First trigger evals (2 runs per query): 15/16 before the rename, 13/16 after, same
  description. Superseded by the 6-run result under Unreleased.
