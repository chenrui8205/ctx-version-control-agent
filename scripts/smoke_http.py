#!/usr/bin/env python
"""Scripted end-to-end over HTTP (M0 acceptance, no-LLM path).

Uses fresh subjects so reconciliation finds no candidates — exercises repo bootstrap,
auth, staging jobs, the §4.3 commit, compile-after-commit, wiki serving, FTS, history,
and the deterministic exact-duplicate drop. The classifier paths are covered by
evals/ (fake mode in CI, live with EVAL_LIVE=1).

Run: uv run python scripts/smoke_http.py [base_url]
"""

import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
n = uuid.uuid4().hex[:8]


def wait_job(c: httpx.Client, job_id: str) -> dict:
    for _ in range(120):
        r = c.get(f"/jobs/{job_id}").raise_for_status().json()
        if r["status"] in ("done", "error"):
            return r
        time.sleep(0.3)
    raise TimeoutError(job_id)


def check(name: str, ok: bool, detail: str = ""):
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        sys.exit(1)


def main():
    anon = httpx.Client(base_url=BASE, timeout=60)
    r = anon.post("/repos", json={"name": f"smoke-{n}", "owner": "chenrui"}).raise_for_status().json()
    repo, token = r["repo_id"], r["token"]
    c = httpx.Client(base_url=BASE, timeout=60, headers={"Authorization": f"Bearer {token}"})
    check("repo created + owner token issued", bool(repo and token))

    r = c.get(f"/repos/{repo}/wiki/index").raise_for_status().json()
    check("index page seeded on repo creation", r["kind"] == "index")

    check("unauthenticated request rejected",
          anon.get(f"/repos/{repo}/subjects").status_code == 401)

    r = c.post(f"/repos/{repo}/members", json={"principal": "teammate", "role": "member"})
    check("member added with token", r.status_code == 200 and r.json()["token"])

    entries = [
        {"type": "finding", "subject": f"smoke-cache-{n}",
         "fields": {"ttl_minutes": 15, "confidence": "high"},
         "body": f"Negative cache TTL is 15 minutes; hit rate 92 percent in staging. [{n}]",
         "provenance": {"origin": "agent", "ts": "2026-07-04"}},
        {"type": "next_step", "subject": f"smoke-alerts-{n}",
         "fields": {"status": "open", "owner": "chenrui"},
         "body": f"Wire the DLQ depth alert to pagerduty. [{n}]",
         "provenance": {"origin": "human", "ts": "2026-07-04"}},
    ]
    r = c.post(f"/repos/{repo}/stage",
               json={"entries": entries, "session_summary": f"smoke session {n}"}).raise_for_status().json()
    job = wait_job(c, r["job_id"])
    check("stage job clean, two new entries", job["merge_status"] == "clean"
          and [a["action"] for a in job["proposed_actions"]] == ["new", "new"], str(job.get("error")))
    staging_id = job["staging_id"]

    r = c.post(f"/repos/{repo}/staging/{staging_id}/commit", json={"resolutions": []}).raise_for_status().json()
    check("commit advances master", r["merge_status"] == "committed" and r["commit_hash"])
    commit1 = r["commit_hash"]

    time.sleep(1.5)  # compile job is async, eventual consistency is seconds (§7)
    ot = c.get(f"/repos/{repo}/wiki/page/open-threads").raise_for_status().json()
    check("open-threads lists the new step", "DLQ depth alert" in ot["content"])
    check("open-threads as_of exposes lag", f"as_of_commit: {commit1}" in ot["content"])

    r = c.get(f"/repos/{repo}/wiki/search", params={"q": "pagerduty"}).raise_for_status().json()
    check("FTS finds the entry", len(r["results"]) >= 1)

    r = c.get(f"/repos/{repo}/subjects").raise_for_status().json()
    check("subject registry has both subjects", len(r["subjects"]) == 2)

    r = c.get(f"/repos/{repo}/commits").raise_for_status().json()
    check("journal ledger has the session", len(r["commits"]) == 1
          and r["commits"][0]["summary"] == f"smoke session {n}")

    # identical push again: deterministic exact-hash drop, no new rows, commit refused
    r = c.post(f"/repos/{repo}/stage",
               json={"entries": entries, "session_summary": "identical again",
                     "parent_commit": commit1}).raise_for_status().json()
    job = wait_job(c, r["job_id"])
    check("identical entries dropped via exact path",
          all(a["action"] == "drop" and a["path"] == "exact" for a in job["proposed_actions"]))
    r = c.post(f"/repos/{repo}/staging/{job['staging_id']}/commit", json={"resolutions": []})
    check("empty commit refused, master unmoved", r.status_code == 409)
    r = c.get(f"/repos/{repo}/commits").raise_for_status().json()
    check("still exactly one commit", len(r["commits"]) == 1)

    # close the step via a refines push — but with no LLM key this pair would need the
    # classifier; the collision-exempt status field routes it to the open path. Skipped
    # here; covered by S2 (fake) and live evals.
    print("\nsmoke: ALL GREEN")


if __name__ == "__main__":
    main()
