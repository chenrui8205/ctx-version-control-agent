"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

export default function ReviewQueue() {
  const [mrs, setMrs] = useState<any[]>([]);
  const [staging, setStaging] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api("/merge-requests?status=open").then((d) => setMrs(d.merge_requests)).catch((e) => setErr(e.message));
    api("/staging").then((d) => setStaging(d.staging)).catch(() => {});
  }, []);

  return (
    <div>
      <h2>Merge queue</h2>
      {err && <div className="banner-err card">{err}</div>}
      {mrs.length === 0 && <div className="card muted">No open merge requests. Master is clean.</div>}
      {mrs.map((mr) => (
        <Link key={mr.merge_request_id} href={`/review/mr/${mr.merge_request_id}`}>
          <div className="card">
            <div className="row">
              <span className="tag tag-conflict">{mr.n_open} open conflict{mr.n_open === 1 ? "" : "s"}</span>
              <strong>{mr.session_summary || "(no summary)"}</strong>
            </div>
            <div className="muted">
              {mr.author} · {mr.origin} · {mr.created_at?.slice(0, 19)} · MR <span className="mono">{mr.merge_request_id.slice(0, 8)}</span>
            </div>
          </div>
        </Link>
      ))}

      <h2 style={{ marginTop: 34 }}>Recent sessions (staging)</h2>
      {staging.map((s) => (
        <Link key={s.staging_id} href={`/review/staging/${s.staging_id}`}>
          <div className="card">
            <div className="row">
              <span className={`tag ${s.status === "committed" ? "tag-new" : s.status === "pending" ? "tag-supersede" : "tag-drop"}`}>{s.status}</span>
              <strong>{s.session_summary || "(no summary)"}</strong>
            </div>
            <div className="muted">{s.author} · {s.n_entries} entries · {s.created_at?.slice(0, 19)}</div>
          </div>
        </Link>
      ))}
    </div>
  );
}
