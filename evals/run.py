"""Run the evaluation set against the real agent (real Claude calls).

    python -m evals.run              # all cases
    python -m evals.run --case dallas_why

Ground truth comes from the deterministic code at run time (scoring + tools), never from hard-coded
numbers, so the eval checks that the agent reports what the code computes. Runs on a temporary copy
of the database so eval conversations don't mix with real ones. Exit code 1 if any case fails.
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import anthropic

from app import agent, conversations, risk, scoring
from app.config import get_settings
from app.db import connect
from app.hubs import find_hub
from app.tools import run_tool

CASES_FILE = Path(__file__).parent / "cases.json"
RESULTS_DIR = Path(__file__).parent / "results"
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _top(conn, hazard: str, region: str | None) -> list[str]:
    """Hub ids ranked by hazard (or composite) within a region, from the scoring code."""
    ranked = scoring.rank(risk.score_all(conn), None if hazard == "composite" else hazard)
    return [s.hub_id for s in ranked if region is None or find_hub(s.hub_id).region == region]


def _hub_score(conn, hub: str, hazard: str) -> float:
    score = next(s for s in risk.score_all(conn) if s.hub_id == hub)
    return score.composite if hazard == "composite" else score.hazards[hazard].score


def _expected_number(conn, spec: dict) -> float:
    if "tool" in spec:
        return run_tool(conn, spec["tool"], spec["args"])[spec["field"]]
    if "hub_score" in spec:
        return _hub_score(conn, spec["hub_score"]["hub"], spec["hub_score"]["hazard"])
    top_spec = spec["hub_score_of_top"]
    top_hub = _top(conn, top_spec["hazard"], top_spec["region"])[0]
    return _hub_score(conn, top_hub, top_spec["score_hazard"])


def check(conn, checks: dict, result: agent.TurnResult, tools_used: list[str]) -> list[str]:
    """Return a list of failure messages (empty = pass)."""
    a = result.answer
    text = a.answer.lower()
    fails = []
    if "status_in" in checks and a.status not in checks["status_in"]:
        fails.append(f"status {a.status!r} not in {checks['status_in']}")
    if "tools_any" in checks and not set(checks["tools_any"]) & set(tools_used):
        fails.append(f"none of {checks['tools_any']} called (called {tools_used})")
    for hub in checks.get("hubs_include", []):
        if hub not in a.hub_ids:
            fails.append(f"hub {hub!r} missing from hub_ids {a.hub_ids}")
    for hz in checks.get("hazards_include", []):
        if hz not in a.hazards:
            fails.append(f"hazard {hz!r} missing from hazards {a.hazards}")
    if region := checks.get("hubs_all_in_region"):
        outside = [h for h in a.hub_ids if find_hub(h).region != region]
        if outside:
            fails.append(f"hubs outside {region}: {outside}")
    if spec := checks.get("first_hub_is_top_of"):
        expected = _top(conn, spec["hazard"], spec["region"])[0]
        if not a.hub_ids or a.hub_ids[0] != expected:
            fails.append(f"first hub should be {expected!r}, got {a.hub_ids[:1]}")
    if spec := checks.get("first_hubs_are_top_n_of"):
        expected = _top(conn, spec["hazard"], spec["region"])[: spec["n"]]
        if a.hub_ids[: spec["n"]] != expected:
            fails.append(f"first {spec['n']} hubs should be {expected}, got {a.hub_ids[: spec['n']]}")
    for group in checks.get("mentions_all_groups", []):
        if not any(word in text for word in group):
            fails.append(f"answer mentions none of {group}")
    numbers = [float(n) for n in NUMBER_RE.findall(a.answer)]
    for spec in checks.get("numbers_in_answer", []):
        expected = _expected_number(conn, spec)
        if not any(abs(n - expected) <= spec["tolerance"] for n in numbers):
            fails.append(f"expected number {expected} (±{spec['tolerance']}) not in answer")
    return fails


def run_case(conn, case: dict) -> dict:
    cid = conversations.create(conn)
    started = time.perf_counter()
    try:
        for message in case["turns"]:
            result = agent.run_turn(conn, cid, message)
        fails = check(conn, case["checks"], result, result.tools_used)
        record = {"answer": result.answer.model_dump(), "tools_used": result.tools_used}
    except (agent.AgentError, anthropic.APIError) as exc:
        fails, record = [f"{type(exc).__name__}: {exc}"], {}
    return {"id": case["id"], "passed": not fails, "failures": fails,
            "seconds": round(time.perf_counter() - started, 1), **record}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--case", help="run only this case id")
    args = parser.parse_args()

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"no case {args.case!r}")
            return 2

    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / "eval.db"
        shutil.copy(get_settings().db_path, db_copy)
        conn = connect(db_copy)
        results = []
        try:
            for case in cases:
                r = run_case(conn, case)
                results.append(r)
                print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']:<24} {r['seconds']:>5}s  "
                      + "; ".join(r["failures"]))
        finally:
            conn.close()  # Windows can't delete the temp dir while the file is open

    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} cases passed")
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"model": get_settings().anthropic_model, "results": results}, indent=2), encoding="utf-8")
    print(f"details: {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
