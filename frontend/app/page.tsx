"use client";
import { useEffect } from "react";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function RootPage() {
  useEffect(() => {
    fetch(`${JAVA}/api/me`, { credentials: "include" })
      .then(async r => {
        if (!r.ok) { window.location.href = "/login"; return; }
        const { role } = await r.json() as { role: string };
        if (role === "ADMIN")    window.location.href = "/admin";
        else if (role === "REVIEWER") window.location.href = "/reviewer/queue";
        else window.location.href = "/login";
      })
      .catch(() => { window.location.href = "/login"; });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );
}
