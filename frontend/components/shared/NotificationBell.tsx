"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Bell, X, CheckCircle2, AlertTriangle, Info,
  CheckCheck, Layers,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getNotifications, markNotificationRead, markAllNotificationsRead } from "@/lib/api";
import Link from "next/link";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Notification {
  id: string;
  /** Present for DB-persisted notifications (e.g. order-assigned); absent for live WS-only events. */
  serverId?: number;
  type: string;
  message: string;
  link?: string;
  batchId?: number;
  parentBatchId?: string;
  status?: string;
  needsReview?: boolean;
  occurredAt: string;
  read: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function notifIcon(type: string, status?: string) {
  if (type === "QC_COMPLETED") {
    if (status === "COMPLETED") return <CheckCircle2 size={16} className="text-green-400" />;
    if (status === "ERROR")     return <AlertTriangle size={16} className="text-red-400" />;
    return <Layers size={16} className="text-indigo-400" />;
  }
  if (type === "RE_REVIEW_REQUESTED") return <AlertTriangle size={16} className="text-amber-400" />;
  if (type === "ORDER_ASSIGNED") return <CheckCheck size={16} className="text-indigo-400" />;
  return <Info size={16} className="text-slate-400" />;
}

function notifIconBg(type: string, status?: string) {
  if (type === "QC_COMPLETED") {
    if (status === "COMPLETED") return "bg-green-500/10 ring-green-500/25";
    if (status === "ERROR")     return "bg-red-500/10 ring-red-500/25";
    return "bg-indigo-500/10 ring-indigo-500/25";
  }
  if (type === "RE_REVIEW_REQUESTED") return "bg-amber-500/10 ring-amber-500/25";
  return "bg-white/[0.05] ring-white/10";
}

function notifLabel(type: string, status?: string) {
  if (type === "QC_COMPLETED") {
    if (status === "COMPLETED") return "QC Passed";
    if (status === "ERROR")     return "QC Error";
    return "QC Complete";
  }
  if (type === "RE_REVIEW_REQUESTED") return "Re-review Request";
  if (type === "ORDER_ASSIGNED") return "Order Assigned";
  return "Notification";
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

const MAX_NOTIFS = 60;

// ── Single card ───────────────────────────────────────────────────────────────

function NotifCard({ n, onDismiss, onRead }: {
  n: Notification;
  onDismiss: (id: string) => void;
  onRead: (id: string) => void;
}) {
  return (
    <div
      onClick={() => onRead(n.id)}
      className={`group relative flex cursor-default select-none items-start gap-3.5 rounded-2xl p-4 transition-all duration-100 ${
        n.read
          ? "opacity-45 hover:opacity-65"
          : "bg-white/[0.04] ring-1 ring-inset ring-white/[0.06] hover:bg-white/[0.06]"
      }`}
    >
      {/* unread dot — top-right corner */}
      {!n.read && (
        <span className="absolute right-4 top-4 h-2 w-2 rounded-full bg-indigo-400 ring-2 ring-sunken ring-offset-0" />
      )}

      {/* icon badge */}
      <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ring-1 ring-inset ${notifIconBg(n.type, n.status)}`}>
        {notifIcon(n.type, n.status)}
      </div>

      {/* body */}
      <div className="min-w-0 flex-1 pr-5">
        <span className={`text-[10px] font-bold uppercase tracking-widest ${n.read ? "text-slate-700" : "text-slate-500"}`}>
          {notifLabel(n.type, n.status)}
        </span>
        <p className={`mt-0.5 text-[13px] leading-snug ${n.read ? "text-slate-500" : "text-slate-100"}`}>
          {n.message}
        </p>
        <div className="mt-2 flex items-center gap-3">
          <span className="text-[11px] text-slate-600">{timeAgo(n.occurredAt)}</span>
          {n.needsReview && n.batchId && (
            <Link
              href={`/admin/batches/${n.batchId}`}
              onClick={e => { e.stopPropagation(); onRead(n.id); }}
              className="text-[11px] font-medium text-indigo-400/80 transition-colors hover:text-indigo-300"
            >
              View batch →
            </Link>
          )}
        </div>
      </div>

      {/* dismiss on hover */}
      <button
        onClick={e => { e.stopPropagation(); onDismiss(n.id); }}
        className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-white/[0.05] text-slate-600 opacity-0 transition-all hover:bg-white/10 hover:text-slate-300 group-hover:opacity-100"
        aria-label="Dismiss"
      >
        <X size={10} />
      </button>
    </div>
  );
}

// ── Notification Drawer (portal) ──────────────────────────────────────────────
// Rendered via createPortal at document.body so it is NOT trapped inside the
// sidebar's backdrop-filter stacking context. Without the portal, position:fixed
// children of a backdrop-filter parent are positioned relative to that parent
// rather than the viewport, so the "right-0" lands at the sidebar's right edge
// instead of the screen's right edge.

function NotificationDrawer({
  notifs,
  open,
  onClose,
  onMarkAllRead,
  onClearAll,
  onDismiss,
  onRead,
}: {
  notifs: Notification[];
  open: boolean;
  onClose: () => void;
  onMarkAllRead: () => void;
  onClearAll: () => void;
  onDismiss: (id: string) => void;
  onRead: (id: string) => void;
}) {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [now, setNow] = useState(0);
  const drawerRef = useRef<HTMLDivElement>(null);

  const unread = notifs.filter(n => !n.read).length;

  // mount → paint → animate in
  useEffect(() => {
    let frame: number | null = null;
    let nestedFrame: number | null = null;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    if (open) {
      frame = requestAnimationFrame(() => {
        setNow(Date.now());
        setMounted(true);
        nestedFrame = requestAnimationFrame(() => setVisible(true));
      });
    } else {
      frame = requestAnimationFrame(() => setVisible(false));
      timeout = setTimeout(() => setMounted(false), 320);
    }

    return () => {
      if (frame != null) cancelAnimationFrame(frame);
      if (nestedFrame != null) cancelAnimationFrame(nestedFrame);
      if (timeout != null) clearTimeout(timeout);
    };
  }, [open]);

  // ESC
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    if (mounted) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mounted, onClose]);

  // click outside
  useEffect(() => {
    const onMouse = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) onClose();
    };
    if (visible) {
      const t = setTimeout(() => document.addEventListener("mousedown", onMouse), 60);
      return () => { clearTimeout(t); document.removeEventListener("mousedown", onMouse); };
    }
  }, [visible, onClose]);

  const [today, earlier] = useMemo(() => {
    const currentTime = now || 0;
    const recent: Notification[] = [];
    const older: Notification[] = [];

    for (const notification of notifs) {
      if (currentTime - new Date(notification.occurredAt).getTime() < 86400000) {
        recent.push(notification);
      } else {
        older.push(notification);
      }
    }

    return [recent, older];
  }, [notifs, now]);

  if (!mounted) return null;

  const drawer = (
    <>
      {/* dim backdrop */}
      <div
        onClick={onClose}
        style={{ transition: "opacity 280ms ease", opacity: visible ? 1 : 0 }}
        className="fixed inset-0 z-[9998] bg-black/40 backdrop-blur-[2px]"
      />

      {/* drawer panel — anchored to viewport right edge */}
      <div
        ref={drawerRef}
        style={{
          transition: "transform 320ms cubic-bezier(0.32,0.72,0,1)",
          transform: visible ? "translateX(0)" : "translateX(100%)",
        }}
        className="fixed right-0 top-0 bottom-0 z-[9999] flex w-[400px] flex-col
                   border-l border-white/[0.08]
                   bg-sunken/75
                   shadow-[-24px_0_72px_rgba(0,0,0,0.65)]
                   backdrop-blur-[28px]"
      >
        {/* ── Header ─────────────────────────────── */}
        <div className="flex items-start justify-between px-5 pt-8 pb-5">
          <div>
            <div className="flex items-center gap-2.5">
              <Bell size={15} className="text-slate-400" />
              <h2 className="text-[15px] font-semibold tracking-tight text-white">Notifications</h2>
              {unread > 0 && (
                <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold text-indigo-300">
                  {unread} new
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-slate-600">
              QC completions, alerts and review requests
            </p>
          </div>
          <button
            onClick={onClose}
            className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-white/[0.06] text-slate-500 transition hover:bg-white/[0.1] hover:text-white"
          >
            <X size={13} />
          </button>
        </div>

        {/* ── Action bar ─────────────────────────── */}
        {notifs.length > 0 && (
          <>
            <div className="mx-5 h-px bg-white/[0.06]" />
            <div className="flex items-center justify-between px-5 py-2.5">
              {unread > 0 ? (
                <button
                  onClick={onMarkAllRead}
                  className="flex items-center gap-1.5 text-[11px] text-slate-500 transition hover:text-slate-300"
                >
                  <CheckCheck size={11} /> Mark all as read
                </button>
              ) : (
                <span className="text-[11px] text-slate-700">All caught up</span>
              )}
              <button
                onClick={onClearAll}
                className="text-[11px] text-slate-600 transition hover:text-slate-400"
              >
                Clear all
              </button>
            </div>
          </>
        )}

        {/* ── List ───────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-3 pb-6">
          {notifs.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-3xl border border-white/[0.06] bg-white/[0.03]">
                <Bell size={24} className="text-slate-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-400">No recent notifications</p>
                <p className="mt-1 text-xs text-slate-600">You&apos;re all caught up.</p>
              </div>
            </div>
          ) : (
            <div className="space-y-1 pt-1">
              {today.length > 0 && (
                <>
                  <p className="px-2 pb-1.5 pt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-700">Today</p>
                  {today.map(n => <NotifCard key={n.id} n={n} onDismiss={onDismiss} onRead={onRead} />)}
                </>
              )}
              {earlier.length > 0 && (
                <>
                  <p className="px-2 pb-1.5 pt-3 text-[10px] font-semibold uppercase tracking-widest text-slate-700">Earlier</p>
                  {earlier.map(n => <NotifCard key={n.id} n={n} onDismiss={onDismiss} onRead={onRead} />)}
                </>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ─────────────────────────────── */}
        {notifs.length > 0 && (
          <div className="border-t border-white/[0.06] px-5 py-3 text-center">
            <span className="text-[11px] text-slate-700">
              {notifs.length} notification{notifs.length !== 1 ? "s" : ""}
              {unread > 0 ? ` · ${unread} unread` : " · all read"}
            </span>
          </div>
        )}
      </div>
    </>
  );

  // Portal to document.body — escapes sidebar's backdrop-filter stacking context
  return typeof document !== "undefined"
    ? createPortal(drawer, document.body)
    : null;
}

// ── Bell trigger (lives in sidebar) ──────────────────────────────────────────

export function NotificationBell({ topics = ["/topic/admin/notifications"] }: {
  topics?: string[];
}) {
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const unread = notifs.filter(n => !n.read).length;

  const addNotif = useCallback((raw: unknown) => {
    const d = raw as Record<string, unknown>;
    setNotifs(prev => [{
      id:            Date.now().toString(36) + Math.random().toString(36).slice(2),
      type:          String(d.type ?? "NOTIFICATION"),
      message:       String(d.message ?? "New notification"),
      batchId:       d.batchId as number | undefined,
      parentBatchId: d.parentBatchId as string | undefined,
      status:        d.status as string | undefined,
      needsReview:   Boolean(d.needsReview),
      occurredAt:    String(d.occurredAt ?? new Date().toISOString()),
      read:          false,
    }, ...prev].slice(0, MAX_NOTIFS));
  }, []);

  useWebSocket(
    topics,
    useCallback((_t: string, p: unknown) => addNotif(p), [addNotif]),
  );

  // Persisted notifications (e.g. order-assigned) — fetched on mount and polled.
  // Live WS-only events (no serverId) are preserved and merged newest-first.
  const refreshPersisted = useCallback(async () => {
    try {
      const res = await getNotifications(30);
      const persisted: Notification[] = res.items.map(it => ({
        id: `db-${it.id}`,
        serverId: it.id,
        type: it.type,
        message: it.message || it.title,
        link: it.link ?? undefined,
        occurredAt: it.createdAt ?? new Date().toISOString(),
        read: it.read,
      }));
      setNotifs(prev => {
        const wsOnly = prev.filter(n => n.serverId === undefined);
        return [...wsOnly, ...persisted]
          .sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime())
          .slice(0, MAX_NOTIFS);
      });
    } catch {
      /* offline / not authenticated — leave existing state */
    }
  }, []);

  useEffect(() => {
    void refreshPersisted();
    const t = setInterval(() => void refreshPersisted(), 30000);
    return () => clearInterval(t);
  }, [refreshPersisted]);

  const handleRead = useCallback((id: string) => {
    setNotifs(prev => {
      const target = prev.find(n => n.id === id);
      if (target?.serverId) void markNotificationRead(target.serverId).catch(() => undefined);
      return prev.map(n => (n.id === id ? { ...n, read: true } : n));
    });
  }, []);

  const handleMarkAllRead = useCallback(() => {
    setNotifs(prev => prev.map(n => ({ ...n, read: true })));
    void markAllNotificationsRead().catch(() => undefined);
  }, []);

  return (
    <>
      {/* Bell button in sidebar */}
      <button
        onClick={() => setDrawerOpen(o => !o)}
        className="relative flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-300"
        aria-label="Open notifications"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-indigo-500 px-0.5 text-[9px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {/* Drawer rendered at document.body via portal */}
      <NotificationDrawer
        notifs={notifs}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onMarkAllRead={handleMarkAllRead}
        onClearAll={() => { setNotifs([]); setDrawerOpen(false); }}
        onDismiss={id => setNotifs(p => p.filter(n => n.id !== id))}
        onRead={handleRead}
      />
    </>
  );
}
