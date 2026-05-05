"use client";
import { useState } from "react";
import { AlertCircle, ArrowRight, BrainCircuit, LockKeyhole, ShieldCheck } from "lucide-react";
import { login } from "@/lib/api";
import Spinner from "@/components/shared/Spinner";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      window.location.href = "/";
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="foundation-grid relative min-h-screen overflow-hidden bg-slate-950 text-white">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_30%,rgba(226,232,240,0.045),transparent_34%),linear-gradient(to_bottom,rgba(5,7,10,0.62),rgba(5,7,10,0.86)_78%)]" />
      <div className="relative mx-auto grid min-h-screen w-full max-w-6xl items-center gap-10 px-6 py-10 lg:grid-cols-[1fr_25rem]">
        <section className="hidden max-w-2xl lg:block">
          <div className="mb-6 inline-flex items-center gap-2 rounded-md border border-slate-500/20 bg-slate-950/20 px-3 py-1.5 text-xs font-medium text-slate-200">
            <BrainCircuit size={14} />
            AI Document Intelligence Platform
          </div>
          <h1 className="max-w-xl text-[40px] font-semibold leading-tight tracking-normal text-white">
            Appraisal decisions with audit-grade clarity.
          </h1>
          <p className="mt-4 max-w-lg text-sm leading-6 text-slate-400">
            Upload, process, verify, and sign off document intelligence workflows from one controlled operations surface.
          </p>
          <div className="mt-8 grid max-w-xl gap-3 sm:grid-cols-3">
            <Signal icon={ShieldCheck} label="Role gated" value="Admin / Reviewer" />
            <Signal icon={LockKeyhole} label="Session mode" value="Cookie secured" />
            <Signal icon={BrainCircuit} label="QC engine" value="Human in loop" />
          </div>
        </section>

        <section className="mx-auto w-full max-w-sm lg:mx-0">
          <div className="mb-7">
            <div className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-lg border border-slate-500/25 bg-slate-950/35 shadow-[0_0_28px_rgba(226,232,240,0.18)]">
              <span className="text-base font-semibold text-white">A</span>
            </div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">Secure workspace</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-normal text-white">Ardur Appraisal QC</h2>
            <p className="mt-1 text-sm text-slate-500">Sign in to continue your review or operations workflow.</p>
          </div>

          {error && (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-red-500/25 bg-red-950/45 px-3 py-2.5 text-sm text-red-200">
              <AlertCircle size={15} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={submit} className="rounded-lg border border-white/10 bg-[#11161C]/95 p-5 shadow-[0_22px_60px_rgba(0,0,0,0.34)] backdrop-blur">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">Username</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Enter username"
                required
                autoFocus
                className="h-10 w-full rounded-md border border-white/10 bg-[#161B22] px-3 text-sm text-white placeholder:text-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
              />
            </div>
            <div className="mt-3">
              <label className="mb-1.5 block text-xs font-medium text-slate-400">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Enter password"
                required
                className="h-10 w-full rounded-md border border-white/10 bg-[#161B22] px-3 text-sm text-white placeholder:text-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-md border border-slate-400/30 bg-slate-600 text-sm font-semibold text-white shadow-[0_0_24px_rgba(226,232,240,0.18)] transition-all hover:bg-slate-500 disabled:opacity-50"
            >
              {loading ? <Spinner size={14} /> : <ArrowRight size={14} />}
              {loading ? "Signing in..." : "Sign in"}
            </button>
            <div className="mt-4 border-t border-white/10 pt-3 text-[11px] leading-relaxed text-slate-600">
              Access is restricted to assigned administrators and reviewers. Every saved decision is tied to your session.
            </div>
          </form>
        </section>
      </div>
    </main>
  );
}

function Signal({ icon: Icon, label, value }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#11161C]/80 p-3">
      <Icon size={15} className="mb-2 text-slate-300" />
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600">{label}</div>
      <div className="mt-1 text-xs text-slate-300">{value}</div>
    </div>
  );
}
