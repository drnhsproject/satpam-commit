# Changelog

## Unreleased

- Guards now see gitignored files: Step 1 lists them with `git ls-files --others --ignored --exclude-standard`
  and passes the list through Step 2 (conflict markers, secret names, secret content, build-output
  junk) with plain `grep`/`case` loops, because every git command skips ignored paths.
  Verified in a scratch repository against both trials' trap sets: `.env` with a `sk-test-`
  value, `dist/bundle.js`, `.DS_Store` and conflict markers in a gitignored new file are all
  caught now — the `ls-files` listing surfaces the traps, the `grep` loops hit them, and
  `git check-ignore -v` shows which pattern hides each.
- adaCODE behavior trial (2026-11-16, `adacode-3.0-flash` via api.adacode.ai + tool calling, real repository `mvp-react`): all 4 gitignored traps caught live (`.env` secret via `git check-ignore -v` + `sk-` content scan, `dist/bundle.js` and `.DS_Store` via the junk case-loop, conflict markers in a new file via the untracked scan); split proposal and commit refusal without approval both behaved per SKILL.md; 0 blocked destructive commands; user's working tree restored byte-exact. Confirms the Unreleased guard fix closes the gap the earlier manual simulation found. Minor: the model sampled 5 of the `dist/*` files in the junk loop — thoroughness now depends on model sampling, not a mechanical miss.
- Trigger proxy re-run on the adaCODE backend (96 queries: 16 x 6, `adacode-3.0-flash`): 16/16 stable — every positive 6/6, every negative 0/6. `evals/trigger-proxy.py` gained a `--backend adacode` option (key from `~/.adacode/auth.json` or `ADACODE_API_KEY`), so the description-only pre-screen no longer needs the `claude` CLI.
- v0.1.0 published: `github.com/drnhsproject/satpam-commit`, tag `v0.1.0`. Install verified: `npx skills add drnhsproject/satpam-commit` succeeds and the installed copy is byte-identical to the repo (`diff -r`). Publish exposed the YAML bug in the first push: an unquoted `description` containing `: ` failed the skills CLI's front-matter parse — fixed in `a47d342` (quoted value, single-quoted inner examples).
## 0.1.0 — 2026-11-16
- Renamed from `rapi-commit` to `satpam-commit` before any release (the old name sounded like a tidy-up tool; the skill is a guard in front of the commit). Description unchanged.

- First version. Review by area, guards (conflicts, secrets, build output, protected branches,
  operations in progress), split proposal, the project's own gate, Conventional Commit from
  the real diff, opt-in `--push`. Written from scratch; not yet run on a real repository and
  not yet trigger-tested.
- First trial in a throwaway repository with deliberate traps (on `main`, a `.env`, conflict markers in a new file, `node_modules/`, debug output). Found and fixed: the conflict and secret scans used `git grep` without `--untracked`, so they missed new files.
- Trigger eval (`evals/`, 16 queries, 2 runs each, only this skill installed): 15/16 pass. 8/8 negatives (push, merge, rebase, squash, deploy, unrelated) stay silent. The one miss is the literal `/satpam-commit` query, where `claude -p` ran Bash instead; probably how the runner passes a slash command, not measured otherwise. "Write a conventional commit ... and commit them" triggered 1/2.
- Second trial, throwaway repository with a local bare remote and a lint/test setup: red lint stopped the commit and the one-line fix turned it green; `--amend` worked on an unpushed commit and the remote check now has an explicit command; `--push` rebased onto a remote commit, re-scanned and pushed; a conflicting remote change left the repository mid-rebase and the skill hands back instead of forcing. Not yet run on a real project.
- Trigger eval re-run after the rename, same description, same 16 queries, 2 runs: 13/16 (the first run under the old name was 15/16). Negatives still 8/8 silent. Positives are borderline: 4 of the 8 triggered only 1 of 2 times, and 3 failed (`Pecah perubahan ini jadi beberapa commit.`, the literal slash command, and `Can you write a conventional commit ...`). Two runs per query cannot tell the rename from noise; the earlier review of the sibling skill found the same swing. Not yet re-measured with more runs.
