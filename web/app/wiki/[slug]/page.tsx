"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "../../../lib/api";
import PageView from "../../../components/PageView";
import BlamePanel from "../../../components/BlamePanel";
import { useT } from "../../../lib/i18n";

export default function SubjectPage() {
  const t = useT();
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<any>(null);
  const [err, setErr] = useState("");
  const [showBlame, setShowBlame] = useState(false);

  useEffect(() => {
    api(`/wiki/page/${slug}`).then(setPage).catch((e) => setErr(e.message));
  }, [slug]);

  if (err) return <div className="banner-err card">{err}</div>;
  if (!page) return <div className="muted">{t("loading")}</div>;
  const isSubject = page.kind === "subject";
  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <Link href="/wiki">{t("backToWiki")}</Link>
        <span className="muted">
          {page.kind} · {t("asOf")} <span className="mono">{page.source_commit?.slice(0, 8)}</span>
        </span>
        {page.open_conflicts?.length > 0 && (
          <span className="tag tag-conflict">{page.open_conflicts.length} {t("openConflicts")}</span>
        )}
        <span className="spacer" />
        {isSubject && (
          <button onClick={() => setShowBlame(!showBlame)}>{t("blame")}</button>
        )}
      </div>
      {showBlame && isSubject && (
        <BlamePanel subject={page.subject_key || slug} onClose={() => setShowBlame(false)} />
      )}
      {page.open_conflicts?.map((c: any) => (
        <div className="card" key={c.conflict_id}>
          <span className="tag tag-conflict">{t("contested")}</span>{" "}
          {t("fields")}: {c.conflicting_fields.join(", ") || "prose"} —{" "}
          <Link href={`/review/mr/${c.merge_request_id}`}>{t("reviewLink")}</Link>
        </div>
      ))}
      <PageView content={page.content} />
    </div>
  );
}
