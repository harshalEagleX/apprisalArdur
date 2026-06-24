"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, XCircle, CheckCircle2, AlertCircle, Info, Clock } from "lucide-react";
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

function iconFor(type: string, status?: string) {
  if (type === "QC_COMPLETED") {
    if (status === "COMPLETED") return <CheckCircle2 size={14} className="text-green-400 shrink-0" />;
    if (status === "ERROR")     return <AlertCircle size={14} className="text-red-400 shrink-0" />;
    return <Info size={14} className="text-indigo-400 shrink-0" />;
  }
  if (type === "RE_REVIEW_REQUESTED") return <AlertCircle size={14} className="text-amber-400 shrink-0" />;
  return <Info size={14} className="text-slate-400 shrink-0" />;
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const MAX_NOTIFS = 50;

export function NotificationBell() {
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  const unread = notifs.filter(n => !n.read).length;

  const addNotif = useCallback((raw: unknown) => {
    const data = raw as Record<string, unknown>;
    const notif: Notification = {
      id:             Date.now().toString() + Math.random().toString(36).slice(2),
      type:           String(data.type ?? "NOTIFICATION"),
      message:        String(data.message ?? "New notification"),
      batchId:        data.batchId as number | undefined,
      parentBatchId:  data.parentBatchId as string | undefined,
      status:         data.status as string | undefined,
      needsReview:    Boolean(data.needsReview),
      occurredAt:     String(data.occurredAt ?? new Date().toISOString()),
      read:           false,
    };
    setNotifs(prev => [notif, ...prev].slice(0, MAX_NOTIFS));
  }, []);

  const topics = ["/topic/admin/notifications"];
  useWebSocket(topics, useCallback((_topic: string, payload: unknown) => {
    addNotif(payload);
  }, [addNotif]));

  // Close on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  function markAllRead() {
    setNotifs(prev => prev.map(n => ({ ...n, read: true })));
  }

  function dismiss(id: string) {
    setNotifs(prev => prev.filter(n => n.id !== id));
  }

  return (
    <div className="relative" ref={drawerRef}>
      {/* Bell button */}
      <button
        onClick={() => {
          setOpen(o => !o);
          if (!open) markAllRead();
        }}
        className="relative flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-300"
        aria-label="Notifications"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-600 text-[9px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {/* Drawer */}
      {open && (
        <div className="absolute right-0 top-10 z-50 w-[340px] rounded-xl border border-white/10 bg-[#0E1318] shadow-[0_16px_48px_rgba(0,0,0,0.4)]">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3">
            <div className="flex items-center gap-2">
              <Bell size={14} className="text-slate-400" />
              <span className="text-sm font-semibold text-white">Notifications</span>
              {notifs.length > 0 && (
                <span className="rounded-full bg-[#161B22] px-1.5 py-0.5 text-[10px] text-slate-500">
                  {notifs.length}
                </span>
              )}
            </div>
            {notifs.length > 0 && (
              <button
                onClick={() => setNotifs([])}
                className="text-xs text-slate-600 transition hover:text-slate-400"
              >
                Clear all
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-[400px] overflow-y-auto">
            {notifs.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-10 text-slate-600">
                <Bell size={20} />
                <span className="text-sm">No notifications yet</span>
                <span className="text-xs text-slate-700">QC completions and alerts appear here</span>
              </div>
            ) : (
              <ul className="divide-y divide-white/[0.05]">
                {notifs.map(n => (
                  <li key={n.id} className="flex items-start gap-3 px-4 py-3 transition hover:bg-white/[0.02]">
                    <div className="mt-0.5">{iconFor(n.type, n.status)}</div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] leading-snug text-slate-200">{n.message}</p>
                      {n.needsReview && n.batchId && (
                        <Link
                          href={`/admin/batches/${n.batchId}`}
                          onClick={() => setOpen(false)}
                          className="mt-1 text-[11px] text-indigo-400 hover:underline"
                        >
                          Open batch →
                        </Link>
                      )}
                      <div className="mt-1 flex items-center gap-1 text-[11px] text-slate-600">
                        <Clock size={9} />
                        {timeAgo(n.occurredAt)}
                      </div>
                    </div>
                    <button
                      onClick={() => dismiss(n.id)}
                      className="shrink-0 text-slate-700 transition hover:text-slate-400"
                      aria-label="Dismiss"
                    >
                      <XCircle size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
