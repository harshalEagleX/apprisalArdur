"use client";
import { useEffect, useState, useCallback } from "react";
import { Plus, Building2 } from "lucide-react";
import { getClients, type Client } from "@/lib/api";
import ClientModal from "@/components/admin/ClientModal";
import EmptyState from "@/components/shared/EmptyState";
import { CardSkeleton } from "@/components/shared/Skeleton";
import { toast } from "@/lib/toast";

export default function ClientsPage() {
  const [clients, setClients]     = useState<Client[]>([]);
  const [loading, setLoading]     = useState(true);
  const [showModal, setShowModal] = useState(false);

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

  return (
    <div className="p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-lg font-semibold text-white">Client organisations</h1>
          <p className="text-slate-500 text-sm mt-0.5">Tenant organisations whose appraisals this platform reviews</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="h-9 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm flex items-center gap-1.5 font-medium transition-colors"
        >
          <Plus size={14} /> New client
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : clients.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl">
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
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {clients.map(c => (
            <div key={c.id} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-colors">
              {/* Avatar */}
              <div className="w-10 h-10 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center mb-4">
                <span className="text-base font-bold text-slate-300">{c.name[0].toUpperCase()}</span>
              </div>
              <div className="font-semibold text-slate-200 text-sm">{c.name}</div>
              <div className="text-xs text-slate-500 font-mono mt-0.5">{c.code}</div>
              <div className="mt-3 flex items-center gap-2">
                <span className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md border font-medium ${
                  c.status === "ACTIVE"
                    ? "bg-green-950/50 border-green-800/50 text-green-400"
                    : "bg-slate-800 border-slate-700 text-slate-500"
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
