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
  ADMIN:    "bg-slate-950/40 border-slate-500/25 text-slate-200",
  REVIEWER: "bg-green-950/35 border-green-500/25 text-green-200",
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
    <div className="max-w-[1200px] p-6">
      <div data-guide="admin-users-header" className="flex flex-col gap-4 mb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Access control</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-white">Users</h1>
          <p className="mt-1 text-sm text-slate-500">Admins and reviewers with access to this platform.</p>
        </div>
        <button
          onClick={() => setEditUser(null)}
          className="flex h-9 items-center gap-1.5 rounded-md border border-slate-400/30 bg-slate-600 px-4 text-sm font-semibold text-white shadow-[0_0_22px_rgba(226,232,240,0.16)] transition-colors hover:bg-slate-500"
        >
          <Plus size={14} /> New user
        </button>
      </div>

      <div data-guide="admin-users-search" className="mb-4 grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-center">
        <div className="relative max-w-sm">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by name, username, or email…"
            className="h-9 w-full rounded-md border border-white/10 bg-[#11161C] pl-8 pr-9 text-sm text-white placeholder-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.04] hover:text-slate-300"
              aria-label="Clear search"
              title="Clear search"
            >
              <XCircle size={13} />
            </button>
          )}
        </div>
        <RoleSummary icon={ShieldCheck} label="Admins" value={roleCounts.admins} tone="blue" />
        <RoleSummary icon={ClipboardCheck} label="Reviewers" value={roleCounts.reviewers} tone="green" />
      </div>

      {/* Table */}
      <div data-guide="admin-users-table" className="overflow-hidden rounded-lg border border-white/10 bg-[#11161C] shadow-[0_16px_40px_rgba(0,0,0,0.2)]">
        <div className="data-scroll">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-white/10 bg-[#0B0F14]/80">
              {["User", "Role", "Client org", "Added", ""].map(h => (
                <th key={h} className={`sticky top-0 z-10 bg-[#0B0F14] px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500 ${!h ? "w-24 text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {loading ? (
              <tr><td colSpan={5} className="p-0"><TableSkeleton rows={6} cols={5} /></td></tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon={UsersIcon} title={search ? "No users match your search" : "No users yet"}
                    description={!search ? "Add an admin or reviewer to get started." : undefined}
                    action={!search ? (
                      <button onClick={() => setEditUser(null)}
                        className="text-sm text-slate-400 hover:text-slate-300 flex items-center gap-1.5 transition-colors">
                        <Plus size={14} /> Add first user
                      </button>
                    ) : undefined}
                  />
                </td>
              </tr>
            ) : filtered.map(u => (
              <tr key={u.id} className="transition-colors hover:bg-white/[0.03]">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-200 text-sm">{u.fullName ?? u.username}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{u.username}{u.email ? ` · ${u.email}` : ""}</div>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center text-xs px-2 py-0.5 rounded-md border font-medium ${ROLE_STYLES[u.role] ?? "border-white/10 bg-[#161B22] text-slate-400"}`}>
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
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-slate-300"
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
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-30">
            <ChevronLeft size={14} /> Previous
          </button>
          <span className="text-xs text-slate-500">Page {page + 1} of {total}</span>
          <button onClick={() => setPage(p => Math.min(total - 1, p + 1))} disabled={page >= total - 1}
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-30">
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
        confirmationText={deleteTarget?.username}
        onConfirm={handleDelete} onCancel={() => setDelete(null)}
      />
    </div>
  );
}

function RoleSummary({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  tone: "blue" | "green";
}) {
  const styles = tone === "blue"
    ? "border-slate-500/25 bg-slate-950/30 text-slate-200"
    : "border-green-500/25 bg-green-950/30 text-green-200";
  return (
    <div className={`flex h-9 items-center gap-2 rounded-lg border px-3 ${styles}`}>
      <Icon size={14} className="opacity-80" />
      <span className="text-sm font-semibold tabular-nums">{value}</span>
      <span className="text-[11px] uppercase tracking-wide opacity-70">{label}</span>
    </div>
  );
}
