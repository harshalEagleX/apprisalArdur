"use client";
import { useEffect, useState } from "react";
import {
  User as UserIcon, Shield, Mail, KeyRound, Eye, EyeOff,
  Bell, CheckCircle2, AlertCircle, Loader2, Building2, Clock, ToggleRight,
} from "lucide-react";
import { getProfile, updateProfile, changePassword, getPasswordPolicy, type UserProfile } from "@/lib/api";
import { Skeleton } from "@/components/shared/Skeleton";
import { toast } from "@/lib/toast";

// ── Password input with show/hide ─────────────────────────────────────────────
function PasswordInput({ label, value, onChange, required }: {
  label: string; value: string; onChange: (v: string) => void; required?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-slate-300">{label}</label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          required={required}
          className="h-10 w-full rounded-lg border border-white/10 bg-[#0B0F14]/70 pl-3.5 pr-10 text-sm text-white placeholder-slate-600 transition focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
        />
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          tabIndex={-1}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 transition hover:text-slate-300"
        >
          {show ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>
    </div>
  );
}

function Card({ title, icon: Icon, children }: {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]">
      <div className="flex items-center gap-3 border-b border-white/[0.07] px-5 py-3.5">
        <Icon size={15} className="shrink-0 text-slate-400" />
        <h2 className="text-sm font-semibold text-white">{title}</h2>
      </div>
      <div className="px-5 py-5">{children}</div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/[0.05] py-3 last:border-0">
      <span className="text-[12px] font-medium uppercase tracking-wider text-slate-500 shrink-0">{label}</span>
      <span className="text-right text-sm text-slate-200">{value ?? <span className="text-slate-600">—</span>}</span>
    </div>
  );
}

function PrimaryBtn({ loading, label, loadingLabel }: {
  loading: boolean; label: string; loadingLabel: string;
}) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-400/25 bg-slate-700 px-5 text-sm font-semibold text-white transition hover:bg-slate-600 disabled:opacity-50"
    >
      {loading && <Loader2 size={13} className="animate-spin" />}
      {loading ? loadingLabel : label}
    </button>
  );
}

export default function ReviewerProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [minPwLen, setMinPwLen] = useState(8);
  const [loading, setLoading] = useState(true);
  const [editForm, setEditForm] = useState({ fullName: "", email: "" });
  const [editSaving, setEditSaving] = useState(false);
  const [pwForm, setPwForm] = useState({ current: "", next: "", confirm: "" });
  const [pwSaving, setPwSaving] = useState(false);
  const [pwFeedback, setPwFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    Promise.all([getProfile(), getPasswordPolicy()])
      .then(([p, pol]) => {
        setProfile(p);
        setMinPwLen(pol.minLength ?? 8);
        setEditForm({ fullName: p.fullName ?? "", email: p.email ?? "" });
      })
      .catch(() => toast.error("Failed to load profile"))
      .finally(() => setLoading(false));
  }, []);

  async function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    setEditSaving(true);
    try {
      await updateProfile({ fullName: editForm.fullName || undefined, email: editForm.email || undefined });
      toast.success("Profile saved");
    } catch (err) {
      toast.error("Save failed", err instanceof Error ? err.message : undefined);
    } finally {
      setEditSaving(false);
    }
  }

  async function handlePwSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPwFeedback(null);
    if (pwForm.next !== pwForm.confirm) { setPwFeedback({ type: "error", msg: "New passwords do not match" }); return; }
    if (pwForm.next.length < minPwLen) { setPwFeedback({ type: "error", msg: `Password must be at least ${minPwLen} characters` }); return; }
    setPwSaving(true);
    try {
      await changePassword(pwForm.current, pwForm.next, pwForm.confirm);
      setPwFeedback({ type: "success", msg: "Password changed successfully" });
      setPwForm({ current: "", next: "", confirm: "" });
    } catch (err) {
      setPwFeedback({ type: "error", msg: err instanceof Error ? err.message : "Change failed" });
    } finally {
      setPwSaving(false);
    }
  }

  const initial = profile ? (profile.fullName ?? profile.username ?? "?")[0]?.toUpperCase() : "?";
  const roleTone = "border-slate-500/25 bg-slate-800/40 text-slate-300";

  return (
    <div className="w-full max-w-[1200px] mx-auto p-6 lg:p-8">
      <div className="mb-6">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Account</div>
        <h1 className="mt-1 text-2xl font-semibold text-white">My Profile</h1>
        <p className="mt-1 text-sm text-slate-500">Manage your account details, password, and notification preferences.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: identity */}
        <div className="space-y-5 lg:col-span-1">
          <div className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]">
            <div className="flex flex-col items-center px-6 py-8 text-center">
              {loading ? <Skeleton className="h-20 w-20 rounded-full" /> : (
                <div className="flex h-20 w-20 items-center justify-center rounded-full border border-white/10 bg-[#161B22] text-3xl font-bold text-slate-200">
                  {initial}
                </div>
              )}
              {loading ? (
                <div className="mt-4 space-y-2"><Skeleton className="mx-auto h-5 w-36" /><Skeleton className="mx-auto h-4 w-48" /></div>
              ) : (
                <>
                  <div className="mt-4 text-base font-semibold text-white">{profile?.fullName ?? profile?.username}</div>
                  <div className="mt-0.5 text-sm text-slate-500">{profile?.username}</div>
                  <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
                    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${roleTone}`}>
                      <Shield size={10} /> {profile?.role ?? "REVIEWER"}
                    </span>
                    {profile?.active !== undefined && (
                      <span className={`text-xs font-medium ${profile.active ? "text-green-400" : "text-red-400"}`}>
                        {profile.active ? "Active" : "Inactive"}
                      </span>
                    )}
                  </div>
                  {profile?.client && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
                      <Building2 size={11} /> {profile.client.name}
                    </div>
                  )}
                  {profile?.lastLoginAt && (
                    <div className="mt-1.5 flex items-center gap-1 text-xs text-slate-600">
                      <Clock size={10} />
                      Last login {new Date(profile.lastLoginAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          <Card title="Account details" icon={UserIcon}>
            {loading ? (
              <div className="space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-10 w-full" />)}</div>
            ) : (
              <>
                <InfoRow label="Username" value={profile?.username} />
                <InfoRow label="Email" value={profile?.email
                  ? <span className="flex items-center justify-end gap-1.5"><Mail size={12} className="shrink-0 text-slate-500" />{profile.email}</span>
                  : null} />
                <InfoRow label="Role" value={
                  <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${roleTone}`}>
                    <Shield size={9} /> {profile?.role}
                  </span>} />
                <InfoRow label="Member since" value={profile?.createdAt
                  ? new Date(profile.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
                  : null} />
              </>
            )}
          </Card>
        </div>

        {/* Right: editable */}
        <div className="space-y-6 lg:col-span-2">
          <Card title="Edit profile" icon={UserIcon}>
            {loading ? (
              <div className="space-y-4"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
            ) : (
              <form onSubmit={e => { void handleEditSubmit(e); }} className="space-y-5">
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-300">Full name</label>
                    <input type="text" value={editForm.fullName} onChange={e => setEditForm(f => ({ ...f, fullName: e.target.value }))}
                      placeholder="Your display name"
                      className="h-10 w-full rounded-lg border border-white/10 bg-[#0B0F14]/70 px-3.5 text-sm text-white placeholder-slate-600 transition focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30" />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-300">Email address</label>
                    <input type="email" value={editForm.email} onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))}
                      placeholder="you@example.com"
                      className="h-10 w-full rounded-lg border border-white/10 bg-[#0B0F14]/70 px-3.5 text-sm text-white placeholder-slate-600 transition focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30" />
                  </div>
                </div>
                <PrimaryBtn loading={editSaving} label="Save changes" loadingLabel="Saving…" />
              </form>
            )}
          </Card>

          <Card title="Security — change password" icon={KeyRound}>
            <form onSubmit={e => { void handlePwSubmit(e); }} className="space-y-5">
              <p className="text-sm text-slate-500">Use a strong password of at least {minPwLen} characters. Your session will not be terminated after a change.</p>
              {pwFeedback && (
                <div className={`flex items-center gap-2.5 rounded-lg border px-4 py-3 text-sm ${
                  pwFeedback.type === "success" ? "border-green-500/25 bg-green-950/30 text-green-300" : "border-red-500/25 bg-red-950/30 text-red-300"
                }`}>
                  {pwFeedback.type === "success" ? <CheckCircle2 size={14} className="shrink-0" /> : <AlertCircle size={14} className="shrink-0" />}
                  {pwFeedback.msg}
                </div>
              )}
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
                <PasswordInput label="Current password" value={pwForm.current} onChange={v => setPwForm(f => ({ ...f, current: v }))} required />
                <PasswordInput label="New password" value={pwForm.next} onChange={v => setPwForm(f => ({ ...f, next: v }))} required />
                <PasswordInput label="Confirm new password" value={pwForm.confirm} onChange={v => setPwForm(f => ({ ...f, confirm: v }))} required />
              </div>
              <PrimaryBtn loading={pwSaving} label="Change password" loadingLabel="Changing…" />
            </form>
          </Card>

          <Card title="Notification preferences" icon={Bell}>
            <p className="mb-5 text-sm text-slate-500">Choose which events generate notifications in the bell menu.</p>
            <div className="space-y-3">
              {[
                { key: "assigned",  label: "Batch assigned to me",    sub: "When admin assigns a batch for your review" },
                { key: "override",  label: "Override decisions",       sub: "When admin approves or rejects your override request" },
                { key: "reassign",  label: "Re-review notifications",  sub: "When a batch is re-assigned or updated" },
              ].map(item => (
                <label key={item.key} className="flex cursor-pointer items-center gap-4 rounded-lg border border-white/[0.06] bg-[#0B0F14]/50 px-4 py-3.5 transition hover:border-white/10">
                  <input type="checkbox" defaultChecked className="h-4 w-4 rounded border-white/20 bg-[#11161C] accent-indigo-500" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-200">{item.label}</div>
                    <div className="mt-0.5 text-xs text-slate-500">{item.sub}</div>
                  </div>
                  <ToggleRight size={16} className="shrink-0 text-slate-600" />
                </label>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
