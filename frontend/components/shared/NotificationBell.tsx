"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bell, X, CheckCircle2, AlertTriangle, Info,
  CheckCheck, Layers,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import Link from "next/link";

export interface Notification {
  id: string;
  type: string;
  message: string;
  batchId?: number;
  parentBatchId?: string;
  status?: string;
  needsReview?: boolean;
  occurredAt: string;
  read: boolean;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function iconFor(type: string, status?: string) {
  if (type === "QC_COMPLETED") {
    if (status === "COMPLETED") return <CheckCircle2 size={15} className="text-green-400" />;
    if (status === "ERROR")     return <AlertTriangle size={15} className="text-red-400" />;
    return <Layers size={15} className="text-indigo-400" />;
  }
  if (type === "RE_REVIEW_REQUESTED") return <AlertTriangle size={15} className="text-amber-400" />;
  return <Info size={15} className="text-slate-400" />;
}

function iconBg(type: string, status?: string) {
  if (type === "QC_COMPLETED") {
    if (status === "COMPLETED") return "bg-green-500/15 border-green-500/20";
    if (status === "ERROR")     return "bg-red-500/15 border-red-500/20";
    return "bg-indigo-500/15 border-indigo-500/20";
  }
  if (type === "RE_REVIEW_REQUESTED") return "bg-amber-500/15 border-amber-500/20";
  return "bg-white/[0.06] border-white/10";
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 5)   return "just now";
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  if (h < 48)  return "Yesterday";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

const MAX_NOTIFS = 50;

// ── NotificationCard ──────────────────────────────────────────────────────────

function NotificationCard({
  n, onDismiss, onRead,
}: {
  n: Notification;
  onDismiss: (id: string) => void;
  onRead: (id: string) => void;
}) {
  return (
    <div
      onClick={() => onRead(n.id)}
      className={`group relative flex items-start gap-3 rounded-xl px-3.5 py-3 transition-all duration-150 cursor-default ${
        n.read
          ? "opacity-60 hover:opacity-80"
          : "bg-white/[0.03] hover:bg-white/[0.05]"
      }`}
    >
      {/* unread dot */}
      {!n.read && (
        <span className="absolute left-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-indigo-400" />
      )}

      {/* icon */}
      <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border ${iconBg(n.type, n.status)}`}>
        {iconFor(n.type, n.status)}
      </div>

      {/* content */}
      <div className="min-w-0 flex-1">
        <p className={`text-[13px] leading-snug ${n.read ? "text-slate-400" : "text-slate-100 font-medium"}`}>
          {n.message}
        </p>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-[11px] text-slate-600">{timeAgo(n.occurredAt)}</span>
          {n.needsReview && n.batchId && (
            <Link
              href={`/admin/batches/${n.batchId}`}
              onClick={e => { e.stopPropagation(); onRead(n.id); }}
              className="text-[11px] text-indigo-400/80 hover:text-indigo-300 transition-colors"
            >
              Open →
            </Link>
          )}
        </div>
      </div>

      {/* dismiss */}
      <button
        onClick={e => { e.stopPropagation(); onDismiss(n.id); }}
        className="shrink-0 rounded-lg p-1 text-slate-700 opacity-0 transition-all group-hover:opacity-100 hover:bg-white/[0.06] hover:text-slate-400"
        aria-label="Dismiss"
      >
        <X size={12} />
      </button>
    </div>
  );
}

// ── NotificationBell ──────────────────────────────────────────────────────────

export function NotificationBell() {
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [entering, setEntering] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const btnRef  = useRef<HTMLButtonElement>(null);

  const unread = notifs.filter(n => !n.read).length;

  const addNotif = useCallback((raw: unknown) => {
    const data = raw as Record<string, unknown>;
    const notif: Notification = {
      id:            Date.now().toString(36) + Math.random().toString(36).slice(2),
      type:          String(data.type ?? "NOTIFICATION"),
      message:       String(data.message ?? "New notification"),
      batchId:       data.batchId as number | undefined,
      parentBatchId: data.parentBatchId as string | undefined,
      status:        data.status as string | undefined,
      needsReview:   Boolean(data.needsReview),
      occurredAt:    String(data.occurredAt ?? new Date().toISOString()),
      read:          false,
    };
    setNotifs(prev => [notif, ...prev].slice(0, MAX_NOTIFS));
  }, []);

  useWebSocket(
    ["/topic/admin/notifications"],
    useCallback((_topic: string, payload: unknown) => { addNotif(payload); }, [addNotif]),
  );

  // open with entrance animation
  function toggleOpen() {
    if (open) {
      setOpen(false);
    } else {
      setOpen(true);
      setEntering(true);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setEntering(false));
      });
    }
  }

  // ESC key
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    if (open) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // click outside
  useEffect(() => {
    function onMouse(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        btnRef.current   && !btnRef.current.contains(e.target as Node)
      ) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onMouse);
    return () => document.removeEventListener("mousedown", onMouse);
  }, [open]);

  function markAllRead() {
    setNotifs(prev => prev.map(n => ({ ...n, read: true })));
  }
  function dismissOne(id: string) {
    setNotifs(prev => prev.filter(n => n.id !== id));
  }
  function readOne(id: string) {
    setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  }
  function clearAll() {
    setNotifs([]);
    setOpen(false);
  }

  return (
    <div className="relative">
      {/* Bell button */}
      <button
        ref={btnRef}
        onClick={toggleOpen}
        className="relative flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-300"
        aria-label="Notifications"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-indigo-500 px-0.5 text-[9px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {/* macOS-style panel */}
      {open && (
        <div
          ref={panelRef}
          style={{
            transition: "opacity 180ms ease, transform 180ms ease",
            opacity: entering ? 0 : 1,
            transform: entering ? "scale(0.95) translateY(-6px)" : "scale(1) translateY(0)",
            transformOrigin: "top right",
          }}
          className="absolute right-0 top-10 z-50 w-[380px] overflow-hidden rounded-2xl
                     border border-white/[0.08]
                     bg-[#141618]/90
                     shadow-[0_32px_64px_rgba(0,0,0,0.7),0_0_0_0.5px_rgba(255,255,255,0.05)]
                     backdrop-blur-2xl"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3.5">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold text-white tracking-tight">Notifications</span>
              {unread > 0 && (
                <span className="rounded-full bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-300">
                  {unread} new
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  title="Mark all as read"
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-300"
                >
                  <CheckCheck size={11} /> All read
                </button>
              )}
              {notifs.length > 0 && (
                <button
                  onClick={clearAll}
                  className="rounded-md px-2 py-1 text-[11px] text-slate-600 transition hover:bg-white/[0.06] hover:text-slate-400"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Thin separator */}
          <div className="mx-4 h-px bg-white/[0.06]" />

          {/* Notification list */}
          <div className="max-h-[440px] overflow-y-auto px-1.5 py-2">
            {notifs.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.03]">
                  <Bell size={22} className="text-slate-600" />
                </div>
                <div>
                  <div className="text-sm font-medium text-slate-400">No recent notifications</div>
                  <div className="mt-1 text-xs text-slate-600">You&apos;re all caught up.</div>
                </div>
              </div>
            ) : (
              <ul className="space-y-0.5">
                {notifs.map(n => (
                  <li key={n.id}>
                    <NotificationCard n={n} onDismiss={dismissOne} onRead={readOne} />
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Footer */}
          {notifs.length > 0 && (
            <>
              <div className="mx-4 h-px bg-white/[0.06]" />
              <div className="px-4 py-2.5 text-center">
                <span className="text-[11px] text-slate-700">
                  {notifs.length} notification{notifs.length !== 1 ? "s" : ""}
                  {unread > 0 ? ` · ${unread} unread` : " · all read"}
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
