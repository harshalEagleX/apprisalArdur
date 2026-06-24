"use client";
import { useEffect, useState } from "react";
import {
  User as UserIcon, Shield, Mail, KeyRound,
  Bell, CheckCircle2, AlertCircle, Loader2, Eye, EyeOff,
} from "lucide-react";
import { getProfile, updateProfile, changePassword, getPasswordPolicy, type UserProfile } from "@/lib/api";
import { Skeleton } from "@/components/shared/Skeleton";
import { toast } from "@/lib/toast";

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-[#11161C] overflow-hidden">
      <div className="border-b border-white/10 px-5 py-3">
        <h2 className="text-sm font-semibold text-white">{title}</h2>
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

// ── Field row ─────────────────────────────────────────────────────────────────
function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-white/[0.05] last:border-0">
      <span className="text-[12px] text-slate-500 min-w-[120px] shrink-0">{label}</span>
      <span className="text-[13px] text-slate-200 text-right">{value ?? <span className="text-slate-600">—</span>}</span>
    </div>
  );
}

// ── Password field with show/hide toggle ─────────────────────────────────────
function PasswordInput({
  value, onChange, label, required,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  required?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label className="mb-1 block text-[11px] uppercase tracking-wide text-slate-500">{label}</label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          required={required}
          className="h-9 w-full rounded-md border border-white/10 bg-[#0B0F14]/70 pl-3 pr-9 text-sm text-white placeholder-slate-600 focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
        />
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          tabIndex={-1}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
          aria-label={show ? "Hide password" : "Show password"}
        >
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
    </div>
  );
}

// ── Password form ─────────────────────────────────────────────────────────────
function PasswordForm({ minLength }: { minLength: number }) {
  const [form, setForm] = useState({ currentPassword: "", newPassword: "", confirmPassword: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setSuccess(false);
    if (form.newPassword !== form.confirmPassword) { setError("New passwords do not match"); return; }
    if (form.newPassword.length < minLength) { setError(`Password must be at least ${minLength} characters`); return; }
    setSaving(true);
    try {
      await changePassword(form.currentPassword, form.newPassword, form.confirmPassword);
      setSuccess(true);
      setForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
      toast.success("Password changed successfully");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password change failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={e => { void handleSubmit(e); }} className="space-y-4">
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/25 bg-red-950/20 px-3 py-2 text-[12px] text-red-300">
          <AlertCircle size={13} className="shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 rounded-lg border border-green-500/25 bg-green-950/20 px-3 py-2 text-[12px] text-green-300">
          <CheckCircle2 size={13} className="shrink-0" /> Password changed successfully
        </div>
      )}
      <PasswordInput
        label="Current password"
        value={form.currentPassword}
        onChange={v => setForm(f => ({ ...f, currentPassword: v }))}
        required
      />
      <PasswordInput
        label="New password"
        value={form.newPassword}
        onChange={v => setForm(f => ({ ...f, newPassword: v }))}
        required
      />
      <PasswordInput
        label="Confirm new password"
        value={form.confirmPassword}
        onChange={v => setForm(f => ({ ...f, confirmPassword: v }))}
        required
      />
      <button
        type="submit"
        disabled={saving}
        className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-400/25 bg-slate-700 px-4 text-sm font-medium text-white transition-colors hover:bg-slate-600 disabled:opacity-40"
      >
        {saving ? <Loader2 size={13} className="animate-spin" /> : <KeyRound size={13} />}
        {saving ? "Changing…" : "Change password"}
      </button>
    </form>
  );
}

// ── Profile form ──────────────────────────────────────────────────────────────
function ProfileForm({ profile }: { profile: UserProfile }) {
  const [form, setForm] = useState({ fullName: profile.fullName ?? "", email: profile.email ?? "" });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await updateProfile({ fullName: form.fullName || undefined, email: form.email || undefined });
      toast.success("Profile updated");
    } catch (err) {
      toast.error("Update failed", err instanceof Error ? err.message : undefined);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={e => { void handleSubmit(e); }} className="space-y-4">
      <div>
        <label className="mb-1 block text-[11px] uppercase tracking-wide text-slate-500">Full name</label>
        <input
          type="text"
          value={form.fullName}
          onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))}
          placeholder="Your display name"
          className="h-9 w-full rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-white placeholder-slate-600 focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
        />
      </div>
      <div>
        <label className="mb-1 block text-[11px] uppercase tracking-wide text-slate-500">Email</label>
        <input
          type="email"
          value={form.email}
          onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
          placeholder="you@example.com"
          className="h-9 w-full rounded-md border border-white/10 bg-[#0B0F14]/70 px-3 text-sm text-white placeholder-slate-600 focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
        />
      </div>
      <button
        type="submit"
        disabled={saving}
        className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-400/25 bg-slate-700 px-4 text-sm font-medium text-white transition-colors hover:bg-slate-600 disabled:opacity-40"
      >
        {saving ? <Loader2 size={13} className="animate-spin" /> : <UserIcon size={13} />}
        {saving ? "Saving…" : "Save profile"}
      </button>
    </form>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const [profile, setProfile]   = useState<UserProfile | null>(null);
  const [minPwLen, setMinPwLen] = useState(8);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    Promise.all([getProfile(), getPasswordPolicy()])
      .then(([p, pol]) => { setProfile(p); setMinPwLen(pol.minLength ?? 8); })
      .catch(() => toast.error("Failed to load profile"))
      .finally(() => setLoading(false));
  }, []);

  const roleBadge = (role: string) => (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
      role === "ADMIN"
        ? "border border-violet-500/25 bg-violet-950/40 text-violet-300"
        : "border border-slate-500/25 bg-slate-800/40 text-slate-300"
    }`}>
      <Shield size={9} /> {role}
    </span>
  );

  return (
    <div className="w-full max-w-[900px] p-6 lg:p-8">
      {/* Header */}
      <div className="mb-6">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Account</div>
        <h1 className="mt-1 text-2xl font-semibold text-white">My Profile</h1>
        <p className="mt-1 text-sm text-slate-500">Manage your account details, security, and notification preferences.</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Left: avatar + account summary */}
        <div className="lg:col-span-1">
          <div className="rounded-xl border border-white/10 bg-[#11161C] p-5 text-center">
            {loading ? (
              <Skeleton className="mx-auto mb-3 h-16 w-16 rounded-full" />
            ) : (
              <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full border border-white/10 bg-[#161B22] text-2xl font-semibold text-slate-300">
                {(profile?.fullName ?? profile?.username ?? "?")[0]?.toUpperCase()}
              </div>
            )}
            {loading ? (
              <Skeleton className="mx-auto h-5 w-32" />
            ) : (
              <>
                <div className="text-sm font-semibold text-white">{profile?.fullName ?? profile?.username}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">@{profile?.username}</div>
                {profile?.role && <div className="mt-2">{roleBadge(profile.role)}</div>}
              </>
            )}
          </div>

          {/* Account info */}
          <div className="mt-4 rounded-xl border border-white/10 bg-[#11161C] overflow-hidden">
            <div className="border-b border-white/10 px-5 py-3">
              <h2 className="text-sm font-semibold text-white">Account info</h2>
            </div>
            <div className="px-5 py-4">
              {loading ? (
                <div className="space-y-2">
                  {[1,2,3].map(i => <Skeleton key={i} className="h-5 w-full" />)}
                </div>
              ) : (
                <>
                  <Field label="Username"   value={profile?.username} />
                  <Field label="Email"      value={profile?.email ? (
                    <span className="flex items-center gap-1"><Mail size={11} className="text-slate-500" />{profile.email}</span>
                  ) : null} />
                  <Field label="Role"       value={profile?.role ? roleBadge(profile.role) : null} />
                  <Field label="Client"     value={profile?.client?.name} />
                  <Field label="Status"     value={
                    <span className={`text-[11px] ${profile?.active ? "text-green-300" : "text-red-300"}`}>
                      {profile?.active ? "Active" : "Inactive"}
                    </span>
                  } />
                  <Field label="Last login" value={profile?.lastLoginAt
                    ? new Date(profile.lastLoginAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
                    : null} />
                  <Field label="Member since" value={profile?.createdAt
                    ? new Date(profile.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
                    : null} />
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right: edit sections */}
        <div className="lg:col-span-2 space-y-5">
          {/* My profile */}
          <Section title="My Profile">
            {loading ? (
              <div className="space-y-3">
                {[1,2].map(i => <Skeleton key={i} className="h-9 w-full" />)}
              </div>
            ) : profile ? (
              <ProfileForm profile={profile} />
            ) : null}
          </Section>

          {/* Security */}
          <Section title="Security">
            <p className="mb-4 text-[12px] text-slate-500">
              Use a strong, unique password of at least {minPwLen} characters.
              Your session will not be terminated after a password change.
            </p>
            <PasswordForm minLength={minPwLen} />
          </Section>

          {/* Preferences */}
          <Section title="Preferences">
            <p className="mb-3 text-[12px] text-slate-500">
              Choose which events generate in-app notifications for your account.
            </p>
            <div className="space-y-2">
              {[
                { label: "QC completed",       sub: "When batch QC finishes running" },
                { label: "Review notifications", sub: "When reviewer submits a report" },
                { label: "Re-QC updates",       sub: "When a single-file re-QC completes" },
              ].map(p => (
                <label key={p.label} className="flex cursor-pointer items-start gap-3 rounded-lg border border-white/[0.06] bg-[#0B0F14] px-4 py-3 transition-colors hover:border-white/10">
                  <Bell size={14} className="mt-0.5 shrink-0 text-slate-500" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] text-slate-200">{p.label}</div>
                    <div className="text-[11px] text-slate-600">{p.sub}</div>
                  </div>
                  <input type="checkbox" defaultChecked className="mt-0.5 h-4 w-4 rounded border-white/20 bg-[#11161C] accent-indigo-500 cursor-pointer" />
                </label>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-slate-600">Notification preferences are stored locally and will be respected once the notification system is fully active.</p>
          </Section>
        </div>
      </div>
    </div>
  );
}
