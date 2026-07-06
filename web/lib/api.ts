export type Cfg = { url: string; repo: string; token: string };

// Dev: web on :3000, API on :8000. Prod: one origin, API under /api (Caddy).
export function apiBase(): string {
  if (typeof window === "undefined") return "http://localhost:8000";
  const o = window.location.origin;
  return o.includes("localhost:3000") || o.includes("127.0.0.1:3000")
    ? "http://localhost:8000"
    : `${o}/api`;
}

export function getCfg(): Cfg | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("ctxvcs");
  if (!raw) return null;
  try {
    const c = JSON.parse(raw);
    return c.url && c.repo && c.token ? c : null;
  } catch {
    return null;
  }
}

export function setCfg(c: Cfg) {
  localStorage.setItem("ctxvcs", JSON.stringify(c));
}

export async function api(path: string, init?: RequestInit): Promise<any> {
  const cfg = getCfg();
  if (!cfg) throw new Error("not configured");
  const res = await fetch(`${cfg.url}/repos/${cfg.repo}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${cfg.token}`,
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body?.detail ? JSON.stringify(body.detail) : res.statusText);
  return body;
}

export const ACTION_COLORS: Record<string, string> = {
  new: "tag-new",
  supersede: "tag-supersede",
  drop: "tag-drop",
  keep: "tag-keep",
  conflict: "tag-conflict",
};
