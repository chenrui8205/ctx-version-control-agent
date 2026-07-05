#!/usr/bin/env python
"""Golden scenario runner (§12.3): S1 mixed second session, S2 close the loop.

--mode fake  : deterministic scripted relations (CI on every change)
--mode live  : real classifier + embedder (EVAL_LIVE=1; nightly / on prompt changes)

Writes a report to evals/reports/. Exit 1 on any failed check.
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctxvcs.config import settings  # noqa: E402
from ctxvcs.store.db import session_factory  # noqa: E402

from evals.scenario_lib import run_s1, run_s2, run_s3  # noqa: E402

REPORTS = Path(__file__).resolve().parent / "reports"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fake", "live"], default="fake")
    args = ap.parse_args()

    if args.mode == "live":
        if os.environ.get("EVAL_LIVE") != "1":
            print("live run refused: set EVAL_LIVE=1 (§12.1)", file=sys.stderr)
            return 2
        cfg = settings()
        print(f"live scenarios: ~26 classifier calls to {cfg.reconcile_model} + embeddings")
    else:
        os.environ.setdefault("CTXVCS_EMBED_PROVIDER", "fake")

    runs = []
    for fn in (run_s1, run_s2, run_s3):
        with session_factory()() as session:
            runs.append(fn(session, args.mode))

    ts = datetime.now(UTC)
    lines = [f"# Scenario evals — {args.mode} — {ts.strftime('%Y-%m-%d %H:%M:%SZ')}", ""]
    ok_all = True
    for r in runs:
        lines += [f"## {r.name} — {'PASS' if r.passed else 'FAIL'}", ""]
        for c in r.checks:
            lines.append(f"- {'✅' if c.ok else '❌'} {c.name}" + (f" — {c.detail}" if c.detail else ""))
        lines.append("")
        ok_all = ok_all and r.passed
    report = "\n".join(lines) + "\n"
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"{ts.strftime('%Y%m%d-%H%M%S')}-scenarios-{args.mode}.md"
    out.write_text(report)
    print(report)
    print(f"report written: {out}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
