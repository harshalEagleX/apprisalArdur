"use client";
import { useEffect } from "react";
import { Loader2, ShieldCheck } from "lucide-react";

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
    <div className="min-h-screen flex items-center justify-center bg-slate-950 px-6 text-white">
      <div className="w-full max-w-sm rounded-lg border border-slate-800 bg-slate-900 p-6 text-center">
        <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-blue-900/50 bg-blue-950/40">
          <ShieldCheck size={20} className="text-blue-300" />
        </div>
        <h1 className="text-base font-semibold text-white">Opening your workspace</h1>
        <p className="mt-1 text-sm text-slate-500">Checking your role and routing you to the right dashboard.</p>
        <div className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-500">
          <Loader2 size={14} className="animate-spin text-blue-400" />
          Preparing session
        </div>
      </div>
    </div>
  );
}
