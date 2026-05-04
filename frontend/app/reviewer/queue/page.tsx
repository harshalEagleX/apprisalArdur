"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Clock, AlertCircle, CheckCircle2, ChevronRight, RefreshCw,
  Search, XCircle, ListFilter, FileText, ShieldAlert, PlayCircle, CalendarDays,
} from "lucide-react";
import type { ComponentType } from "react";
import { type QCResult } from "@/lib/api";
import StatusBadge from "@/components/shared/StatusBadge";
import EmptyState from "@/components/shared/EmptyState";
import { PageSpinner } from "@/components/shared/Spinner";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";
type QueueView = "all" | "failures" | "review";
const QUEUE_VIEWS: QueueView[] = ["all", "failures", "review"];

export default function ReviewerQueuePage() {
  const [items, setItems]     = useState<QCResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("q") ?? "";
  });
  const [view, setView] = useState<QueueView>(() => {
    if (typeof window === "undefined") return "all";
    const next = new URLSearchParams(window.location.search).get("view");
    return QUEUE_VIEWS.includes(next as QueueView) ? next as QueueView : "all";
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  async function loadQueue(showRefreshSpinner = false) {
    if (showRefreshSpinner) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const r = await fetch(`${JAVA}/api/reviewer/qc/results/pending`, { credentials: "include" });
      if (!r.ok) { setError(`Server responded with ${r.status}`); return; }
      const data: QCResult[] = await r.json();
      setItems(data);
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadQueue(); }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (view !== "all") params.set("view", view);
    const nextUrl = params.toString() ? `/reviewer/queue?${params}` : "/reviewer/queue";
    window.history.replaceState(null, "", nextUrl);
  }, [query, view]);

  const searched = useMemo(() => items.filter(item => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return item.batchFile.filename.toLowerCase().includes(q)
      || String(item.id).includes(q)
      || item.qcDecision.toLowerCase().includes(q);
  }), [items, query]);
  const scoped = useMemo(() => searched.filter(item => {
    if (view === "failures") return item.failedCount > 0;
    if (view === "review") return item.failedCount === 0;
    return true;
  }), [searched, view]);
  const urgent = useMemo(() => scoped.filter(i => i.failedCount > 0), [scoped]);
  const normal = useMemo(() => scoped.filter(i => i.failedCount === 0), [scoped]);
  const orderedScoped = useMemo(() => [...urgent, ...normal], [urgent, normal]);
  const stats = {
    total: items.length,
    failures: items.filter(i => i.failedCount > 0).length,
    reviewOnly: items.filter(i => i.failedCount === 0).length,
    verifyRules: items.reduce((sum, item) => sum + item.verifyCount, 0),
  };
  const prioritized = [...items].sort((a, b) =>
    (b.failedCount - a.failedCount) ||
    (b.verifyCount - a.verifyCount) ||
    (new Date(a.processedAt).getTime() - new Date(b.processedAt).getTime())
  );
  const nextItem = prioritized[0];
  const todayKey = new Date().toDateString();
  const processedToday = items.filter(item => new Date(item.processedAt).toDateString() === todayKey).length;
  const oldestItem = items.reduce<QCResult | undefined>((oldest, item) => {
    if (!oldest) return item;
    return new Date(item.processedAt).getTime() < new Date(oldest.processedAt).getTime() ? item : oldest;
  }, undefined);
  const oldestPending = oldestItem
    ? new Date(oldestItem.processedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "None";

  useEffect(() => {
    let cancelled = false;
    if (orderedScoped.length === 0) {
      const timer = window.setTimeout(() => {
        if (!cancelled) setSelectedId(null);
      }, 0);
      return () => {
        cancelled = true;
        window.clearTimeout(timer);
      };
    }
    if (!selectedId || !orderedScoped.some(item => item.id === selectedId)) {
      const timer = window.setTimeout(() => {
        if (!cancelled) setSelectedId(orderedScoped[0].id);
      }, 0);
      return () => {
        cancelled = true;
        window.clearTimeout(timer);
      };
    }
  }, [orderedScoped, selectedId]);

  function openQueueItem(item?: QCResult) {
    if (!item) return;
    window.location.href = `/reviewer/verify/${item.id}`;
  }

  function moveSelection(delta: number) {
    if (orderedScoped.length === 0) return;
    const currentIndex = Math.max(0, orderedScoped.findIndex(item => item.id === selectedId));
    const nextIndex = Math.min(Math.max(currentIndex + delta, 0), orderedScoped.length - 1);
    const next = orderedScoped[nextIndex];
    setSelectedId(next.id);
    window.setTimeout(() => {
      document.getElementById(`queue-item-${next.id}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 0);
  }

  function setViewShortcut(next: QueueView) {
    setView(next);
    setSelectedId(null);
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName?.toLowerCase();
      const inTextField = tagName === "input" || tagName === "textarea" || tagName === "select" || target?.isContentEditable;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      if (event.key === "Escape") {
        if (query) {
          event.preventDefault();
          setQuery("");
          searchRef.current?.blur();
        }
        return;
      }
      if (inTextField) return;

      const key = event.key.toLowerCase();
      if (key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (key === "r") {
        event.preventDefault();
        void loadQueue(true);
        return;
      }
      if (key === "n") {
        event.preventDefault();
        openQueueItem(nextItem);
        return;
      }
      if (key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        moveSelection(1);
        return;
      }
      if (key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        moveSelection(-1);
        return;
      }
      if (event.key === "Home") {
        event.preventDefault();
        if (orderedScoped[0]) setSelectedId(orderedScoped[0].id);
        return;
      }
      if (event.key === "End") {
        event.preventDefault();
        const last = orderedScoped[orderedScoped.length - 1];
        if (last) setSelectedId(last.id);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        openQueueItem(orderedScoped.find(item => item.id === selectedId) ?? nextItem);
        return;
      }
      if (event.key === "1") setViewShortcut("all");
      if (event.key === "2") setViewShortcut("failures");
      if (event.key === "3") setViewShortcut("review");
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nextItem, orderedScoped, query, selectedId]);

  return (
    <div className="mx-auto max-w-6xl px-5 py-7">
      {/* Header */}
      <div className="mb-5 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Verification queue</h1>
          <p className="text-slate-500 text-sm mt-0.5">Appraisal files assigned to you that need a decision</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {items.length > 0 && (
            <span className="text-xs bg-amber-950/60 border border-amber-800/50 text-amber-300 px-2.5 py-1 rounded-full font-medium">
              {items.length} pending
            </span>
          )}
          <button
            onClick={() => loadQueue(true)}
            disabled={refreshing}
            className="h-8 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-400 text-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {!loading && !error && (
        <div className="mb-4 grid gap-3 lg:grid-cols-[1.25fr_0.75fr]">
          <ReviewerNextAction item={nextItem} />
          <div className="grid grid-cols-2 gap-2">
            <QueueSignal icon={CalendarDays} label="Processed today" value={processedToday} />
            <QueueSignal icon={Clock} label="Oldest pending" value={oldestPending} />
          </div>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        <QueueStat icon={FileText} label="Assigned files" value={stats.total} tone="slate" />
        <QueueStat icon={ShieldAlert} label="With failures" value={stats.failures} tone="red" />
        <QueueStat icon={Clock} label="Review only" value={stats.reviewOnly} tone="amber" />
        <QueueStat icon={ListFilter} label="Verify rules" value={stats.verifyRules} tone="blue" />
      </div>

      <div className="mb-5 rounded-lg border border-slate-800 bg-slate-900/80 p-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative flex-1 md:max-w-md">
            <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              ref={searchRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search file name, QC result, or decision..."
              className="h-9 w-full rounded-lg border border-slate-700 bg-slate-900 pl-8 pr-9 text-sm text-white placeholder-slate-500 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-slate-300"
                title="Clear search"
                aria-label="Clear search"
              >
                <XCircle size={13} />
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {QUEUE_VIEWS.map(next => (
              <button
                key={next}
                onClick={() => setView(next)}
                aria-pressed={view === next}
                aria-keyshortcuts={next === "all" ? "1" : next === "failures" ? "2" : "3"}
                className={`h-9 rounded-md px-3 text-xs font-medium transition-colors ${
                  view === next
                    ? "bg-blue-600 text-white"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
              >
                {next === "all" ? "All" : next === "failures" ? "Failures" : "Review only"}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-2 text-[11px] text-slate-500">
          Showing {scoped.length} of {items.length} assigned file{items.length === 1 ? "" : "s"}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-5 flex items-start gap-3 p-4 bg-red-950/40 border border-red-800/50 rounded-xl text-red-300 text-sm">
          <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <PageSpinner label="Loading your queue…" />
      ) : items.length === 0 && !error ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl">
          <EmptyState
            icon={CheckCircle2}
            title="Queue is clear"
            description="No files require your review right now. Check back later or refresh."
          />
        </div>
      ) : scoped.length === 0 && !error ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900">
          <EmptyState
            icon={Search}
            title="No queue items match"
            description="Clear the search or change the queue filter."
            action={
              <button onClick={() => { setQuery(""); setView("all"); }} className="text-sm text-blue-400 hover:text-blue-300">
                Reset queue filters
              </button>
            }
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Urgent — files with failures */}
          {urgent.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-2 px-1">
                <AlertCircle size={12} className="text-red-400" />
                <span className="text-xs font-semibold text-red-400 uppercase tracking-wide">Requires attention — has failures</span>
              </div>
              <QueueList items={urgent} selectedId={selectedId} onSelect={setSelectedId} />
            </section>
          )}

          {/* Normal queue */}
          {normal.length > 0 && (
            <section>
              {urgent.length > 0 && (
                <div className="flex items-center gap-2 mb-2 px-1">
                  <Clock size={12} className="text-slate-400" />
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Pending review</span>
                </div>
              )}
              <QueueList items={normal} selectedId={selectedId} onSelect={setSelectedId} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function ReviewerNextAction({ item }: { item?: QCResult }) {
  if (!item) {
    return (
      <div className="rounded-lg border border-green-900/50 bg-green-950/25 p-4 text-green-100">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <CheckCircle2 size={16} />
          Nothing needs review right now
        </div>
        <p className="mt-1 text-sm text-green-100/75">Your assigned review queue is clear. Refresh later for new work.</p>
      </div>
    );
  }
  const hasFailure = item.failedCount > 0;
  return (
    <a
      href={`/reviewer/verify/${item.id}`}
      aria-keyshortcuts="N"
      className={`group flex min-h-24 items-center gap-4 rounded-lg border p-4 transition-colors ${
        hasFailure
          ? "border-red-900/50 bg-red-950/25 text-red-100 hover:border-red-700"
          : "border-amber-900/50 bg-amber-950/25 text-amber-100 hover:border-amber-700"
      }`}
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-current/20 bg-slate-950/30">
        {hasFailure ? <ShieldAlert size={20} /> : <PlayCircle size={20} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-semibold uppercase tracking-wide opacity-70">Next review action</div>
        <div className="mt-1 truncate text-base font-semibold text-white">{item.batchFile.filename}</div>
        <div className="mt-1 text-xs opacity-80">
          {item.failedCount} fail · {item.verifyCount} review · {item.passedCount} pass
        </div>
      </div>
      <div className="flex items-center gap-1.5 text-sm font-semibold text-white">
        Review <ChevronRight size={14} className="transition-transform group-hover:translate-x-0.5" />
      </div>
    </a>
  );
}

function QueueSignal({ icon: Icon, label, value }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-3">
      <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-100">
        <Icon size={14} className="text-slate-500" />
        <span className="truncate">{value}</span>
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

function QueueList({ items, selectedId, onSelect }: { items: QCResult[]; selectedId: number | null; onSelect: (id: number) => void }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900 divide-y divide-slate-800">
      {items.map(item => {
        const total      = item.totalRules;
        const passRate   = total > 0 ? Math.round((item.passedCount / total) * 100) : 0;
        const hasFailure = item.failedCount > 0;
        const actionLabel = hasFailure ? "Review failures" : "Review";

        return (
          <div
            id={`queue-item-${item.id}`}
            key={item.id}
            onMouseEnter={() => onSelect(item.id)}
            className={`flex flex-col gap-3 px-5 py-4 transition-colors hover:bg-slate-800/30 md:flex-row md:items-center ${hasFailure ? "bg-red-950/5" : ""} ${selectedId === item.id ? "ring-1 ring-blue-500/70 ring-inset" : ""}`}
          >
            {/* File icon */}
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${hasFailure ? "bg-red-950/60 border border-red-800/40" : "bg-slate-800 border border-slate-700"}`}>
              <svg className={`w-4 h-4 ${hasFailure ? "text-red-400" : "text-slate-400"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>

            {/* File info */}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-slate-200 truncate" title={item.batchFile.filename}>{item.batchFile.filename}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">QC #{item.id}</span>
                <span className="text-[11px] text-slate-500">
                  Processed {new Date(item.processedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                </span>
                {item.cacheHit && (
                  <span className="text-[10px] bg-slate-800 border border-slate-700 text-slate-500 px-1.5 py-0.5 rounded font-mono">cached</span>
                )}
              </div>
            </div>

            {/* Rule summary */}
            <div className="flex items-center gap-4 flex-shrink-0">
              <RuleStat label="Pass"   count={item.passedCount}  color="text-green-400" />
              <RuleStat label="Fail"   count={item.failedCount}  color="text-red-400" />
              <RuleStat label="Review" count={item.verifyCount}  color="text-amber-400" />
              <div className="flex flex-col items-end gap-1 w-16">
                <span className="text-[10px] text-slate-600 font-mono">{passRate}% pass</span>
                <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{
                    width: `${passRate}%`,
                    background: passRate >= 80 ? "#22c55e" : passRate >= 50 ? "#f59e0b" : "#ef4444",
                  }} />
                </div>
              </div>
            </div>

            {/* Decision badge */}
            <div className="hidden md:block flex-shrink-0">
              <StatusBadge status={item.qcDecision} size="xs" />
            </div>

            {/* Action */}
            <a
              href={`/reviewer/verify/${item.id}`}
              onFocus={() => onSelect(item.id)}
              aria-keyshortcuts="Enter"
              className="flex h-9 flex-shrink-0 items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 text-xs font-medium text-white transition-colors hover:bg-blue-700 md:min-w-[126px]"
            >
              {actionLabel} <ChevronRight size={13} />
            </a>
          </div>
        );
      })}
    </div>
  );
}

function QueueStat({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  tone: "slate" | "red" | "amber" | "blue";
}) {
  const styles = {
    slate: "border-slate-800 bg-slate-900 text-slate-300",
    red: "border-red-900/50 bg-red-950/25 text-red-200",
    amber: "border-amber-900/50 bg-amber-950/25 text-amber-200",
    blue: "border-blue-900/50 bg-blue-950/25 text-blue-200",
  };
  return (
    <div className={`flex h-14 items-center gap-3 rounded-lg border px-3 ${styles[tone]}`}>
      <Icon size={16} className="shrink-0 opacity-80" />
      <div className="min-w-0">
        <div className="text-lg font-semibold leading-none tabular-nums">{value}</div>
        <div className="mt-1 truncate text-[11px] uppercase tracking-wide opacity-70">{label}</div>
      </div>
    </div>
  );
}

function RuleStat({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="text-center w-10">
      <div className={`text-sm font-bold tabular-nums ${count === 0 ? "text-slate-600" : color}`}>{count}</div>
      <div className="text-[10px] text-slate-600">{label}</div>
    </div>
  );
}
