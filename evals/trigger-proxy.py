#!/usr/bin/env python3
"""Trigger proxy WITHOUT a live agent runtime.

The real eval (run-triggers.py) measures whether a Claude Code session calls
the Skill tool from the description alone. This proxy asks a model (via the
`claude -p` headless CLI, or any backend you point --backend at) the same
question, per query: "from this description alone, would the agent pick this
skill for this query?" No tools are granted, so it cannot act on the query.

Use it when the agent CLI quota is unavailable, or as a cheap pre-screen:
results are a signal, NOT a substitute for run-triggers.py, because a proxy
answer ("the model thinks the skill would fire") is not the same evidence as
an observed Skill tool call in a real session.

Usage:
  python3 evals/trigger-proxy.py evals/triggers-satpam-commit.json [--runs N] [--jobs N]
  python3 evals/trigger-proxy.py ... --backend manual   # print prompts, collect answers by hand

Needs the `claude` CLI logged in (one short, tool-free call per run).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROMPT = """You are an agent in a coding environment. Exactly one skill is installed: `satpam-commit`.
Its description (what the environment shows the agent) is:

---
{desc}
---

The user just said exactly this:

---
{query}
---

Based on the description alone (no diff, no files, no other context), would the
agent pick this skill to handle the user's request? Answer with a single line
in the form `PICK: yes` or `PICK: no`, then one short reason (max 15 words).
Do not use any tools; just answer.
"""


def load_description(repo: Path, skill: str | None) -> str:
    hits = sorted(repo.glob("skills/*/SKILL.md"))
    if skill:
        hits = [h for h in hits if h.parent.name == skill]
    if len(hits) != 1:
        sys.exit(f"expected exactly one matching skills/*/SKILL.md under {repo}, found {len(hits)}")
    for line in hits[0].read_text().splitlines():
        m = re.match(r"^description:\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    sys.exit(f"no description line in {hits[0]}")


def run_once(desc: str, query: str, backend: str, model: str | None) -> tuple[bool, str]:
    prompt = PROMPT.format(desc=desc, query=query)
    if backend == "manual":
        print(prompt)
        return False, "manual"
    if shutil.which("claude") is None:
        return False, "no-claude-cli"
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit",
           "WebFetch", "WebSearch", "Agent", "Skill", "Task"]
    if model:
        cmd += ["--model", model]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return False, "timeout"
        answer = ""
        for line in (proc.stdout or "").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") != "assistant":
                continue
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    answer += block.get("text", "")
        if "hit your 5-hour limit" in answer or "api_error" in proc.stdout:
            return False, "quota-limited"
        m = re.search(r"PICK:\s*(yes|no)", answer, re.IGNORECASE)
        if not m:
            return False, f"no-answer: {answer[:60]!r}".replace("'","")[:70]
        return m.group(1).lower() == "yes", m.group(1).lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("triggers")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model")
    ap.add_argument("--skill")
    ap.add_argument("--backend", default="claude", choices=["claude", "manual"])
    args = ap.parse_args()

    triggers_path = Path(args.triggers).resolve()
    repo = triggers_path.parent.parent
    desc = load_description(repo, args.skill)
    cases = json.loads(triggers_path.read_text())

    jobs = [(i, c) for i, c in enumerate(cases) for _ in range(args.runs)]
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(lambda j: (j[0], run_once(desc, j[1]["query"],
                                                         args.backend, args.model)), jobs))
    per_case: dict[int, list[tuple[bool, str]]] = {}
    for i, r in results:
        per_case.setdefault(i, []).append(r)

    passed = 0
    errors = 0
    print(f"trigger-proxy   runs per query: {args.runs}   backend: {args.backend}\n")
    for i, case in enumerate(cases):
        rs = per_case[i]
        hits = sum(1 for t, _ in rs if t)
        errs = sum(1 for t, d in rs if d not in ("yes", "no"))
        errors += errs
        rate = hits / max(1, len(rs) - errs) if len(rs) - errs > 0 else 0.0
        ok = rate >= 0.5 if case["trigger"] else rate < 0.5
        passed += ok
        detail = ",".join(sorted({d for _, d in rs if d not in ("yes", "no")}))
        print(f"{'PASS' if ok else 'FAIL'}  expect={'yes' if case['trigger'] else 'no':3}  "
              f"picked {hits}/{len(rs)}  {case['query'][:64]}"
              + (f"   [errors: {detail}]" if detail else ""))
    print(f"\n{passed}/{len(cases)} queries pass"
          + (f"   ({errors} error run(s) — treat affected rates as inconclusive)" if errors else ""))
    sys.exit(0 if passed == len(cases) and errors == 0 else 1)


if __name__ == "__main__":
    main()
