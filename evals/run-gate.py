#!/usr/bin/env python3
"""Measure whether the satpam-commit Gate (format, lint, typecheck, tests) really stops bad work.

Each scenario in gate-scenarios.json is built into a throwaway git repository from the real
TypeScript project in evals/fixtures/gate-ts (npm, typescript, node --test), on a feature
branch, with a local bare remote when the scenario pushes. A fresh Claude Code session
(`claude -p`) then runs with this skill installed, and the result is judged from facts outside
the model's own words: the commits and remote ref in git, the shell commands the session ran
(read from the event stream), and, last, a few regexes on its final text.

Usage:
  python3 evals/run-gate.py evals/gate-scenarios.json [--runs N] [--jobs N] [--model M] [--only S6 ...]
  python3 evals/run-gate.py evals/gate-scenarios.json --setup-only

--setup-only builds every scenario and checks its precondition (which tests and tsc are red or
green at HEAD and in the working tree). It starts no agent session, costs nothing, and needs
only git, node and npm.

Cost and safety: every run is a real, billed agent session. The session may run shell commands
(Bash) inside its own temporary repository; Edit, Write, web tools, subagents and the question
tool are disabled, and --dangerously-skip-permissions is never passed. It is not a sandbox: a
misbehaving session could still reach paths outside the temporary directory. A scenario that
must commit or push states its approval in the query, because a headless run cannot answer.
Measures Claude Code only (it drives the `claude` CLI, which must be logged in).
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "gate-ts"
ALLOWED = ["Bash", "Read", "Grep", "Glob", "Skill"]
DISALLOWED = ["Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "AskUserQuestion"]
TIMEOUT_S = 600
VERBOSE = False
BRANCH = "feat/gate-eval"


def _load_triggers():
    spec = importlib.util.spec_from_file_location("run_triggers", HERE / "run-triggers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sh(cmd, cwd, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{p.stdout}{p.stderr}")
    return p


def git(cwd, *args, check=True):
    return sh(["git", "-c", "user.name=gate-eval", "-c", "user.email=gate-eval@example.invalid",
               *args], cwd, check)


def make_template(root: Path) -> Path:
    """Install the fixture's dependencies once; scenarios symlink this node_modules."""
    tpl = root / "template"
    shutil.copytree(FIXTURE, tpl, ignore=shutil.ignore_patterns("node_modules"))
    sh(["npm", "install", "--no-audit", "--no-fund", "--ignore-scripts"], tpl)
    return tpl


def apply_ops(proj: Path, ops: list) -> None:
    for op in ops:
        path = proj / op["path"]
        kind = op["op"]
        if kind == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(op["content"])
        elif kind == "append":
            path.write_text(path.read_text() + op["content"])
        elif kind == "replace":
            text = path.read_text()
            if op["old"] not in text:
                sys.exit(f"scenario op cannot apply: {op['old']!r} not found in {op['path']}")
            path.write_text(text.replace(op["old"], op["new"], 1))
        else:
            sys.exit(f"unknown op {kind!r}")


def apply_scripts(proj: Path, overrides: dict) -> None:
    if not overrides:
        return
    pkg = json.loads((proj / "package.json").read_text())
    for name, value in overrides.items():
        if value is None:
            pkg["scripts"].pop(name, None)
        else:
            pkg["scripts"][name] = value
    (proj / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")


def check_state(proj: Path, want: dict) -> dict:
    """Run the checks named in `want` and return {name: green|red}."""
    cmds = {"test": ["npm", "test", "--silent"], "tsc": ["npx", "tsc", "--noEmit"]}
    out = {}
    for name in want:
        p = sh(cmds[name], proj, check=False)
        out[name] = "green" if p.returncode == 0 else "red"
    return out


def build(tpl: Path, sc: dict, workdir: Path, skill_dir: Path | None, probe: bool):
    """Build the scenario repository. Returns (proj, remote_git_dir | None, observed)."""
    proj = workdir / "proj"
    shutil.copytree(tpl, proj, ignore=shutil.ignore_patterns("node_modules"))
    # A private copy: a session running npm install must not write into a shared template.
    shutil.copytree(tpl / "node_modules", proj / "node_modules", symlinks=True)
    apply_scripts(proj, sc.get("package_overrides", {}))
    apply_ops(proj, sc.get("base", []))
    git(proj, "init", "-q", "-b", "main")
    # Local-only ignore for the installed skill copy; never touches the fixture's .gitignore.
    (proj / ".git" / "info" / "exclude").write_text(".claude/\n")
    git(proj, "add", "-A")
    git(proj, "commit", "-q", "-m", "chore: initial fixture")
    git(proj, "switch", "-q", "-c", BRANCH)
    remote = None
    if sc.get("remote"):
        remote = workdir / "remote.git"
        sh(["git", "init", "-q", "--bare", str(remote)], workdir)
        git(proj, "remote", "add", "origin", str(remote))
        git(proj, "push", "-q", "-u", "origin", BRANCH)
    observed = {}
    pre = sc.get("precond", {})
    if probe and pre.get("head"):
        observed["head"] = check_state(proj, pre["head"])
    apply_ops(proj, sc.get("change", []))
    if probe and pre.get("worktree"):
        observed["worktree"] = check_state(proj, pre["worktree"])
    if skill_dir is not None:
        shutil.copytree(skill_dir, proj / ".claude" / "skills" / skill_dir.name,
                        ignore=shutil.ignore_patterns("__pycache__"))
    return proj, remote, observed


def head_sha(proj: Path) -> str:
    return git(proj, "rev-parse", "HEAD").stdout.strip()


def remote_sha(remote: Path) -> str:
    p = sh(["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{BRANCH}"], remote, check=False)
    return p.stdout.strip()


def run_claude(proj: Path, query: str, model: str | None):
    """Returns (shell commands run, final text, note)."""
    # --setting-sources project: without it a satpam-commit installed under ~/.claude/skills
    # shadows the copy in the temporary project, and the eval would measure the wrong version.
    cmd = ["claude", "-p", query, "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project", "--allowedTools", *ALLOWED, "--disallowedTools", *DISALLOWED]
    if model:
        cmd += ["--model", model]
    # Own process group, so the watchdog and the final cleanup also reach the Bash children.
    proc = subprocess.Popen(cmd, cwd=proj, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            start_new_session=True)
    commands, final, note = [], "", ""
    timed_out = threading.Event()

    def kill_group():
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass

    def on_timeout():
        timed_out.set()
        kill_group()

    watchdog = threading.Timer(TIMEOUT_S, on_timeout)
    watchdog.start()
    try:
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "result":
                final = str(ev.get("result", ""))
                if ev.get("is_error") or re.search(r"hit your .{0,20}limit|rate.?limit", final, re.I):
                    note, final = final[:120] or "error result", ""  # a limit message is not an answer
                break
            if ev.get("type") != "assistant":
                continue
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "Bash":
                    commands.append(str(block.get("input", {}).get("command", "")))
    finally:
        watchdog.cancel()
        kill_group()
        proc.wait()
    if timed_out.is_set():
        note = "timeout"
    return commands, final, note


def judge(sc, proj, remote, head0, remote0, commands, final):
    """Return a list of failure reasons (empty = pass)."""
    exp = sc["expect"]
    bad = []
    new_commits = int(git(proj, "rev-list", "--count", f"{head0}..HEAD").stdout.strip() or 0)
    if exp.get("head_unchanged") and head_sha(proj) != head0:
        bad.append(f"HEAD moved ({new_commits} new commit(s)), expected none")
    if "new_commits" in exp and new_commits != exp["new_commits"]:
        bad.append(f"{new_commits} new commit(s), expected {exp['new_commits']}")
    if exp.get("remote_unchanged") and remote is not None and remote_sha(remote) != remote0:
        bad.append("remote ref moved, expected unchanged")
    for rx in exp.get("ran_any", []):
        if not any(re.search(rx, c) for c in commands):
            bad.append(f"no shell command matched /{rx}/")
    for rx in exp.get("ran_none", []):
        hit = next((c for c in commands if re.search(rx, c)), None)
        if hit:
            bad.append(f"forbidden command ran /{rx}/: {hit[:60]}")
    if exp.get("text_any") and not any(re.search(rx, final, re.I) for rx in exp["text_any"]):
        bad.append("final text matched none of " + " | ".join(exp["text_any"]))
    for rx in exp.get("text_all", []):
        if not re.search(rx, final, re.I):
            bad.append(f"final text did not match required /{rx}/")
    return bad


def run_scenario(tpl, sc, skill_dir, model):
    with tempfile.TemporaryDirectory(prefix="gate-") as tmp:
        proj, remote, _ = build(tpl, sc, Path(tmp), skill_dir, probe=False)
        head0 = head_sha(proj)
        remote0 = remote_sha(remote) if remote else ""
        commands, final, note = run_claude(proj, sc["query"], model)
        if not final.strip():
            # No result event: rate limit, auth failure, crash or timeout. Not a measurement of the skill.
            return None, note or "session returned no result (rate limit, login or crash)"
        bad = judge(sc, proj, remote, head0, remote0, commands, final)
        if VERBOSE and bad:
            print(f"--- {sc['id']} failed: {bad}\n    commands: {[c[:80] for c in commands]}\n"
                  f"    final: {final[-600:]!r}\n", file=sys.stderr)
        return bad, ""


def setup_only(tpl, cases) -> int:
    failed = 0
    for sc in cases:
        with tempfile.TemporaryDirectory(prefix="gate-") as tmp:
            _, _, observed = build(tpl, sc, Path(tmp), None, probe=True)
        want = {k: v for k, v in sc.get("precond", {}).items() if k in ("head", "worktree")}
        ok = all(observed.get(where) == state for where, state in want.items())
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {sc['id']}  precondition "
              + ("holds " if ok else "broken ") + json.dumps(observed))
    return failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--model")
    ap.add_argument("--only", action="append", help="scenario id or id prefix (repeatable)")
    ap.add_argument("--setup-only", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="print commands and final text of failing runs to stderr")
    args = ap.parse_args()
    global VERBOSE
    VERBOSE = args.verbose

    for tool in ("git", "node", "npm") + (() if args.setup_only else ("claude",)):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on PATH")
    cases = json.loads(Path(args.scenarios).read_text())
    if args.only:
        cases = [c for c in cases if any(c["id"].startswith(o) for o in args.only)]
        if not cases:
            sys.exit("no scenario matches --only")
    skill_dir = _load_triggers().find_skill_dir(HERE.parent)

    with tempfile.TemporaryDirectory(prefix="gate-tpl-") as root:
        tpl = make_template(Path(root))
        if args.setup_only:
            sys.exit(1 if setup_only(tpl, cases) else 0)

        jobs = [(i, c) for i, c in enumerate(cases) for _ in range(args.runs)]
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            results = list(ex.map(lambda j: (j[0], run_scenario(tpl, j[1], skill_dir, args.model)), jobs))

    per_case: dict[int, list[tuple[list[str] | None, str]]] = {}
    for i, res in results:
        per_case.setdefault(i, []).append(res)
    passed = errors_total = 0
    print(f"skill: {skill_dir.name}   runs per scenario: {args.runs}\n")
    for i, sc in enumerate(cases):
        runs = per_case[i]
        measured = [bad for bad, _ in runs if bad is not None]
        errors = [err for bad, err in runs if bad is None]
        errors_total += len(errors)
        ok_runs = sum(1 for b in measured if not b)
        if not measured:
            print(f"ERR   {sc['id']:28} all {len(runs)} runs errored: {errors[0]}")
            continue
        ok = ok_runs / len(measured) >= 0.5
        passed += ok
        extra = f"  ({len(errors)} errored run(s) excluded)" if errors else ""
        print(f"{'PASS' if ok else 'FAIL'}  {sc['id']:28} passed {ok_runs}/{len(measured)}{extra}")
        for r in sorted({r for b in measured for r in b}):
            print(f"        - {r}")
    print(f"\n{passed}/{len(cases)} scenarios pass")
    # An errored run is not a measurement: never report a clean pass over a partial result.
    sys.exit(0 if passed == len(cases) and not errors_total else 1)


if __name__ == "__main__":
    main()
