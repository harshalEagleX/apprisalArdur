"use client";
import { useEffect, useState } from "react";
import {
  User as UserIcon, Shield, Mail, KeyRound, Eye, EyeOff,
  Bell, CheckCircle2, AlertCircle, Loader2, Building2, Clock,
} from "lucide-react";
import { getProfile, updateProfile, changePassword, getPasswordPolicy, type UserProfile } from "@/lib/api";
import { Skeleton } from "@/components/shared/Skeleton";
import { toast } from "@/lib/toast";

// ── Labelled input ────────────────────────────────────────────────────────────
function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</span>
      <div className="text-sm text-slate-200">{value ?? <span className="text-slate-600">—</span>}</div>
    </div>
  );
}

// ── Text input ────────────────────────────────────────────────────────────────
function TextInput({
  label, value, onChange, type = "text", placeholder,
}: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-slate-300">{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-11 rounded-lg border border-white/10 bg-[#0B0F14] px-4 text-sm text-white placeholder-slate-600 transition focus:border-indigo-500/60 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
      />
    </div>
  );
}

// ── Password input with show/hide ─────────────────────────────────────────────
function PasswordInput({
  label, value, onChange, required,
}: {
  label: string; value: string; onChange: (v: string) => void; required?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-slate-300">{label}</label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          required={required}
          className="h-11 w-full rounded-lg border border-white/10 bg-[#0B0F14] pl-4 pr-12 text-sm text-white placeholder-slate-600 transition focus:border-indigo-500/60 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
        />
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          tabIndex={-1}
          className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 transition hover:text-slate-300"
          aria-label={show ? "Hide password" : "Show password"}
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
    </div>
  );
}

// ── Section card ──────────────────────────────────────────────────────────────
function Card({ title, icon: Icon, children }: {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-[#11161C]">
      <div className="flex items-center gap-3 border-b border-white/[0.07] px-6 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-[#0B0F14]">
          <Icon size={15} className="text-slate-400" />
        </div>
        <h2 className="text-sm font-semibold text-white">{title}</h2>
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}

// ── Primary button ────────────────────────────────────────────────────────────
function Btn({ loading, label, loadingLabel, icon: Icon }: {
  loading: boolean; label: string; loadingLabel: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="inline-flex h-11 items-center gap-2.5 rounded-lg bg-indigo-600 px-6 text-sm font-semibold text-white shadow-lg transition hover:bg-indigo-500 disabled:opacity-50"
    >
      {loading
        ? <><Loader2 size={15} className="animate-spin" /> {loadingLabel}</>
        : <><Icon size={15} /> {label}</>}
    </button>
  );
}

// ── Alert ─────────────────────────────────────────────────────────────────────
function Alert({ type, message }: { type: "success" | "error"; message: string }) {
  const styles = type === "success"
    ? "border-green-500/25 bg-green-950/30 text-green-300"
    : "border-red-500/25 bg-red-950/30 text-red-300";
  const Icon = type === "success" ? CheckCircle2 : AlertCircle;
  return (
    <div className={`flex items-center gap-2.5 rounded-lg border px-4 py-3 text-sm ${styles}`}>
      <Icon size={15} className="shrink-0" />
      <span>{message}</span>
    </div>
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
      toast.success("Profile saved");
    } catch (err) {
      toast.error("Save failed", err instanceof Error ? err.message : undefined);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={e => { void handleSubmit(e); }} className="space-y-5">
      <TextInput
        label="Full name"
        value={form.fullName}
        onChange={v => setForm(f => ({ ...f, fullName: v }))}
        placeholder="Your display name"
      />
      <TextInput
        label="Email address"
        value={form.email}
        onChange={v => setForm(f => ({ ...f, email: v }))}
        type="email"
        placeholder="you@example.com"
      />
      <div className="pt-1">
        <Btn loading={saving} label="Save changes" loadingLabel="Saving…" icon={UserIcon} />
      </div>
    </form>
  );
}

// ── Password form ─────────────────────────────────────────────────────────────
function PasswordForm({ minLength }: { minLength: number }) {
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFeedback(null);
    if (form.next !== form.confirm) {
      setFeedback({ type: "error", msg: "New passwords do not match" });
      return;
    }
    if (form.next.length < minLength) {
      setFeedback({ type: "error", msg: `Password must be at least ${minLength} characters` });
      return;
    }
    setSaving(true);
    try {
      await changePassword(form.current, form.next, form.confirm);
      setFeedback({ type: "success", msg: "Password changed successfully" });
      setForm({ current: "", next: "", confirm: "" });
    } catch (err) {
      setFeedback({ type: "error", msg: err instanceof Error ? err.message : "Change failed" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={e => { void handleSubmit(e); }} className="space-y-5">
      <p className="text-sm leading-relaxed text-slate-500">
        Use a strong password with at least {minLength} characters. Changing your password
        does not end your current session.
      </p>

      {feedback && <Alert type={feedback.type} message={feedback.msg} />}

      <PasswordInput
        label="Current password"
        value={form.current}
        onChange={v => setForm(f => ({ ...f, current: v }))}
        required
      />
      <PasswordInput
        label="New password"
        value={form.next}
        onChange={v => setForm(f => ({ ...f, next: v }))}
        required
      />
      <PasswordInput
        label="Confirm new password"
        value={form.confirm}
        onChange={v => setForm(f => ({ ...f, confirm: v }))}
        required
      />
      <div className="pt-1">
        <Btn loading={saving} label="Change password" loadingLabel="Changing…" icon={KeyRound} />
      </div>
    </form>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [minPwLen, setMinPwLen] = useState(8);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getProfile(), getPasswordPolicy()])
      .then(([p, pol]) => { setProfile(p); setMinPwLen(pol.minLength ?? 8); })
      .catch(() => toast.error("Failed to load profile"))
      .finally(() => setLoading(false));
  }, []);

  const initial = profile
    ? (profile.fullName ?? profile.username ?? "?")[0]?.toUpperCase()
    : "?";

  const roleTone =
    profile?.role === "ADMIN"
      ? "border-violet-500/25 bg-violet-950/30 text-violet-300"
      : "border-slate-500/25 bg-slate-800/40 text-slate-300";

  return (
    <div className="min-h-screen w-full bg-[#0B0F14] px-4 py-10 md:px-8 lg:px-12">
      <div className="mx-auto max-w-2xl space-y-6">

        {/* ── Page header ─────────────────────────────────── */}
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Account</div>
          <h1 className="mt-1 text-2xl font-semibold text-white">My Profile</h1>
          <p className="mt-1.5 text-sm text-slate-500">
            Manage your account details, password, and notification preferences.
          </p>
        </div>

        {/* ── Identity card ───────────────────────────────── */}
        <div className="flex items-center gap-5 rounded-2xl border border-white/10 bg-[#11161C] px-6 py-5">
          {loading ? (
            <Skeleton className="h-16 w-16 rounded-full shrink-0" />
          ) : (
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-white/10 bg-[#161B22] text-2xl font-bold text-slate-200">
              {initial}
            </div>
          )}
          <div className="min-w-0 flex-1">
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-4 w-28" />
              </div>
            ) : (
              <>
                <div className="truncate text-base font-semibold text-white">
                  {profile?.fullName ?? profile?.username}
                </div>
                <div className="mt-0.5 text-sm text-slate-500">@{profile?.username}</div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {profile?.role && (
                    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${roleTone}`}>
                      <Shield size={10} /> {profile.role}
                    </span>
                  )}
                  {profile?.client && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-[#0B0F14] px-2 py-0.5 text-xs text-slate-400">
                      <Building2 size={10} /> {profile.client.name}
                    </span>
                  )}
                  {profile?.lastLoginAt && (
                    <span className="inline-flex items-center gap-1 text-xs text-slate-600">
                      <Clock size={10} />
                      Last login {new Date(profile.lastLoginAt).toLocaleString("en-GB", {
                        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* ── Account details (read-only) ─────────────────── */}
        {!loading && profile && (
          <Card title="Account details" icon={UserIcon}>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Field label="Username"    value={profile.username} />
              <Field label="Email"       value={profile.email
                ? <span className="flex items-center gap-1.5"><Mail size={13} className="shrink-0 text-slate-500" />{profile.email}</span>
                : null}
              />
              <Field label="Role"        value={
                <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${roleTone}`}>
                  <Shield size={10} /> {profile.role}
                </span>}
              />
              <Field label="Status"      value={
                <span className={`text-sm font-medium ${profile.active ? "text-green-400" : "text-red-400"}`}>
                  {profile.active ? "Active" : "Inactive"}
                </span>}
              />
              <Field label="Member since" value={profile.createdAt
                ? new Date(profile.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
                : null}
              />
              <Field label="Client"      value={profile.client?.name} />
            </div>
          </Card>
        )}
        {loading && (
          <Card title="Account details" icon={UserIcon}>
            <div className="grid grid-cols-2 gap-5">
              {[1,2,3,4,5,6].map(i => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          </Card>
        )}

        {/* ── Edit profile ────────────────────────────────── */}
        <Card title="Edit profile" icon={UserIcon}>
          {loading
            ? <div className="space-y-5">{[1,2].map(i => <Skeleton key={i} className="h-11 w-full" />)}</div>
            : profile ? <ProfileForm profile={profile} /> : null}
        </Card>

        {/* ── Security ────────────────────────────────────── */}
        <Card title="Security — change password" icon={KeyRound}>
          <PasswordForm minLength={minPwLen} />
        </Card>

        {/* ── Notification preferences ─────────────────────── */}
        <Card title="Notification preferences" icon={Bell}>
          <p className="mb-4 text-sm leading-relaxed text-slate-500">
            Choose which events you want to be notified about in the bell menu.
          </p>
          <div className="space-y-3">
            {[
              { key: "qc_complete",  label: "QC completed",        sub: "When a batch finishes QC processing" },
              { key: "review_notif", label: "Review notifications", sub: "When a reviewer submits a report" },
              { key: "rerun_notif",  label: "Re-QC updates",        sub: "When a single-file re-QC completes" },
            ].map(item => (
              <label
                key={item.key}
                className="flex cursor-pointer items-start gap-4 rounded-xl border border-white/[0.06] bg-[#0B0F14] px-4 py-3.5 transition-colors hover:border-white/10 hover:bg-[#0d1218]"
              >
                <input
                  type="checkbox"
                  defaultChecked
                  className="mt-0.5 h-4 w-4 rounded border-white/20 bg-[#11161C] accent-indigo-500 cursor-pointer"
                />
                <div>
                  <div className="text-sm font-medium text-slate-200">{item.label}</div>
                  <div className="mt-0.5 text-xs text-slate-500">{item.sub}</div>
                </div>
              </label>
            ))}
          </div>
        </Card>

      </div>
    </div>
  );
}
