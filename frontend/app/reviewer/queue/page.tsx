"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Clock, AlertCircle, CheckCircle2, ChevronRight, RefreshCw,
  Search, XCircle, FileText, ShieldAlert, PlayCircle, CalendarDays,
  Archive,
} from "lucide-react";
import type { ComponentType } from "react";
import { getReviewerPending, getSubmittedQueue, type QCResult } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import EmptyState from "@/components/shared/EmptyState";
import { PageSpinner } from "@/components/shared/Spinner";

type QueueView = "all" | "failures" | "review";
const QUEUE_VIEWS: QueueView[] = ["all", "failures", "review"];

interface SubmittedReviewItem {
  id: number;
  finalDecision?: "PASS" | "FAIL";
  totalRules: number;
  passedCount: number;
  failedCount: number;
  reviewedAt?: string;
  batchFile?: {
    id: number;
    filename: string;
  };
}

interface QueuePageResponse<T> {
  content?: T[];
  totalElements?: number;
  totalPages?: number;
  page?: number;
  size?: number;
}

function asArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object" && Array.isArray((value as QueuePageResponse<T>).content)) {
    return (value as QueuePageResponse<T>).content ?? [];
  }
  return [];
}

function queueFilename(item: Pick<QCResult, "batchFile" | "id">): string {
  return item.batchFile?.filename || `QC #${item.id}`;
}

function formatProcessedAt(value?: string | null): string {
  if (!value) return "time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return date.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function ReviewerQueuePage() {
  const [items, setItems]     = useState<QCResult[]>([]);
  const [submittedItems, setSubmittedItems] = useState<SubmittedReviewItem[]>([]);
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
  // qcResultIds in this queue that a re-run superseded while the reviewer sat
  // here — surfaces a "queue has updates" banner without a manual refresh.
  const [staleIds, setStaleIds] = useState<Set<number>>(new Set());
  const searchRef = useRef<HTMLInputElement | null>(null);

  const loadQueue = useCallback(async (showRefreshSpinner = false) => {
    if (showRefreshSpinner) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      // Pending is the critical payload; the submitted list is best-effort
      // (a failure there must not blank out the queue), so it gets its own catch.
      const data = await getReviewerPending<unknown>();
      setItems(asArray<QCResult>(data));
      setStaleIds(new Set()); // a fresh load reflects the latest active results
      try {
        const submitted = await getSubmittedQueue();
        setSubmittedItems(asArray<SubmittedReviewItem>(submitted));
      } catch { /* non-critical — keep the previously loaded submitted list */ }
    } catch (err) {
      setError(err instanceof Error && err.message
        ? err.message
        : "Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadQueue(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadQueue]);

  // Queue-level live notifications: subscribe to each assigned result's existing
  // /superseded topic. When an admin re-runs QC, the active result the reviewer
  // sees is replaced — instead of silently going stale, the queue flags it and
  // offers a one-click refresh. Reuses the same realtime channel the verify page
  // uses; no extra backend wiring.
  const supersededTopics = useMemo(
    () => items.map(i => `/topic/reviewer/qc/${i.id}/superseded`),
    [items],
  );
  useWebSocket(
    supersededTopics,
    useCallback((topic: string) => {
      const match = topic.match(/\/topic\/reviewer\/qc\/(\d+)\/superseded/);
      if (!match) return;
      const supersededId = Number(match[1]);
      setStaleIds(prev => {
        if (prev.has(supersededId)) return prev;
        const next = new Set(prev);
        next.add(supersededId);
        return next;
      });
    }, []),
  );

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
    const filename = item.batchFile?.filename ?? "";
    return filename.toLowerCase().includes(q)
      || String(item.id).includes(q)
      || String(item.qcDecision ?? "").toLowerCase().includes(q);
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
    submitted: submittedItems.length,
  };
  const prioritized = [...items].sort((a, b) =>
    (b.failedCount - a.failedCount) ||
    (b.verifyCount - a.verifyCount) ||
    (new Date(a.processedAt ?? 0).getTime() - new Date(b.processedAt ?? 0).getTime())
  );
  const nextItem = prioritized[0];
  const todayKey = new Date().toDateString();
  const reviewedToday = submittedItems.filter(item =>
    item.reviewedAt && new Date(item.reviewedAt).toDateString() === todayKey
  ).length;
  const oldestItem = items.reduce<QCResult | undefined>((oldest, item) => {
    if (!oldest) return item;
    return new Date(item.processedAt ?? 0).getTime() < new Date(oldest.processedAt ?? 0).getTime() ? item : oldest;
  }, undefined);
  const oldestPending = oldestItem
    ? formatProcessedAt(oldestItem.processedAt)
    : "None";
  const queueReturnPath = useMemo(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (view !== "all") params.set("view", view);
    return params.toString() ? `/reviewer/queue?${params}` : "/reviewer/queue";
  }, [query, view]);

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
    window.location.href = reviewHref(item.id, queueReturnPath);
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
      if (inTextField && tagName === "input" && event.key === "Enter") {
        event.preventDefault();
        openQueueItem(orderedScoped.find(item => item.id === selectedId) ?? nextItem);
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
  }, [nextItem, orderedScoped, query, queueReturnPath, selectedId]);

  return (
    <div className="mx-auto max-w-6xl px-5 py-7">
      {/* Header */}
      <div className="mb-5 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600">Reviewer decision desk</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-white">Verification queue</h1>
          <p className="mt-1 text-sm text-slate-500">Assigned appraisal files that need evidence-based human decisions.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {items.length > 0 && (
            <span className="rounded-md border border-amber-500/25 bg-amber-950/35 px-2.5 py-1 text-xs font-medium text-amber-200">
              {items.length} pending
            </span>
          )}
          <button
            onClick={() => loadQueue(true)}
            disabled={refreshing}
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-surface px-3 text-sm text-slate-400 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {staleIds.size > 0 && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-indigo-500/30 bg-indigo-950/30 px-4 py-3">
          <RefreshCw size={16} className="shrink-0 text-indigo-300" />
          <span className="flex-1 text-sm text-indigo-100/90">
            {staleIds.size} report{staleIds.size === 1 ? " was" : "s were"} re-processed by a new QC run.
            Your queue is out of date — refresh to load the latest results.
          </span>
          <button
            onClick={() => loadQueue(true)}
            disabled={refreshing}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-indigo-400/30 bg-indigo-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
            Refresh queue
          </button>
        </div>
      )}

      {!loading && !error && (
        <div data-guide="reviewer-queue-next" className="mb-4 grid gap-3 lg:grid-cols-[1.25fr_0.75fr]">
          <ReviewerNextAction item={nextItem} returnTo={queueReturnPath} />
          <div className="grid grid-cols-2 gap-2">
            <QueueSignal icon={CalendarDays} label="Reviewed today" value={reviewedToday} />
            <QueueSignal icon={Clock} label="Oldest pending" value={oldestPending} />
          </div>
        </div>
      )}

      {/* Reviewers are task-oriented: show the 3 metrics that drive action, not 5.
          Per-file failure/verify breakdowns live on each queue row below. */}
      <div className="mb-4 grid grid-cols-3 gap-2">
        <QueueStat icon={FileText} label="Pending reviews" value={stats.total} tone="slate" />
        <QueueStat icon={ShieldAlert} label="With issues" value={stats.failures} tone="red" />
        <QueueStat icon={Archive} label="Completed by you" value={stats.submitted} tone="green" />
      </div>

      <div data-guide="reviewer-queue-filters" className="mb-5 rounded-lg border border-white/10 bg-surface/95 p-3 shadow-[0_12px_32px_rgba(0,0,0,0.16)]">
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative flex-1 md:max-w-md">
            <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              ref={searchRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search file name, QC result, or decision..."
              className="h-9 w-full rounded-md border border-white/10 bg-sunken/70 pl-8 pr-9 text-sm text-white placeholder-slate-600 transition-colors focus:border-slate-500/70 focus:outline-none focus:ring-2 focus:ring-slate-500/30"
            />
            {query && (
              <button
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.04] hover:text-slate-300"
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
                    ? "bg-slate-600 text-white shadow-[0_0_18px_rgba(226,232,240,0.16)]"
                    : "text-slate-500 hover:bg-white/[0.04] hover:text-slate-200"
                }`}
              >
                {next === "all" ? "All" : next === "failures" ? "Has issues" : "Review only"}
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
        <div className="mb-5 flex items-start gap-3 rounded-lg border border-red-500/25 bg-red-950/40 p-4 text-sm text-red-200">
          <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <PageSpinner label="Loading your queue…" />
      ) : items.length === 0 && !error ? (
        <div className="space-y-6">
          <div className="rounded-lg border border-white/10 bg-surface">
            <EmptyState
              icon={CheckCircle2}
              title="Queue is clear"
              description="No files require your review right now. Recently completed work is listed below."
            />
          </div>
          <SubmittedReviews items={submittedItems} returnTo={queueReturnPath} />
        </div>
      ) : scoped.length === 0 && !error ? (
        <div className="space-y-6">
          <div className="rounded-lg border border-white/10 bg-surface">
            <EmptyState
              icon={Search}
              title="No queue items match"
              description="Clear the search or change the queue filter."
              action={
                <button onClick={() => { setQuery(""); setView("all"); }} className="text-sm text-slate-400 hover:text-slate-300">
                  Reset queue filters
                </button>
              }
            />
          </div>
          <SubmittedReviews items={submittedItems} returnTo={queueReturnPath} />
        </div>
      ) : (
        <div className="space-y-6">
          <div data-guide="reviewer-queue-list" className="space-y-6">
            {/* Urgent — files with failures */}
            {urgent.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-2 px-1">
                  <AlertCircle size={12} className="text-red-400" />
                  <span className="text-xs font-semibold text-red-400 uppercase tracking-wide">Has issues — requires a decision</span>
                </div>
                <QueueList items={urgent} selectedId={selectedId} returnTo={queueReturnPath} onSelect={setSelectedId} />
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
                <QueueList items={normal} selectedId={selectedId} returnTo={queueReturnPath} onSelect={setSelectedId} />
              </section>
            )}
          </div>
          <SubmittedReviews items={submittedItems} returnTo={queueReturnPath} />
        </div>
      )}
    </div>
  );
}

function SubmittedReviews({ items, returnTo }: { items: SubmittedReviewItem[]; returnTo: string }) {
  if (items.length === 0) return null;

  return (
    <section>
      <div className="mb-2 flex items-center gap-2 px-1">
        <Archive size={12} className="text-slate-400" />
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Completed by you</span>
      </div>
      <div className="overflow-hidden rounded-lg border border-white/10 bg-surface shadow-[0_16px_40px_rgba(0,0,0,0.2)] divide-y divide-white/10">
        {items.map(item => {
          const reviewedAt = item.reviewedAt
            ? new Date(item.reviewedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
            : "Submitted";
          const filename = item.batchFile?.filename ?? `QC Result #${item.id}`;

          return (
            <div key={item.id} className="flex flex-col gap-3 px-5 py-4 transition-colors hover:bg-white/[0.03] md:flex-row md:items-center">
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-green-500/25 bg-green-950/30">
                <CheckCircle2 size={16} className="text-green-300" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-slate-200" title={filename}>{filename}</div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-slate-500">QC #{item.id}</span>
                  <span className="text-[11px] text-slate-500">{reviewedAt}</span>
                  {item.finalDecision && (
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${item.finalDecision === "PASS" ? "border-green-500/25 bg-green-950/30 text-green-300" : "border-red-500/25 bg-red-950/30 text-red-300"}`}>
                      {item.finalDecision}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4 flex-shrink-0">
                <RuleStat label="Clear" count={item.passedCount} color="text-green-400" />
                <RuleStat label="Issues" count={item.failedCount} color="text-red-400" />
                <RuleStat label="Total" count={item.totalRules} color="text-slate-400" />
              </div>
              <a
                href={`/reviewer/submitted/${item.id}?returnTo=${encodeURIComponent(returnTo)}`}
                className="flex h-9 flex-shrink-0 items-center justify-center gap-1.5 rounded-md border border-white/10 bg-sunken/70 px-3 text-xs font-semibold text-slate-200 transition-colors hover:border-slate-500/40 hover:bg-white/[0.04]"
              >
                View decisions <ChevronRight size={13} />
              </a>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ReviewerNextAction({ item, returnTo }: { item?: QCResult; returnTo: string }) {
  if (!item) {
    return (
      <div className="rounded-lg border border-green-500/25 bg-green-950/25 p-4 text-green-100 shadow-[0_12px_32px_rgba(0,0,0,0.16)]">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <CheckCircle2 size={16} />
          Nothing needs review right now
        </div>
        <p className="mt-1 text-sm text-green-100/75">Your assigned review queue is clear. Refresh later for new work.</p>
      </div>
    );
  }
  const hasFailure = item.failedCount > 0;
  const filename = queueFilename(item);
  return (
    <a
      href={reviewHref(item.id, returnTo)}
      aria-keyshortcuts="N"
      className={`group flex min-h-24 items-center gap-4 rounded-lg border p-4 transition-colors ${
        hasFailure
          ? "border-red-500/25 bg-red-950/25 text-red-100 hover:border-red-500/45"
          : "border-amber-500/25 bg-amber-950/25 text-amber-100 hover:border-amber-500/45"
      }`}
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-current/20 bg-sunken/40">
        {hasFailure ? <ShieldAlert size={20} /> : <PlayCircle size={20} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-semibold uppercase tracking-wide opacity-70">Next review action</div>
        <div className="mt-1 truncate text-base font-semibold text-white">{filename}</div>
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
    <div className="rounded-lg border border-white/10 bg-surface px-3 py-3 shadow-[0_12px_32px_rgba(0,0,0,0.16)]">
      <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-100">
        <Icon size={14} className="text-slate-500" />
        <span className="truncate">{value}</span>
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

function QueueList({ items, selectedId, returnTo, onSelect }: { items: QCResult[]; selectedId: number | null; returnTo: string; onSelect: (id: number) => void }) {
  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-surface shadow-[0_16px_40px_rgba(0,0,0,0.2)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <th className="w-2 px-3 py-2"></th>
            <th className="px-3 py-2 font-medium">File</th>
            <th className="px-3 py-2 text-center font-medium">
              <span className="text-red-400">Fail</span>
            </th>
            <th className="px-3 py-2 text-center font-medium">
              <span className="text-amber-400">Review</span>
            </th>
            <th className="px-3 py-2 text-center font-medium">
              <span className="text-green-400">Pass</span>
            </th>
            <th className="hidden px-3 py-2 font-medium sm:table-cell">Age</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.05]">
          {items.map(item => {
            const total      = item.totalRules;
            const passRate   = total > 0 ? Math.round((item.passedCount / total) * 100) : 0;
            const hasFailure = item.failedCount > 0;
            const filename   = queueFilename(item);
            const isSelected = selectedId === item.id;

            return (
              <tr
                id={`queue-item-${item.id}`}
                key={item.id}
                onMouseEnter={() => onSelect(item.id)}
                className={`cursor-default transition-colors hover:bg-white/[0.03] ${hasFailure ? "bg-red-950/[0.04]" : ""} ${isSelected ? "ring-1 ring-inset ring-slate-500/50" : ""}`}
              >
                {/* Priority dot */}
                <td className="px-3 py-2.5">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${hasFailure ? "bg-red-400" : item.verifyCount > 0 ? "bg-amber-400" : "bg-green-400"}`}
                    title={hasFailure ? "Has failures" : item.verifyCount > 0 ? "Needs review" : "All pass"}
                  />
                </td>

                {/* File */}
                <td className="min-w-0 max-w-[260px] px-3 py-2.5">
                  <div className="truncate font-medium text-slate-200" title={filename}>{filename}</div>
                  <div className="mt-0.5 flex items-center gap-1.5">
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-slate-500">QC #{item.id}</span>
                    {item.cacheHit && <span className="rounded bg-muted border border-white/10 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">cached</span>}
                  </div>
                </td>

                {/* Counts */}
                <td className="px-3 py-2.5 text-center">
                  <span className={`text-sm font-bold tabular-nums ${item.failedCount > 0 ? "text-red-300" : "text-slate-600"}`}>
                    {item.failedCount}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-center">
                  <span className={`text-sm font-bold tabular-nums ${item.verifyCount > 0 ? "text-amber-300" : "text-slate-600"}`}>
                    {item.verifyCount}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-center">
                  <div className="flex flex-col items-center gap-0.5">
                    <span className="text-sm font-bold tabular-nums text-slate-400">{item.passedCount}</span>
                    <div className="h-1 w-12 overflow-hidden rounded-full bg-sunken">
                      <div className="h-full rounded-full" style={{
                        width: `${passRate}%`,
                        background: passRate >= 80 ? "#22c55e" : passRate >= 50 ? "#f59e0b" : "#ef4444",
                      }} />
                    </div>
                  </div>
                </td>

                {/* Age */}
                <td className="hidden px-3 py-2.5 text-[11px] text-slate-500 sm:table-cell">
                  {formatProcessedAt(item.processedAt)}
                </td>

                {/* Action */}
                <td className="px-3 py-2.5 text-right">
                  <a
                    href={reviewHref(item.id, returnTo)}
                    onFocus={() => onSelect(item.id)}
                    aria-keyshortcuts="Enter"
                    className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-semibold text-white transition-colors ${
                      hasFailure
                        ? "border border-red-500/30 bg-red-950/50 hover:bg-red-950/80"
                        : "border border-slate-400/30 bg-slate-700 hover:bg-slate-600"
                    }`}
                  >
                    {hasFailure ? "Review" : "Verify"} <ChevronRight size={12} />
                  </a>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function reviewHref(id: number, returnTo: string) {
  return `/reviewer/verify/${id}?returnTo=${encodeURIComponent(returnTo)}`;
}

function QueueStat({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  value: number;
  tone: "slate" | "red" | "amber" | "blue" | "green";
}) {
  const styles = {
    slate: "border-white/10 bg-surface text-slate-300",
    red: "border-red-500/25 bg-red-950/25 text-red-200",
    amber: "border-amber-500/25 bg-amber-950/25 text-amber-200",
    blue: "border-slate-500/25 bg-slate-950/25 text-slate-200",
    green: "border-green-500/25 bg-green-950/25 text-green-200",
  };
  return (
    <div className={`flex h-14 items-center gap-3 rounded-lg border px-3 shadow-[0_12px_32px_rgba(0,0,0,0.16)] ${styles[tone]}`}>
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
