"use client";
import { useEffect, useState, useCallback } from "react";
import { Plus, Building2, Search, CheckCircle2, XCircle } from "lucide-react";
import type { ComponentType } from "react";
import { getClients, type Client } from "@/lib/api";
import ClientModal from "@/components/admin/ClientModal";
import EmptyState from "@/components/shared/EmptyState";
import { CardSkeleton } from "@/components/shared/Skeleton";
import { toast } from "@/lib/toast";

export default function ClientsPage() {
  const [clients, setClients]     = useState<Client[]>([]);
  const [loading, setLoading]     = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [search, setSearch]       = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setClients(await getClients()); }
    catch { toast.error("Failed to load clients"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const filtered = search
    ? clients.filter(c =>
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.code.toLowerCase().includes(search.toLowerCase()) ||
        (c.status ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : clients;
  const activeCount = clients.filter(c => (c.status ?? "ACTIVE") === "ACTIVE").length;

  return (
    <div className="max-w-[1400px] p-6">
      <div className="flex flex-col gap-4 mb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Tenant registry</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-white">Client organisations</h1>
          <p className="mt-1 text-sm text-slate-500">Tenant organisations whose appraisals this platform reviews.</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex h-9 items-center gap-1.5 rounded-md border border-blue-400/30 bg-blue-600 px-4 text-sm font-semibold text-white shadow-[0_0_22px_rgba(59,130,246,0.16)] transition-colors hover:bg-blue-500"
        >
          <Plus size={14} /> New client
        </button>
      </div>

      <div className="mb-4 grid gap-2 lg:grid-cols-[1fr_auto_auto] lg:items-center">
        <div className="relative max-w-sm">
          <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search clients by name, code, or status..."
            className="h-9 w-full rounded-md border border-white/10 bg-[#11161C] pl-8 pr-9 text-sm text-white placeholder-slate-600 transition-colors focus:border-blue-500/70 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.04] hover:text-slate-300" aria-label="Clear search">
              <XCircle size={13} />
            </button>
          )}
        </div>
        <ClientSummary icon={Building2} label="Total clients" value={clients.length} tone="slate" />
        <ClientSummary icon={CheckCircle2} label="Active" value={activeCount} tone="green" />
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : clients.length === 0 ? (
        <div className="rounded-lg border border-white/10 bg-[#11161C]">
          <EmptyState
            icon={Building2}
            title="No client organisations"
            description="Create a client organisation to start uploading and reviewing appraisal batches."
            action={
              <button onClick={() => setShowModal(true)}
                className="flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 transition-colors">
                <Plus size={14} /> Create first client
              </button>
            }
          />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-white/10 bg-[#11161C]">
          <EmptyState
            icon={Search}
            title="No clients match"
            description="Clear the search to return to the full client list."
            action={<button onClick={() => setSearch("")} className="text-sm text-blue-400 hover:text-blue-300">Clear search</button>}
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(c => (
            <div key={c.id} className="rounded-lg border border-white/10 bg-[#11161C] p-5 shadow-[0_12px_32px_rgba(0,0,0,0.16)] transition-colors hover:border-blue-500/25">
              {/* Avatar */}
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-[#161B22]">
                <span className="text-base font-bold text-slate-300">{c.name[0].toUpperCase()}</span>
              </div>
              <div className="font-semibold text-slate-200 text-sm">{c.name}</div>
              <div className="text-xs text-slate-500 font-mono mt-0.5">{c.code}</div>
              <div className="mt-3 flex items-center gap-2">
                <span className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md border font-medium ${
                  c.status === "ACTIVE"
                    ? "bg-green-950/40 border-green-500/25 text-green-200"
                    : "bg-[#161B22] border-white/10 text-slate-500"
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${c.status === "ACTIVE" ? "bg-green-400" : "bg-slate-500"}`} />
                  {c.status ?? "Active"}
                </span>
              </div>
              {c.createdAt && (
                <div className="text-[11px] text-slate-600 mt-3">
                  Added {new Date(c.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <ClientModal open={showModal} onClose={() => setShowModal(false)} onSaved={load} />
    </div>
  );
}

function ClientSummary({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  tone: "slate" | "green";
}) {
  const styles = tone === "green"
    ? "border-green-500/25 bg-green-950/30 text-green-200"
    : "border-white/10 bg-[#11161C] text-slate-300";
  return (
    <div className={`flex h-9 items-center gap-2 rounded-lg border px-3 ${styles}`}>
      <Icon size={14} className="opacity-80" />
      <span className="text-sm font-semibold tabular-nums">{value}</span>
      <span className="text-[11px] uppercase tracking-wide opacity-70">{label}</span>
    </div>
  );
}
