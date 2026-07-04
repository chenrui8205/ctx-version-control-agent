#!/usr/bin/env python
"""Thin CLI for the Context VCS API (§8). Plain REST with the user's token; no MCP.

Env: CTXVCS_URL (default http://localhost:8000), CTXVCS_REPO, CTXVCS_TOKEN.
"""

import argparse
import json
import os
import sys
import time

import httpx


def _client() -> tuple[httpx.Client, str]:
    url = os.environ.get("CTXVCS_URL", "http://localhost:8000")
    repo = os.environ.get("CTXVCS_REPO")
    token = os.environ.get("CTXVCS_TOKEN")
    if not repo or not token:
        sys.exit("set CTXVCS_REPO and CTXVCS_TOKEN")
    return httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=120), repo


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(prog="ctxvcs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("subjects")
    sub.add_parser("schema")
    p = sub.add_parser("stage")
    p.add_argument("entries_file")
    p.add_argument("--summary", required=True)
    p.add_argument("--parent", default=None)
    p = sub.add_parser("job")
    p.add_argument("job_id")
    p.add_argument("--wait", action="store_true")
    p = sub.add_parser("preview")
    p.add_argument("staging_id")
    p = sub.add_parser("commit")
    p.add_argument("staging_id")
    p.add_argument("--resolutions", default=None, help="JSON file: [{conflict_id, decision}]")
    p = sub.add_parser("journal")
    p.add_argument("--last", type=int, default=3)
    p = sub.add_parser("page")
    p.add_argument("slug")
    p.add_argument("--section", default=None)
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=10)
    sub.add_parser("commits")

    args = ap.parse_args()
    client, repo = _client()

    if args.cmd == "subjects":
        _print(client.get(f"/repos/{repo}/subjects").raise_for_status().json())
    elif args.cmd == "schema":
        _print(client.get(f"/repos/{repo}/schema").raise_for_status().json())
    elif args.cmd == "stage":
        entries = json.loads(open(args.entries_file).read())
        body = {"entries": entries, "session_summary": args.summary, "parent_commit": args.parent}
        r = client.post(f"/repos/{repo}/stage", json=body).raise_for_status().json()
        _print(r)
    elif args.cmd == "job":
        while True:
            r = client.get(f"/jobs/{args.job_id}").raise_for_status().json()
            if not args.wait or r["status"] in ("done", "error"):
                _print(r)
                break
            time.sleep(1)
    elif args.cmd == "preview":
        _print(client.get(f"/repos/{repo}/staging/{args.staging_id}").raise_for_status().json())
    elif args.cmd == "commit":
        resolutions = json.loads(open(args.resolutions).read()) if args.resolutions else []
        r = client.post(f"/repos/{repo}/staging/{args.staging_id}/commit",
                        json={"resolutions": resolutions})
        if r.status_code == 409:
            _print(r.json())
            sys.exit("conflicts unresolved — resolve in the review queue")
        _print(r.raise_for_status().json())
    elif args.cmd == "journal":
        page = client.get(f"/repos/{repo}/wiki/page/journal").raise_for_status().json()
        blocks = page["content"].split("\n## ")
        print(blocks[0])
        for b in blocks[1:args.last + 1]:
            print("## " + b)
    elif args.cmd == "page":
        params = {"section": args.section} if args.section else {}
        page = client.get(f"/repos/{repo}/wiki/page/{args.slug}", params=params).raise_for_status().json()
        print(page["content"])
    elif args.cmd == "search":
        _print(client.get(f"/repos/{repo}/wiki/search",
                          params={"q": args.query, "k": args.k}).raise_for_status().json())
    elif args.cmd == "commits":
        _print(client.get(f"/repos/{repo}/commits").raise_for_status().json())


if __name__ == "__main__":
    main()
