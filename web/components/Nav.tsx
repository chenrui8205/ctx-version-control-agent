"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Nav() {
  const p = usePathname() || "";
  const cls = (prefix: string) => (p.startsWith(prefix) ? "active" : "");
  return (
    <nav className="top">
      <span className="brand">ctx‑vcs</span>
      <Link className={cls("/wiki")} href="/wiki">Wiki</Link>
      <Link className={cls("/review")} href="/review">Review</Link>
      <span className="spacer" />
      <Link className={cls("/settings")} href="/settings">Settings</Link>
    </nav>
  );
}
