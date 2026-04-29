"use client";
import { useEffect, useState, useCallback } from "react";
import { getUsers, deleteUser, type User } from "@/lib/api";
import UserModal from "@/components/admin/UserModal";
import ConfirmDialog from "@/components/shared/ConfirmDialog";

export default function UsersPage() {
  const [users, setUsers]       = useState<User[]>([]);
  const [page, setPage]         = useState(0);
  const [totalPages, setTotal]  = useState(1);
  const [loading, setLoading]   = useState(true);
  const [editUser, setEditUser] = useState<User | null | undefined>(undefined);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getUsers(page);
      setUsers(res.content);
      setTotal(res.totalPages);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { load(); }, [load]);

  async function handleDelete() {
    if (!deleteTarget) return;
    try { await deleteUser(deleteTarget.id); setDeleteTarget(null); await load(); }
    catch (e) { alert("Delete failed: " + String(e)); }
  }

  const ROLE_BADGE: Record<string, string> = {
    ADMIN:    "bg-purple-900 text-purple-300",
    REVIEWER: "bg-amber-900 text-amber-300",
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">User Management</h1>
        <button onClick={() => setEditUser(null)}
          className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg font-medium transition-colors">
          + Add User
        </button>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-800 text-slate-400 text-xs uppercase">
            <tr>
              {["User", "Role", "Client Org", "Created", "Actions"].map(h => (
                <th key={h} className="px-4 py-3 text-left">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">Loading…</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-500">No users found</td></tr>
            ) : users.map(u => (
              <tr key={u.id} className="hover:bg-slate-800/30">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-200">{u.fullName ?? u.username}</div>
                  <div className="text-xs text-slate-500">{u.username}</div>
                  {u.email && <div className="text-xs text-slate-600">{u.email}</div>}
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${ROLE_BADGE[u.role] ?? "bg-slate-700 text-slate-300"}`}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs">{u.client?.name ?? "—"}</td>
                <td className="px-4 py-3 text-slate-500 text-xs">
                  {u.createdAt ? new Date(u.createdAt).toLocaleDateString() : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button onClick={() => setEditUser(u)}
                      className="text-blue-400 hover:text-blue-300 text-xs hover:underline">
                      Edit
                    </button>
                    <button onClick={() => setDeleteTarget(u)}
                      className="text-red-400 hover:text-red-300 text-xs hover:underline">
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            className="text-slate-400 disabled:opacity-30 hover:text-white text-sm px-3 py-1.5 rounded-lg hover:bg-slate-800">
            ← Previous
          </button>
          <span className="text-slate-500 text-sm">Page {page + 1} of {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
            className="text-slate-400 disabled:opacity-30 hover:text-white text-sm px-3 py-1.5 rounded-lg hover:bg-slate-800">
            Next →
          </button>
        </div>
      )}

      <UserModal
        open={editUser !== undefined}
        user={editUser}
        onClose={() => setEditUser(undefined)}
        onSaved={load}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete User"
        message={`Delete user "${deleteTarget?.username}"? This cannot be undone.`}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
