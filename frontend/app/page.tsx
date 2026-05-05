"use client";
import { useEffect } from "react";
import { BrainCircuit, ShieldCheck } from "lucide-react";
import Spinner from "@/components/shared/Spinner";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function RootPage() {
  useEffect(() => {
    fetch(`${JAVA}/api/me`, { credentials: "include" })
      .then(async r => {
        if (!r.ok) { window.location.href = "/login"; return; }
        const { role } = await r.json() as { role: string };
        if (role === "ADMIN") window.location.href = "/admin";
        else if (role === "REVIEWER") window.location.href = "/reviewer/queue";
        else window.location.href = "/login";
      })
      .catch(() => { window.location.href = "/login"; });
  }, []);

  return (
    <main className="foundation-grid relative min-h-screen overflow-hidden bg-slate-950 px-6 text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.1),transparent_32%),linear-gradient(to_bottom,#0B0F14,#0B0F14)]" />
      <div className="relative flex min-h-screen items-center justify-center">
        <div className="w-full max-w-sm rounded-lg border border-white/10 bg-[#11161C]/95 p-6 text-center shadow-[0_22px_60px_rgba(0,0,0,0.36)] backdrop-blur">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-blue-500/25 bg-blue-950/35 shadow-[0_0_28px_rgba(59,130,246,0.18)]">
            <ShieldCheck size={21} className="text-blue-300" />
          </div>
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-[#161B22] px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            <BrainCircuit size={11} />
            Session intelligence
          </div>
          <h1 className="text-base font-semibold text-white">Opening your workspace</h1>
          <p className="mt-1 text-sm leading-relaxed text-slate-500">Checking your role and routing you to the correct decision surface.</p>
          <div className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-500">
            <Spinner size={14} className="text-blue-400" />
            Preparing session
          </div>
        </div>
      </div>
    </main>
  );
}
