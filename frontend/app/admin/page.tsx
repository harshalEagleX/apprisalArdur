"use client";
import { useEffect, useState } from "react";
import { getAdminDashboard, getAdminBatches, getUsers, getClients, processQC, assignReviewer,
         deleteBatch, createUser, createClient, type Batch, type User, type Client } from "@/lib/api";

type Tab = "overview" | "batches" | "users" | "clients";

export default function AdminPage() {
  const [tab, setTab]         = useState<Tab>("overview");
  const [dash, setDash]       = useState<Record<string, unknown>>({});
  const [batches, setBatches] = useState<Batch[]>([]);
  const [users, setUsers]     = useState<User[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [reviewers, setReviewers] = useState<User[]>([]);

  useEffect(() => {
    getAdminDashboard().then(setDash).catch(console.error);
    getAdminBatches().then(p => setBatches(p.content)).catch(console.error);
    getUsers().then(p => { setUsers(p.content); setReviewers(p.content.filter(u => u.role === "REVIEWER")); }).catch(console.error);
    getClients().then(setClients).catch(console.error);
  }, []);

  const num = (k: string) => Number(dash[k] ?? 0);

  return (
    <div className="min-h-screen bg-slate-950 text-white flex">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-4 flex items-center gap-2 border-b border-slate-800">
          <div className="w-8 h-8 bg-blue-600 rounded font-bold text-sm flex items-center justify-center">A</div>
          <span className="font-semibold text-sm">Ardur Admin</span>
        </div>
        <nav className="p-2 flex-1 space-y-1">
          {(["overview","batches","users","clients"] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm capitalize transition-colors ${
                tab === t ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white hover:bg-slate-800"
              }`}>
              {t === "overview" ? "📊 Overview" : t === "batches" ? "📦 Batches" :
               t === "users" ? "👥 Users" : "🏢 Clients"}
            </button>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-800">
          <a href="/login" className="text-slate-400 hover:text-white text-xs">Sign out</a>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto p-6">
        {tab === "overview" && (
          <div>
            <h1 className="text-xl font-bold mb-6">Dashboard Overview</h1>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              {[
                { label: "Total Users",     val: num("totalUsers"),      color: "text-blue-400" },
                { label: "Client Orgs",     val: num("clientOrganizations"), color: "text-purple-400" },
                { label: "Total Batches",   val: num("totalBatches"),    color: "text-cyan-400" },
                { label: "Completed",       val: num("completed"),       color: "text-green-400" },
                { label: "Pending OCR",     val: num("pendingOcr"),      color: "text-amber-400" },
                { label: "In Review",       val: num("inReview"),        color: "text-orange-400" },
                { label: "Errors",          val: num("errors"),          color: "text-red-400" },
                { label: "Reviewers",       val: num("reviewerCount"),   color: "text-indigo-400" },
              ].map(s => (
                <div key={s.label} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                  <div className={`text-2xl font-bold ${s.color}`}>{s.val}</div>
                  <div className="text-slate-400 text-sm mt-1">{s.label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "batches" && (
          <div>
            <h1 className="text-xl font-bold mb-4">Batch Management</h1>
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-800 text-slate-400 text-xs uppercase">
                  <tr>{["Batch ID","Client","Status","Files","Reviewer","Actions"].map(h => (
                    <th key={h} className="px-4 py-3 text-left">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {batches.map(b => (
                    <tr key={b.id} className="hover:bg-slate-800/40">
                      <td className="px-4 py-3 font-mono text-xs">{b.parentBatchId}</td>
                      <td className="px-4 py-3 text-slate-300">{b.client?.name ?? "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          b.status === "COMPLETED" ? "bg-green-900 text-green-300" :
                          b.status.includes("ERROR") ? "bg-red-900 text-red-300" :
                          b.status.includes("REVIEW") ? "bg-amber-900 text-amber-300" :
                          "bg-blue-900 text-blue-300"
                        }`}>{b.status}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{b.files?.length ?? 0}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {b.assignedReviewer?.username ?? "Unassigned"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1.5">
                          {(b.status === "OCR_PENDING" || b.status === "OCR_COMPLETED") && (
                            <button onClick={() => processQC(b.id).then(() => window.location.reload())}
                              className="bg-blue-600 hover:bg-blue-700 text-white text-xs px-2 py-1 rounded">
                              QC
                            </button>
                          )}
                          {(b.status === "QC_COMPLETED" || b.status === "REVIEW_PENDING") && reviewers.length > 0 && (
                            <select
                              defaultValue=""
                              onChange={e => e.target.value && assignReviewer(b.id, Number(e.target.value)).then(() => window.location.reload())}
                              className="bg-slate-700 text-white text-xs px-2 py-1 rounded border-none focus:outline-none"
                            >
                              <option value="">Assign…</option>
                              {reviewers.map(r => <option key={r.id} value={r.id}>{r.username}</option>)}
                            </select>
                          )}
                          <button onClick={() => deleteBatch(b.id).then(() => window.location.reload())}
                            className="bg-red-900/50 hover:bg-red-800 text-red-300 text-xs px-2 py-1 rounded">
                            Del
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "users" && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h1 className="text-xl font-bold">User Management</h1>
              <button
                onClick={() => {
                  const u = prompt("Username:"); const p = prompt("Password:");
                  const r = prompt("Role (ADMIN/REVIEWER/CLIENT):");
                  if (u && p && r) createUser({ username: u, password: p, role: r as "ADMIN" | "REVIEWER" | "CLIENT" })
                    .then(() => window.location.reload());
                }}
                className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg">
                + Add User
              </button>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-800 text-slate-400 text-xs uppercase">
                  <tr>{["User","Role","Client","Created"].map(h => (
                    <th key={h} className="px-4 py-3 text-left">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {users.map(u => (
                    <tr key={u.id} className="hover:bg-slate-800/40">
                      <td className="px-4 py-3">
                        <div className="font-medium">{u.fullName ?? u.username}</div>
                        <div className="text-xs text-slate-400">{u.username}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          u.role === "ADMIN" ? "bg-purple-900 text-purple-300" :
                          u.role === "REVIEWER" ? "bg-amber-900 text-amber-300" : "bg-green-900 text-green-300"
                        }`}>{u.role}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{u.client?.name ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {u.createdAt ? new Date(u.createdAt).toLocaleDateString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "clients" && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h1 className="text-xl font-bold">Client Organizations</h1>
              <button
                onClick={() => {
                  const n = prompt("Organization name:"); const c = prompt("Code (e.g. ACME):");
                  if (n && c) createClient(n, c).then(() => window.location.reload());
                }}
                className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg">
                + Add Client
              </button>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              {clients.map(c => (
                <div key={c.id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                  <div className="w-10 h-10 bg-blue-600/30 rounded-lg flex items-center justify-center text-lg font-bold text-blue-400 mb-3">
                    {c.name[0].toUpperCase()}
                  </div>
                  <div className="font-semibold">{c.name}</div>
                  <div className="text-xs text-slate-400 mt-1">Code: {c.code}</div>
                  <span className={`text-xs mt-2 inline-block px-2 py-0.5 rounded ${
                    c.status === "ACTIVE" ? "bg-green-900 text-green-300" : "bg-slate-700 text-slate-400"
                  }`}>{c.status}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
