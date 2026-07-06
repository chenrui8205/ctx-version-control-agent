"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, getCfg } from "../lib/api";
import { useLocale, useT } from "../lib/i18n";

export default function Nav() {
  const p = usePathname() || "";
  const t = useT();
  const [locale, setLoc] = useLocale();
  const router = useRouter();
  const [pending, setPending] = useState(0);
  const [user, setUser] = useState<any>(null);
  const cls = (prefix: string) => (p.startsWith(prefix) ? "active" : "");

  useEffect(() => {
    try { setUser(JSON.parse(localStorage.getItem("ctxvcs-user") || "null")); } catch {}
    if (!getCfg()) return;
    const poll = () =>
      api("/merge-requests?status=open")
        .then((d) => setPending((d.merge_requests || []).length))
        .catch(() => {});
    poll();
    const id = setInterval(poll, 30_000);
    return () => clearInterval(id);
  }, [p]);

  function logout() {
    localStorage.removeItem("ctxvcs");
    localStorage.removeItem("ctxvcs-user");
    router.push("/login");
  }

  return (
    <nav className="top">
      <span className="brand">ctx‑vcs</span>
      <Link className={cls("/wiki")} href="/wiki">{t("wiki")}</Link>
      <Link className={cls("/review")} href="/review">
        {t("review")}
        {pending > 0 && <span className="tag tag-conflict" style={{ marginLeft: 6 }}>{pending}</span>}
      </Link>
      <span className="spacer" />
      <a style={{ cursor: "pointer" }} onClick={() => setLoc(locale === "zh" ? "en" : "zh")}>
        {locale === "zh" ? "EN" : "中文"}
      </a>
      <Link className={cls("/settings")} href="/settings">{t("settings")}</Link>
      {user && <a style={{ cursor: "pointer" }} onClick={logout}>{t("logout")}</a>}
    </nav>
  );
}
