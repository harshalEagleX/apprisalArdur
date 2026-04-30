"use client";
import { useEffect, useState, useCallback } from "react";
import { Search, Plus, Users as UsersIcon, ChevronLeft, ChevronRight } from "lucide-react";
import { getUsers, deleteUser, type User } from "@/lib/api";
import UserModal from "@/components/admin/UserModal";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { TableSkeleton } from "@/components/shared/Skeleton";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";

const ROLE_STYLES: Record<string, string> = {
  ADMIN:    "bg-purple-950/60 border-purple-800/50 text-purple-300",
  REVIEWER: "bg-blue-950/60   border-blue-800/50   text-blue-300",
};

export default function UsersPage() {
  const [users, setUsers]       = useState<User[]>([]);
  const [page, setPage]         = useState(0);
  const [total, setTotal]       = useState(1);
  const [search, setSearch]     = useState("");
  const [loading, setLoading]   = useState(true);
  const [editUser, setEditUser] = useState<User | null | undefined>(undefined);
  const [deleteTarget, setDelete] = useState<User | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getUsers(page);
      setUsers(res.content); setTotal(res.totalPages);
    } catch { toast.error("Failed to load users"); }
    finally { setLoading(false); }
  }, [page]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteUser(deleteTarget.id);
      toast.success(`User "${deleteTarget.username}" removed`);
      setDelete(null); load();
    } catch (e) { toast.error("Delete failed", String(e)); }
  }

  const filtered = search
    ? users.filter(u =>
        u.username.toLowerCase().includes(search.toLowerCase()) ||
        (u.fullName ?? "").toLowerCase().includes(search.toLowerCase()) ||
        (u.email ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : users;

  return (
    <div className="p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-lg font-semibold text-white">Users</h1>
          <p className="text-slate-500 text-sm mt-0.5">Admins and reviewers with access to this platform</p>
        </div>
        <button
          onClick={() => setEditUser(null)}
          className="h-9 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm flex items-center gap-1.5 font-medium transition-colors"
        >
          <Plus size={14} /> New user
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-4 max-w-xs">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search by name or username…"
          className="w-full h-9 bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
        />
      </div>

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              {["User", "Role", "Client org", "Added", ""].map(h => (
                <th key={h} className={`px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 ${!h ? "w-24" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {loading ? (
              <tr><td colSpan={5} className="p-0"><TableSkeleton rows={6} cols={5} /></td></tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon={UsersIcon} title={search ? "No users match your search" : "No users yet"}
                    description={!search ? "Add an admin or reviewer to get started." : undefined}
                    action={!search ? (
                      <button onClick={() => setEditUser(null)}
                        className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1.5 transition-colors">
                        <Plus size={14} /> Add first user
                      </button>
                    ) : undefined}
                  />
                </td>
              </tr>
            ) : filtered.map(u => (
              <tr key={u.id} className="hover:bg-slate-800/30 transition-colors group">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-200 text-sm">{u.fullName ?? u.username}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{u.username}{u.email ? ` · ${u.email}` : ""}</div>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center text-xs px-2 py-0.5 rounded-md border font-medium ${ROLE_STYLES[u.role] ?? "bg-slate-800 text-slate-400 border-slate-700"}`}>
                    {u.role === "ADMIN" ? "Admin" : "Reviewer"}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-slate-400">
                  {u.client?.name ?? <span className="text-slate-600">—</span>}
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">
                  {u.createdAt ? new Date(u.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => setEditUser(u)} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Edit</button>
                    <span className="text-slate-700">·</span>
                    <button onClick={() => setDelete(u)} className="text-xs text-red-400 hover:text-red-300 transition-colors">Remove</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {total > 1 && (
        <div className="flex items-center justify-between mt-4">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-slate-700 text-slate-400 disabled:opacity-30 hover:text-white hover:bg-slate-800 text-sm transition-colors">
            <ChevronLeft size={14} /> Previous
          </button>
          <span className="text-xs text-slate-500">Page {page + 1} of {total}</span>
          <button onClick={() => setPage(p => Math.min(total - 1, p + 1))} disabled={page >= total - 1}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-slate-700 text-slate-400 disabled:opacity-30 hover:text-white hover:bg-slate-800 text-sm transition-colors">
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}

      <UserModal open={editUser !== undefined} user={editUser} onClose={() => setEditUser(undefined)} onSaved={load} />
      <ConfirmDialog
        open={!!deleteTarget}
        title="Remove user"
        message={`Remove "${deleteTarget?.username}" from the platform? They will lose access immediately.`}
        confirmLabel="Remove" danger
        onConfirm={handleDelete} onCancel={() => setDelete(null)}
      />
    </div>
  );
}
