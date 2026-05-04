"use client";
import { useEffect, useState, useCallback } from "react";
import {
  Search, Plus, Users as UsersIcon, ChevronLeft, ChevronRight,
  ShieldCheck, ClipboardCheck, Pencil, Trash2, XCircle,
} from "lucide-react";
import type { ComponentType } from "react";
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
  const roleCounts = {
    admins: users.filter(u => u.role === "ADMIN").length,
    reviewers: users.filter(u => u.role === "REVIEWER").length,
  };

  return (
    <div className="p-6 max-w-[1200px]">
      <div className="flex flex-col gap-4 mb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Users</h1>
          <p className="text-slate-500 text-sm mt-0.5">Admins and reviewers with access to this platform</p>
        </div>
        <button
          onClick={() => setEditUser(null)}
          className="h-9 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm flex items-center gap-1.5 font-medium transition-colors"
        >
          <Plus size={14} /> New user
        </button>
      </div>

      <div className="mb-4 grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-center">
        <div className="relative max-w-sm">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by name, username, or email…"
            className="w-full h-9 bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-9 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-slate-300"
              aria-label="Clear search"
              title="Clear search"
            >
              <XCircle size={13} />
            </button>
          )}
        </div>
        <RoleSummary icon={ShieldCheck} label="Admins" value={roleCounts.admins} tone="purple" />
        <RoleSummary icon={ClipboardCheck} label="Reviewers" value={roleCounts.reviewers} tone="blue" />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
        <div className="data-scroll">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-950/40">
              {["User", "Role", "Client org", "Added", ""].map(h => (
                <th key={h} className={`sticky top-0 z-10 bg-slate-950 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 ${!h ? "w-24 text-right" : ""}`}>{h}</th>
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
              <tr key={u.id} className="hover:bg-slate-800/30 transition-colors">
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
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => setEditUser(u)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-800 hover:text-blue-300"
                      aria-label={`Edit ${u.username}`}
                      title="Edit user"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => setDelete(u)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-red-950/40 hover:text-red-300"
                      aria-label={`Remove ${u.username}`}
                      title="Remove user"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
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

function RoleSummary({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  tone: "blue" | "purple";
}) {
  const styles = tone === "purple"
    ? "border-purple-900/50 bg-purple-950/30 text-purple-200"
    : "border-blue-900/50 bg-blue-950/30 text-blue-200";
  return (
    <div className={`flex h-9 items-center gap-2 rounded-lg border px-3 ${styles}`}>
      <Icon size={14} className="opacity-80" />
      <span className="text-sm font-semibold tabular-nums">{value}</span>
      <span className="text-[11px] uppercase tracking-wide opacity-70">{label}</span>
    </div>
  );
}
