"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ConflictCard from "../../../../components/ConflictCard";
import { api } from "../../../../lib/api";

export default function MRPage() {
  const { id } = useParams<{ id: string }>();
  const [mr, setMr] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [committed, setCommitted] = useState<string | null>(null);

  const load = useCallback(() => {
    api(`/merge-requests/${id}`).then(setMr).catch((e) => setErr(e.message));
  }, [id]);
  useEffect(load, [load]);

  async function resolve(conflictId: string, decision: any) {
    setBusy(true);
    setErr("");
    try {
      const res = await api(`/merge-requests/${id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ conflict_id: conflictId, decision }),
      });
      if (res.commit_hash) setCommitted(res.commit_hash);
      load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!mr) return <div className="muted">{err || "loading…"}</div>;
  return (
    <div>
      <h2>Merge request <span className="mono">{String(id).slice(0, 8)}</span></h2>
      <div className="card">
        <strong>{mr.session_summary || "(no summary)"}</strong>
        <div className="muted">
          {mr.author} · origin {mr.origin} · status {mr.status} · staged on parent{" "}
          <span className="mono">{mr.parent_commit ? mr.parent_commit.slice(0, 8) : "genesis"}</span>
        </div>
      </div>
      {committed && (
        <div className="card banner-ok">
          ✓ all conflicts resolved — master advanced to <span className="mono">{committed.slice(0, 8)}</span>
        </div>
      )}
      {err && <div className="card banner-err">{err}</div>}
      {mr.conflicts.map((c: any) => (
        <ConflictCard key={c.conflict_id} conflict={c} busy={busy}
                      onResolve={(d) => resolve(c.conflict_id, d)} />
      ))}
    </div>
  );
}
