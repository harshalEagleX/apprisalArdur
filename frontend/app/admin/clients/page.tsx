"use client";
import { useEffect, useState, useCallback } from "react";
import { getClients, type Client } from "@/lib/api";
import ClientModal from "@/components/admin/ClientModal";

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setClients(await getClients()); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">Client Organisations</h1>
        <button onClick={() => setShowModal(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg font-medium transition-colors">
          + Add Client
        </button>
      </div>

      {loading ? (
        <div className="text-slate-500 text-sm">Loading…</div>
      ) : clients.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-3">🏢</div>
          <h3 className="text-lg font-semibold text-slate-300 mb-1">No clients yet</h3>
          <p className="text-slate-500 text-sm mb-4">Create a client organisation to start uploading batches.</p>
          <button onClick={() => setShowModal(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg font-medium">
            Add First Client
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {clients.map(c => (
            <div key={c.id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center text-lg font-bold text-blue-400 bg-blue-600/20 mb-3">
                {c.name[0].toUpperCase()}
              </div>
              <div className="font-semibold text-slate-200">{c.name}</div>
              <div className="text-xs text-slate-500 mt-0.5 font-mono">{c.code}</div>
              <div className="mt-2">
                <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                  c.status === "ACTIVE" ? "bg-green-900 text-green-300" : "bg-slate-700 text-slate-400"
                }`}>
                  {c.status ?? "ACTIVE"}
                </span>
              </div>
              {c.createdAt && (
                <div className="text-slate-600 text-[11px] mt-2">
                  Added {new Date(c.createdAt).toLocaleDateString()}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <ClientModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onSaved={load}
      />
    </div>
  );
}
