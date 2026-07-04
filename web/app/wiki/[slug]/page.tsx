"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "../../../lib/api";
import PageView from "../../../components/PageView";

export default function SubjectPage() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api(`/wiki/page/${slug}`).then(setPage).catch((e) => setErr(e.message));
  }, [slug]);

  if (err) return <div className="banner-err card">{err}</div>;
  if (!page) return <div className="muted">loading…</div>;
  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <Link href="/wiki">← wiki</Link>
        <span className="muted">
          {page.kind} · as of <span className="mono">{page.source_commit?.slice(0, 8)}</span>
        </span>
        {page.open_conflicts?.length > 0 && (
          <span className="tag tag-conflict">{page.open_conflicts.length} open conflict(s)</span>
        )}
      </div>
      {page.open_conflicts?.map((c: any) => (
        <div className="card" key={c.conflict_id}>
          <span className="tag tag-conflict">contested</span>{" "}
          fields: {c.conflicting_fields.join(", ") || "prose"} —{" "}
          <Link href={`/review/mr/${c.merge_request_id}`}>review →</Link>
        </div>
      ))}
      <PageView content={page.content} />
    </div>
  );
}
