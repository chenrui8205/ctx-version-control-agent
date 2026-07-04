#!/usr/bin/env python
"""Reconcile classifier eval — the gatekeeper (§12.2).

3 trials per pair against the real llm/reconcile, majority vote, action-level gates:
  - missed conflicts = 0            (silent corruption of master is the worst failure)
  - false conflicts on supersede-expected pairs = 0   (review noise kills adoption)
  - false drops = 0                 (data loss)
  - action accuracy >= 18/21 (proportional above N=21)
  - non-unanimous pairs <= 3; none may cross action groups on conflict-expected pairs

Usage:
  uv run python evals/run_reconcile.py                      # fake mode (harness plumbing self-test)
  EVAL_LIVE=1 uv run python evals/run_reconcile.py --live   # real model; prints call count + cost first

Writes a timestamped markdown report (+ .json twin) to evals/reports/ — commit it (§12.6).
"""

import argparse
import collections
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctxvcs.config import settings  # noqa: E402
from ctxvcs.core.canonical import normalize_subject_key  # noqa: E402
from ctxvcs.llm.reconcile import reconcile_pair  # noqa: E402
from ctxvcs.llm.types import ACTION_FOR_RELATION, RELATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "fixtures" / "reconcile_seed.jsonl"
REPORTS = ROOT / "reports"

# gates (§12.2) — absolute at the seed size, proportional beyond it
SEED_N, SEED_ACC = 21, 18
MAX_NON_UNANIMOUS = 3


def view(side: dict) -> dict:
    return {
        "type": side["type"],
        "subject": side["subject"],
        "fields": side.get("fields", {}),
        "body": side.get("body", ""),
        "ts": side.get("ts"),
        "origin": side.get("origin"),
    }


def expected_set(fx: dict) -> list[str]:
    return fx.get("expected_any") or [fx["expected"]]


def majority(relations: list[str]) -> str:
    counts = collections.Counter(relations)
    top, n = counts.most_common(1)[0]
    if n > 1:
        return top
    return relations[0]  # 3-way tie: first trial (deterministic; reported as non-unanimous)


def run(fixtures: list[dict], client, trials: int) -> dict:
    cfg = settings()
    rows = []
    for fx in fixtures:
        inc, ex = view(fx["incoming"]), view(fx["existing"])
        if hasattr(client, "current_pair"):
            client.current_pair = fx["id"]
        outcomes = [
            reconcile_pair(
                client, inc, ex,
                incoming_subject_key=normalize_subject_key(inc["subject"]),
                existing_subject_key=normalize_subject_key(ex["subject"]),
                cfg=cfg,
            )
            for _ in range(trials)
        ]
        relations = [o.result.relation for o in outcomes]
        pred = majority(relations)
        exp = expected_set(fx)
        exp_actions = {ACTION_FOR_RELATION[e] for e in exp}
        pred_action = ACTION_FOR_RELATION[pred]
        rows.append(
            {
                "id": fx["id"],
                "path_expected": fx.get("path"),
                "path_actual": outcomes[0].path,
                "expected": exp,
                "trials": relations,
                "prediction": pred,
                "action_expected": sorted(exp_actions),
                "action_predicted": pred_action,
                "relation_ok": pred in exp,
                "action_ok": pred_action in exp_actions,
                "unanimous": len(set(relations)) == 1,
                "trial_actions": [ACTION_FOR_RELATION[r] for r in relations],
                "confidences": [o.result.confidence for o in outcomes],
                "rationales": [o.result.rationale for o in outcomes],
                "conflicting_fields": outcomes[0].result.conflicting_fields,
                "overridden_from": [o.overridden_from for o in outcomes],
                "downgraded_from": [o.downgraded_from for o in outcomes],
            }
        )
    return score(rows)


def score(rows: list[dict]) -> dict:
    n = len(rows)
    acc_needed = SEED_ACC if n <= SEED_N else math.ceil(n * SEED_ACC / SEED_N)
    missed_conflicts = [r for r in rows if "conflict" in r["action_expected"] and r["action_predicted"] != "conflict"]
    false_conflicts_on_supersede = [
        r for r in rows
        if r["action_expected"] == ["supersede"] and r["action_predicted"] == "conflict"
    ]
    false_drops = [
        r for r in rows if r["action_predicted"] == "drop" and "drop" not in r["action_expected"]
    ]
    action_correct = sum(1 for r in rows if r["action_ok"])
    non_unanimous = [r for r in rows if not r["unanimous"]]
    conflict_cross = [
        r for r in rows
        if r["action_expected"] == ["conflict"] and any(a != "conflict" for a in r["trial_actions"])
    ]
    path_mismatch = [r for r in rows if r["path_expected"] and r["path_expected"] != r["path_actual"]]

    gates = {
        "missed_conflicts == 0": len(missed_conflicts) == 0,
        "false_conflicts_on_supersede == 0": len(false_conflicts_on_supersede) == 0,
        "false_drops == 0": len(false_drops) == 0,
        f"action_accuracy >= {acc_needed}/{n}": action_correct >= acc_needed,
        f"non_unanimous <= {MAX_NON_UNANIMOUS}": len(non_unanimous) <= MAX_NON_UNANIMOUS,
        "no action-crossing trials on conflict-expected pairs": len(conflict_cross) == 0,
        "prefilter path matches fixture path": len(path_mismatch) == 0,
    }
    return {
        "rows": rows,
        "n": n,
        "action_correct": action_correct,
        "acc_needed": acc_needed,
        "missed_conflicts": missed_conflicts,
        "false_conflicts_on_supersede": false_conflicts_on_supersede,
        "false_drops": false_drops,
        "non_unanimous": non_unanimous,
        "conflict_cross": conflict_cross,
        "path_mismatch": path_mismatch,
        "gates": gates,
        "passed": all(gates.values()),
    }


def confusion_matrix(rows: list[dict]) -> str:
    grid = {e: {p: 0 for p in RELATIONS} for e in RELATIONS}
    for r in rows:
        grid[r["expected"][0]][r["prediction"]] += 1
    head = "| expected \\ predicted | " + " | ".join(RELATIONS) + " |"
    sep = "|---" * (len(RELATIONS) + 1) + "|"
    lines = [head, sep]
    for e in RELATIONS:
        lines.append(f"| **{e}** | " + " | ".join(str(grid[e][p]) or "0" for p in RELATIONS) + " |")
    return "\n".join(lines)


def render_report(res: dict, mode: str, model: str, fixtures_path: str) -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    cfg = settings()
    out = [
        f"# Reconcile eval — {mode} — {ts}",
        "",
        f"- fixtures: `{fixtures_path}` (N={res['n']})",
        f"- model: `{model}` · trials/pair: {cfg.eval_trials} · TAU_CONF={cfg.tau_conf} · CONF_MIN={cfg.conf_min}",
        f"- **RESULT: {'PASS' if res['passed'] else 'FAIL'}** — action accuracy "
        f"{res['action_correct']}/{res['n']} (gate ≥ {res['acc_needed']})",
        "",
        "## Gates",
        "",
        "| gate | status |",
        "|---|---|",
    ]
    for g, ok in res["gates"].items():
        out.append(f"| {g} | {'✅ pass' if ok else '❌ FAIL'} |")
    out += ["", "## Relation-level confusion matrix (majority vote; expected_any counted under first)", "",
            confusion_matrix(res["rows"]), "", "## Per-pair results", "",
            "| id | path | expected | trials | prediction | action ok | unanimous |", "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        out.append(
            f"| {r['id']} | {r['path_actual']} | {'/'.join(r['expected'])} | "
            f"{', '.join(r['trials'])} | {r['prediction']} | "
            f"{'✅' if r['action_ok'] else '❌'} | {'yes' if r['unanimous'] else '⚠️ no'} |"
        )
    flips = sum(1 for r in res["rows"] if not r["unanimous"])
    out += ["", f"Flip rate: {flips}/{res['n']} pairs non-unanimous"]

    if res["non_unanimous"]:
        out += ["", "## Non-unanimous pairs (all trial outputs)", ""]
        for r in res["non_unanimous"]:
            out.append(f"### {r['id']} — expected {'/'.join(r['expected'])}")
            for i, (rel, conf, rat) in enumerate(zip(r["trials"], r["confidences"], r["rationales"])):
                out.append(f"- trial {i + 1}: **{rel}** ({conf:.2f}) — {rat}")
            out.append("")
    failures = [r for r in res["rows"] if not r["action_ok"]]
    if failures:
        out += ["", "## Failures — model rationale dump (§12.6.5)", ""]
        for r in failures:
            out.append(f"### {r['id']} — expected {'/'.join(r['expected'])}, predicted {r['prediction']}")
            for i, rat in enumerate(r["rationales"]):
                out.append(f"- trial {i + 1} ({r['trials'][i]}): {rat}")
            out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use the real Claude classifier (needs EVAL_LIVE=1)")
    ap.add_argument("--fixtures", default=str(SEED))
    args = ap.parse_args()

    fixtures = [json.loads(line) for line in Path(args.fixtures).read_text().splitlines() if line.strip()]
    cfg = settings()

    if args.live:
        if os.environ.get("EVAL_LIVE") != "1":
            print("live run refused: set EVAL_LIVE=1 (§12.1)", file=sys.stderr)
            return 2
        calls = len(fixtures) * cfg.eval_trials
        est_tok = calls * cfg.eval_est_tokens_per_call
        est_cost = est_tok / 1e6 * (cfg.eval_price_in_per_mtok + cfg.eval_price_out_per_mtok * 0.15)
        print(f"live eval: {calls} calls to {cfg.reconcile_model}, ~{est_tok} tokens, est ${est_cost:.2f}")
        from ctxvcs.llm.claude import ClaudeReconcileClient

        client = ClaudeReconcileClient()
        mode, model = "live", cfg.reconcile_model
    else:
        from ctxvcs.llm.fakes import EchoExpectedClient

        client = EchoExpectedClient({fx["id"]: expected_set(fx)[0] for fx in fixtures})
        mode, model = "fake", "echo-expected"

    res = run(fixtures, client, cfg.eval_trials)
    report = render_report(res, mode, model, args.fixtures)
    REPORTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    md = REPORTS / f"{stamp}-reconcile-{mode}.md"
    md.write_text(report)
    (REPORTS / f"{stamp}-reconcile-{mode}.json").write_text(json.dumps(res, indent=2, default=str))
    print(report)
    print(f"report written: {md}")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
