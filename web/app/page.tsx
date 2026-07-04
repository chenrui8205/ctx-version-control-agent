"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getCfg } from "../lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getCfg() ? "/wiki" : "/settings");
  }, [router]);
  return null;
}
