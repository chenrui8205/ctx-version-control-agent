"""ctxvcs — Context VCS client (M1, spec §8).

Write: `ctxvcs push` (raw notes → server-side extraction → preview → auto-commit
when clean). Read: threads / journal / page / search / pull / blame. Agent path:
stage --file + commit. Setup: login / install-skill.
"""

import argparse
import getpass
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

CONFIG_PATH = Path.home() / ".ctxvcs" / "config.json"
PUSH_TEMPLATE = """\
# Session notes — what happened this session?
# Bullets are fine. Say what you DECIDED (and what you rejected), what you FOUND,
# what you CHANGED, questions you OPENED or CLOSED, and next steps (with owners).
# Phrase changes as changes ("raised TTL 15m -> 30m after the spike"), not bare
# claims ("TTL is 30m"). Lines starting with # are ignored.

"""


# ---------- config / http ----------

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit("not logged in — run: ctxvcs login")
    return json.loads(CONFIG_PATH.read_text())


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=1))
    CONFIG_PATH.chmod(0o600)


def client(cfg: dict) -> httpx.Client:
    return httpx.Client(base_url=cfg["api_url"], timeout=120,
                        headers={"Authorization": f"Bearer {cfg['token']}"})


def die_on_error(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        sys.exit(f"error {r.status_code}: {detail}")
    return r.json()


def web_url(cfg: dict, path: str = "") -> str:
    return cfg.get("web_url", cfg["api_url"]).rstrip("/") + path


# ---------- commands ----------

def cmd_login(args) -> None:
    api = args.api or (load_config()["api_url"] if CONFIG_PATH.exists() else None) \
        or input("API url [http://localhost:8000]: ").strip() or "http://localhost:8000"
    email = args.email or input("email: ").strip()
    password = getpass.getpass("password: ")
    r = httpx.post(f"{api.rstrip('/')}/auth/login", json={"email": email, "password": password},
                   timeout=30)
    data = die_on_error(r)
    web = args.web or (api.replace(":8000", ":3000") if ":8000" in api else api.removesuffix("/api"))
    save_config({"api_url": api.rstrip("/"), "web_url": web.rstrip("/"), "token": data["token"],
                 "repo_id": data["repo_id"], "email": email})
    print(f"logged in as {email} ({data.get('display_name')}) — config: {CONFIG_PATH}")
    print("note: logging in again anywhere rotates your token; re-run login here if that happens.")


def _read_notes(args) -> str:
    if args.file:
        return Path(args.file).read_text()
    if args.stdin:
        return sys.stdin.read()
    if args.notes:
        return args.notes
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
        f.write(PUSH_TEMPLATE)
        path = f.name
    subprocess.call([editor, path])
    raw = Path(path).read_text()
    os.unlink(path)
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#")).strip()


def _poll_job(c: httpx.Client, job_id: str) -> dict:
    for _ in range(240):
        job = die_on_error(c.get(f"/jobs/{job_id}"))
        if job["status"] in ("done", "error"):
            return job
        time.sleep(1)
    sys.exit("job timed out")


def _print_preview(job: dict) -> None:
    actions = job.get("proposed_actions") or []
    counts: dict[str, int] = {}
    for a in actions:
        label = {"new": "new", "keep": "kept", "supersede": "update",
                 "drop": "dropped (already known)", "conflict": "CONFLICT"}[a["action"]]
        counts[label] = counts.get(label, 0) + 1
    print("preview: " + " · ".join(f"{v} {k}" for k, v in counts.items()))
    for a in actions:
        flag = f"  [was {a['downgraded_from']}, kept both]" if a.get("downgraded_from") else ""
        print(f"  - {a['action']:9s} {a['type']:13s} {a['subject_key']}{flag}")
        if a["action"] in ("drop", "supersede", "conflict"):
            print(f"              {a.get('rationale', '')[:120]}")


def cmd_push(args) -> None:
    cfg = load_config()
    notes = _read_notes(args)
    if not notes.strip():
        sys.exit("no notes — nothing to push")
    with client(cfg) as c:
        job_id = die_on_error(c.post(f"/repos/{cfg['repo_id']}/stage",
                                     json={"raw_notes": notes}))["job_id"]
        print("extracting + reconciling…")
        job = _poll_job(c, job_id)
        if job["status"] == "error" or job.get("error"):
            sys.exit(f"stage failed: {job.get('error')}")
        _print_preview(job)
        if job.get("session_summary"):
            print(f"summary: {job['session_summary']}")
        if job["merge_status"] == "needs_review":
            print(f"\nconflict needs review → {web_url(cfg, '/review')}")
            print(f"(staging {job['staging_id']} stays pending until it's resolved there)")
            return
        cj = die_on_error(c.post(f"/repos/{cfg['repo_id']}/staging/{job['staging_id']}/commit",
                                 json={"resolutions": []}))
        commit = (cj.get("commit_hash") or "")[:8]
        print(f"\ncommitted {commit} — wiki: {web_url(cfg, '/wiki')}")


def cmd_stage(args) -> None:
    """Agent/skill path: structured entries from a file."""
    cfg = load_config()
    payload = json.loads(Path(args.file).read_text())
    entries = payload["entries"] if isinstance(payload, dict) else payload
    summary = args.summary or (payload.get("session_summary", "") if isinstance(payload, dict) else "")
    with client(cfg) as c:
        job_id = die_on_error(c.post(f"/repos/{cfg['repo_id']}/stage",
                                     json={"entries": entries, "session_summary": summary}))["job_id"]
        job = _poll_job(c, job_id)
        if job["status"] == "error" or job.get("error"):
            sys.exit(f"stage failed: {job.get('error')}")
        _print_preview(job)
        print(json.dumps({"staging_id": job["staging_id"], "merge_status": job["merge_status"],
                          "merge_request_id": job.get("merge_request_id")}))


def cmd_commit(args) -> None:
    cfg = load_config()
    with client(cfg) as c:
        out = die_on_error(c.post(f"/repos/{cfg['repo_id']}/staging/{args.staging_id}/commit",
                                  json={"resolutions": []}))
        print(json.dumps(out))


def _print_page(cfg: dict, slug: str, section: str | None = None) -> None:
    with client(cfg) as c:
        params = {"section": section} if section else {}
        page = die_on_error(c.get(f"/repos/{cfg['repo_id']}/wiki/page/{slug}", params=params))
        print(page["content"])


def cmd_threads(args) -> None:
    _print_page(load_config(), "open-threads")


def cmd_journal(args) -> None:
    cfg = load_config()
    with client(cfg) as c:
        page = die_on_error(c.get(f"/repos/{cfg['repo_id']}/wiki/page/journal"))
    parts = page["content"].split("\n## ")
    print(parts[0] + "".join(f"\n## {p}" for p in parts[1: 1 + args.last]))


def cmd_page(args) -> None:
    _print_page(load_config(), args.slug, args.section)


def cmd_search(args) -> None:
    cfg = load_config()
    with client(cfg) as c:
        out = die_on_error(c.get(f"/repos/{cfg['repo_id']}/wiki/search",
                                 params={"q": args.query, "k": 10}))
    for hit in out["results"]:
        print(f"{hit['slug']}#{hit.get('section_id', '')}: {hit.get('snippet', '')}")


def cmd_pull(args) -> None:
    cfg = load_config()
    with client(cfg) as c:
        out = die_on_error(c.get(f"/repos/{cfg['repo_id']}/context"))
    print(out["content"])


def _fmt_blame(b: dict, field: str | None) -> None:
    if field:
        f = b["fields"].get(field)
        if not f:
            return
        i = f["introduced_in"]
        print(f"{b['subject_key']}.{field} = {f['value']!r}")
        print(f"  set by {i['author']} ({i['origin']}) · commit {i['commit'][:8]} · {i['committed_at']}")
    for v in b["versions"]:
        via = v["landed"].get("via")
        line = f"  [{v['commit'][:8]}] {v['type']} by {v['author']} ({v['origin']}) via {via}"
        if via == "conflict_resolution":
            line += f" — decided {v['landed'].get('decided')} by {v['landed'].get('decided_by')}"
        print(line)
        for ch in v.get("challenges", []):
            print(f"      ⚔ challenged by {ch['challenger']} ({ch['challenger_origin']}) "
                  f"with {ch['challenged_fields']} → {ch['decided']} by {ch['decided_by']}")


def cmd_blame(args) -> None:
    cfg = load_config()
    with client(cfg) as c:
        subj = die_on_error(c.get(f"/repos/{cfg['repo_id']}/subjects/{args.subject}/entries"))
        for e in subj["entries"]:
            b = die_on_error(c.get(f"/repos/{cfg['repo_id']}/entries/{e['entry_id']}/blame"))
            if args.field and args.field not in b["fields"]:
                continue
            print(f"\n— {e['type']}: {e['gist'][:80]}")
            _fmt_blame(b, args.field)


SKILL_MD = """\
---
name: ctxvcs-push
description: Push this session's context to the team's Context VCS, or pull the team's
  current context. Trigger on "push context", "pull context", "team context".
---

# Context VCS — agent skill (CLI-backed)

Everything goes through the installed `ctxvcs` CLI (the user ran `ctxvcs login`).

## Pull (session start)
Run `ctxvcs pull` — open threads + recent sessions. Fetch depth per subject with
`ctxvcs page <subject>`; keyword lookup with `ctxvcs search <q>`.

## Push (session end)
1. `ctxvcs page open-threads` and note existing subjects; REUSE subject names —
   invent a new one only when nothing fits.
2. Distill the session into entries (decision / finding / state_change /
   open_question / next_step / constraint). Tag provenance.origin: `human` for what
   the user said/decided, `agent` for what you researched/inferred. Closing a
   question/step = a new entry with status "closed". Phrase value changes as changes.
3. Write `{"entries": [...], "session_summary": "1-3 sentences"}` to a temp JSON file
   and run `ctxvcs stage --file <file>`.
4. Read the preview. If merge_status is "clean": `ctxvcs commit <staging_id>` and
   report the result. If "needs_review": STOP — tell the user to resolve in the
   review UI; never resolve conflicts yourself.
"""


def cmd_install_skill(args) -> None:
    dest = Path.home() / ".claude" / "skills" / "ctxvcs-push"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(SKILL_MD)
    print(f"installed {dest / 'SKILL.md'}")
    print('your agent now responds to "push context" / "pull context" in any project.')


def main() -> None:
    p = argparse.ArgumentParser(prog="ctxvcs", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login", help="log in and store credentials")
    s.add_argument("--api"), s.add_argument("--web"), s.add_argument("--email")
    s.set_defaults(fn=cmd_login)

    s = sub.add_parser("push", help="push session notes (opens $EDITOR unless --file/--stdin)")
    s.add_argument("--file"), s.add_argument("--stdin", action="store_true"), s.add_argument("--notes")
    s.set_defaults(fn=cmd_push)

    s = sub.add_parser("stage", help="agent path: stage structured entries from a JSON file")
    s.add_argument("--file", required=True), s.add_argument("--summary")
    s.set_defaults(fn=cmd_stage)

    s = sub.add_parser("commit", help="finalize a clean staging")
    s.add_argument("staging_id")
    s.set_defaults(fn=cmd_commit)

    sub.add_parser("threads", help="open threads (the landing view)").set_defaults(fn=cmd_threads)

    s = sub.add_parser("journal", help="recent sessions")
    s.add_argument("--last", type=int, default=3)
    s.set_defaults(fn=cmd_journal)

    s = sub.add_parser("page", help="a subject page (or index/journal/open-threads)")
    s.add_argument("slug"), s.add_argument("--section")
    s.set_defaults(fn=cmd_page)

    s = sub.add_parser("search", help="keyword search over the wiki")
    s.add_argument("query")
    s.set_defaults(fn=cmd_search)

    sub.add_parser("pull", help="one-shot context bundle (paste into any agent)"
                   ).set_defaults(fn=cmd_pull)

    s = sub.add_parser("blame", help="溯源: who says so, and was it ever contested?")
    s.add_argument("subject"), s.add_argument("field", nargs="?")
    s.set_defaults(fn=cmd_blame)

    sub.add_parser("install-skill", help="install the agent skill to ~/.claude/skills"
                   ).set_defaults(fn=cmd_install_skill)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
