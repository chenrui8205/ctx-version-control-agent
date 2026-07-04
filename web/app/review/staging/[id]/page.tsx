"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ACTION_COLORS, api } from "../../../../lib/api";

export default function StagingPreview() {
  const { id } = useParams<{ id: string }>();
  const [st, setSt] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [committed, setCommitted] = useState<string | null>(null);

  const load = useCallback(() => {
    api(`/staging/${id}`).then(setSt).catch((e) => setErr(e.message));
  }, [id]);
  useEffect(load, [load]);

  async function commit() {
    setBusy(true);
    setErr("");
    try {
      const res = await api(`/staging/${id}/commit`, { method: "POST", body: JSON.stringify({ resolutions: [] }) });
      if (res.commit_hash) setCommitted(res.commit_hash);
      load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!st) return <div className="muted">{err || "loading…"}</div>;
  const byId: Record<string, any> = {};
  for (const e of st.entries) byId[e.id] = e;
  const hasConflicts = (st.proposed_actions || []).some((a: any) => a.action === "conflict");

  return (
    <div>
      <h2>Session preview</h2>
      <div className="card">
        <strong>{st.session_summary || "(no summary)"}</strong>
        <div className="muted">
          {st.author} · status {st.status} · parent{" "}
          <span className="mono">{st.parent_commit ? st.parent_commit.slice(0, 8) : "genesis"}</span>
          {st.merge_request_id && (
            <> · <Link href={`/review/mr/${st.merge_request_id}`}>open merge request →</Link></>
          )}
        </div>
      </div>
      {committed && (
        <div className="card banner-ok">✓ committed <span className="mono">{committed.slice(0, 8)}</span></div>
      )}
      {err && <div className="card banner-err">{err}</div>}

      {(st.proposed_actions || []).map((a: any) => {
        const e = byId[a.temp_id] || {};
        return (
          <div className="card" key={a.temp_id}>
            <div className="row">
              <span className={`tag ${ACTION_COLORS[a.action] || "tag-drop"}`}>
                {a.relation === "complementary" ? "kept-both" : a.action}
              </span>
              <strong>{a.subject_key}</strong>
              <span className="muted">{a.type} · {a.relation} · {a.path}</span>
              <span className={`tag tag-origin-${e.provenance?.origin || "agent"}`}>{e.provenance?.origin}</span>
            </div>
            <div style={{ margin: "6px 0" }}>{e.body}</div>
            <div className="muted">{a.rationale}</div>
          </div>
        );
      })}

      {st.status === "pending" && !hasConflicts && (
        <button className="primary" disabled={busy} onClick={commit}>Commit session</button>
      )}
      {st.status === "pending" && hasConflicts && (
        <div className="muted">This session has conflicts — resolve them in the merge request before commit.</div>
      )}
    </div>
  );
}
