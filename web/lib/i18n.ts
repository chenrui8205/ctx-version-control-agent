"use client";

import { useEffect, useState } from "react";

// M1 zh-CN UI chrome (spec §10): every UI string comes from this dictionary.
// Page/entry CONTENT stays English by explicit assumption — chrome only.
export type Locale = "zh" | "en";

const dict: Record<string, { zh: string; en: string }> = {
  wiki: { zh: "知识库", en: "Wiki" },
  review: { zh: "审核", en: "Review" },
  settings: { zh: "设置", en: "Settings" },
  logout: { zh: "退出", en: "Log out" },
  login: { zh: "登录", en: "Log in" },
  signup: { zh: "注册", en: "Sign up" },
  email: { zh: "邮箱", en: "Email" },
  password: { zh: "密码", en: "Password" },
  displayName: { zh: "昵称", en: "Display name" },
  inviteCode: { zh: "邀请码", en: "Invite code" },
  loginTitle: { zh: "登录团队工作台", en: "Log in to your team" },
  signupTitle: { zh: "加入团队", en: "Join the team" },
  noAccount: { zh: "没有账号？注册", en: "No account? Sign up" },
  haveAccount: { zh: "已有账号？登录", en: "Have an account? Log in" },
  openThreads: { zh: "进行中", en: "Open threads" },
  journal: { zh: "工作日志", en: "Journal" },
  index: { zh: "目录", en: "Index" },
  searchPlaceholder: { zh: "搜索团队工作上下文…", en: "Search the working context…" },
  search: { zh: "搜索", en: "Search" },
  results: { zh: "搜索结果", en: "Results" },
  noMatches: { zh: "没有找到", en: "no matches" },
  loading: { zh: "加载中…", en: "loading…" },
  asOf: { zh: "版本", en: "as of" },
  compiledAt: { zh: "编译于", en: "compiled" },
  mergeQueue: { zh: "合并队列", en: "Merge queue" },
  noOpenMrs: { zh: "没有待处理的合并请求，主干是干净的。", en: "No open merge requests. Master is clean." },
  openConflicts: { zh: "个待处理冲突", en: "open conflict(s)" },
  recentSessions: { zh: "最近的推送", en: "Recent sessions (staging)" },
  entries: { zh: "条目", en: "entries" },
  noSummary: { zh: "（无摘要）", en: "(no summary)" },
  currentOnMaster: { zh: "主干当前版本", en: "Current on master" },
  incoming: { zh: "新推送的版本", en: "Incoming" },
  acceptIncoming: { zh: "采纳新版本", en: "Accept incoming" },
  keepExisting: { zh: "保留现有版本", en: "Keep existing" },
  edit: { zh: "编辑…", en: "Edit…" },
  resolveWithEdit: { zh: "以编辑后的版本解决", en: "Resolve with edit" },
  invalidJson: { zh: "JSON 格式错误", en: "invalid JSON" },
  fields: { zh: "冲突字段", en: "fields" },
  confidence: { zh: "置信度", en: "confidence" },
  contested: { zh: "有争议", en: "contested" },
  reviewLink: { zh: "去审核 →", en: "review →" },
  backToWiki: { zh: "← 返回知识库", en: "← wiki" },
  blame: { zh: "溯源", en: "Blame" },
  blameTitle: { zh: "溯源 — 谁说的？可信吗？", en: "Blame — who says so?" },
  blameSetBy: { zh: "记录者", en: "set by" },
  blameVia: { zh: "方式", en: "via" },
  blameChallenged: { zh: "曾被质疑", en: "challenged" },
  blameDecidedBy: { zh: "裁决人", en: "decided by" },
  blameRejected: { zh: "被否决的值", en: "rejected value" },
  blameClose: { zh: "关闭", en: "Close" },
  human: { zh: "人工", en: "human" },
  agent: { zh: "智能体", en: "agent" },
  welcomeTitle: { zh: "欢迎加入！三步开始使用", en: "Welcome! Three steps to start" },
  welcomeStep1: { zh: "第一步：在你的电脑上安装命令行工具", en: "Step 1: install the CLI on your machine" },
  welcomeStep2: { zh: "第二步：登录（会提示输入邮箱和刚才的密码）", en: "Step 2: log in (prompts for email + the password you just set)" },
  welcomeStep3: {
    zh: "第三步：每次工作结束后，运行 ctxvcs push，用几句话记下这次做了什么。系统会自动整理、去重、并与团队现有认知合并；有矛盾时会提交管理员审核。",
    en: "Step 3: after each working session run ctxvcs push and jot down what happened. The system structures, dedups, and reconciles it; contradictions go to the admin for review.",
  },
  welcomeRead: {
    zh: "随时可以在这里浏览团队的最新工作状态：「进行中」是待办和未决问题，「工作日志」是每次推送的记录。",
    en: "Browse the team's current state here anytime: Open threads = todo & undecided; Journal = the session ledger.",
  },
  welcomeGo: { zh: "进入知识库 →", en: "Go to the wiki →" },
  copied: { zh: "已复制", en: "copied" },
  copy: { zh: "复制", en: "copy" },
  connection: { zh: "连接（一般由登录自动配置）", en: "Connection (normally set by login)" },
  apiUrl: { zh: "API 地址", en: "API URL" },
  repoId: { zh: "仓库 ID", en: "Repo ID" },
  apiToken: { zh: "API 令牌", en: "API token" },
  saveTest: { zh: "保存并测试", en: "Save & test" },
  connected: { zh: "连接成功 ✓", en: "connected ✓" },
  pendingReview: { zh: "待审核", en: "pending" },
};

export function t(key: string, locale: Locale): string {
  return dict[key]?.[locale] ?? key;
}

export function getLocale(): Locale {
  if (typeof window === "undefined") return "zh";
  return (localStorage.getItem("ctxvcs-locale") as Locale) || "zh";
}

export function setLocale(l: Locale) {
  localStorage.setItem("ctxvcs-locale", l);
  window.dispatchEvent(new Event("ctxvcs-locale"));
}

export function useLocale(): [Locale, (l: Locale) => void] {
  const [locale, set] = useState<Locale>("zh");
  useEffect(() => {
    set(getLocale());
    const h = () => set(getLocale());
    window.addEventListener("ctxvcs-locale", h);
    return () => window.removeEventListener("ctxvcs-locale", h);
  }, []);
  return [locale, setLocale];
}

export function useT() {
  const [locale] = useLocale();
  return (key: string) => t(key, locale);
}
