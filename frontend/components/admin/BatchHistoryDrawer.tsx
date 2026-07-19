"use client";
import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  History, XCircle, FileStack, RefreshCw, Plus, Minus,
  ArrowRight, ChevronDown, ChevronRight, GitCompare, Download,
} from "lucide-react";
import {
  getBatchById, getQCHistory, getQCResultDiff, downloadFindingsExport, processOrderQC,
  type Batch, type BatchFile, type QCHistoryRun, type QCResultDiff, type QCDiffFinding,
  type QCDiffRevision,
} from "@/lib/api";
import { toast } from "@/lib/toast";

/** Colour a QC status token (PASS / FAIL / VERIFY / etc.). */
function statusTone(status: string | null): string {
  const s = (status ?? "").toUpperCase();
  if (s.includes("PASS")) return "text-green-300";
  if (s.includes("FAIL")) return "text-red-300";
  if (s.includes("VERIFY")) return "text-amber-300";
  return "text-slate-300";
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function findingLabel(f: QCDiffFinding): string {
  const id = f.ruleId ?? "?";
  return f.targetField ? `${id} · ${f.targetField}` : id;
}

/** One added/removed finding line. */
function FindingLine({ f, sign }: { f: QCDiffFinding; sign: "+" | "-" }) {
  const Icon = sign === "+" ? Plus : Minus;
  const tone = sign === "+" ? "text-green-300" : "text-slate-500";
  return (
    <div className="flex items-start gap-1.5 py-0.5">
      <Icon size={11} className={`mt-0.5 shrink-0 ${tone}`} />
      <div className="min-w-0">
        <span className="font-mono text-[11px] text-slate-200">{findingLabel(f)}</span>
        {f.ruleName && (
          <span className="ml-1.5 text-[11px] text-slate-500">{f.ruleName}</span>
        )}
        <span className={`ml-1.5 text-[11px] font-medium ${statusTone(f.status)}`}>
          {f.status ?? "—"}
        </span>
      </div>
    </div>
  );
}

/** One changed finding line — previous → current status/severity. */
function ChangedLine({ f }: { f: QCDiffFinding }) {
  return (
    <div className="flex items-start gap-1.5 py-0.5">
      <GitCompare size={11} className="mt-0.5 shrink-0 text-amber-300" />
      <div className="min-w-0">
        <span className="font-mono text-[11px] text-slate-200">{findingLabel(f)}</span>
        <div className="mt-0.5 flex items-center gap-1.5 text-[11px]">
          <span className={statusTone(f.previousStatus ?? null)}>{f.previousStatus ?? "—"}</span>
          {f.previousSeverity && <span className="text-slate-600">({f.previousSeverity})</span>}
          <ArrowRight size={10} className="text-slate-500" />
          <span className={statusTone(f.status)}>{f.status ?? "—"}</span>
          {f.severity && <span className="text-slate-600">({f.severity})</span>}
        </div>
      </div>
    </div>
  );
}

/** Lazy-loaded diff body for a single re-run. */
function RunDiff({ runId }: { runId: number }) {
  const [diff, setDiff] = useState<QCResultDiff | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Initial sync state resets before async fetch — no render cascade.
    /* eslint-disable react-hooks/set-state-in-effect */
    setLoading(true);
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    getQCResultDiff(runId)
      .then(d => { if (!cancelled) setDiff(d); })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [runId]);

  if (loading) return <div className="px-2 py-2 text-[11px] text-slate-500">Loading changes…</div>;
  if (error) return <div className="px-2 py-2 text-[11px] text-red-300">Could not load diff: {error}</div>;
  if (!diff) return null;
  if (!diff.hasPrevious) {
    return <div className="px-2 py-2 text-[11px] text-slate-500">{diff.message ?? "No previous run to compare."}</div>;
  }

  const added = diff.added ?? [];
  const removed = diff.removed ?? [];
  const changed = diff.changed ?? [];
  const noChange = added.length === 0 && removed.length === 0 && changed.length === 0;

  return (
    <div className="mt-1 rounded-md border border-white/10 bg-sunken/60 p-2.5">
      {diff.ruleEngineChanged && (
        <div className="mb-2 flex items-center gap-1.5 rounded border border-amber-900/50 bg-amber-950/30 px-2 py-1 text-[10px] text-amber-200">
          <RefreshCw size={10} />
          Rule engine changed: {diff.previousRuleEngineVersion ?? "?"} → {diff.ruleEngineVersion ?? "?"} — deltas may reflect a rule change, not the report.
        </div>
      )}
      {noChange ? (
        <div className="text-[11px] text-slate-500">
          No findings changed between these two runs ({diff.unchangedCount ?? 0} identical).
        </div>
      ) : (
        <>
          {added.length > 0 && (
            <div className="mb-1.5">
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-green-300/80">Added ({added.length})</div>
              {added.map((f, i) => <FindingLine key={`a${i}`} f={f} sign="+" />)}
            </div>
          )}
          {removed.length > 0 && (
            <div className="mb-1.5">
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Removed ({removed.length})</div>
              {removed.map((f, i) => <FindingLine key={`r${i}`} f={f} sign="-" />)}
            </div>
          )}
          {changed.length > 0 && (
            <div>
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300/80">Changed ({changed.length})</div>
              {changed.map((f, i) => <ChangedLine key={`c${i}`} f={f} />)}
            </div>
          )}
        </>
      )}

      {(diff.auditTrail ?? []).length > 0 && (
        <div className="mt-2.5 border-t border-white/8 pt-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Revision trail
          </div>
          {(diff.auditTrail as QCDiffRevision[]).map(r => (
            <div key={r.revision} className="mb-1 rounded border border-white/6 bg-white/2 px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-medium text-slate-200">{r.action}</span>
                <span className="font-mono text-[10px] text-slate-600">r{r.revision}</span>
              </div>
              {r.changedBy && <p className="text-[10px] text-slate-500">{r.changedBy}</p>}
              <p className="text-[10px] text-slate-600">{new Date(r.changedAt).toLocaleString()}</p>
              {Object.keys(r.changes).length > 0 && (
                <div className="mt-0.5 space-y-0.5">
                  {Object.entries(r.changes).map(([field, { from, to }]) => (
                    <div key={field} className="text-[10px] text-slate-500">
                      <span className="text-slate-400">{field}: </span>
                      {from != null && <span className="line-through text-red-400/70">{String(from)}</span>}
                      {from != null && to != null && <span className="text-slate-600"> → </span>}
                      {to != null && <span className="text-green-400/80">{String(to)}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** A single QC run card within a file's chain. */
function RunCard({ run, index }: { run: QCHistoryRun; index: number }) {
  const [open, setOpen] = useState(false);
  const canDiff = run.rerunOfId != null;

  return (
    <div className="rounded-md border border-white/10 bg-surface/70 p-2.5">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold text-slate-300">Run #{index}</span>
        {run.isActive ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-green-900/60 bg-green-950/40 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-green-300">
            ● Active
          </span>
        ) : (
          <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-500">
            Superseded
          </span>
        )}
        {run.cacheHit && (
          <span className="rounded-full border border-slate-700 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-500">cache</span>
        )}
        <span className="ml-auto text-[10px] text-slate-500">{fmtTime(run.processedAt)}</span>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
        <span className="font-mono text-[10px] text-slate-400" title="Rule-engine version">
          {run.ruleEngineVersion ?? "unversioned"}
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-green-300">{run.passedCount} pass</span>
        <span className="text-red-300">{run.failedCount} fail</span>
        <span className="text-amber-300">{run.verifyCount} verify</span>
        {run.finalDecision && (
          <>
            <span className="text-slate-600">·</span>
            <span className={statusTone(run.finalDecision)}>{run.finalDecision}</span>
          </>
        )}
      </div>

      {canDiff && (
        <>
          <button
            type="button"
            onClick={() => setOpen(o => !o)}
            className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-indigo-300 transition-colors hover:text-indigo-200"
          >
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {open ? "Hide changes" : "View changes vs previous run"}
          </button>
          {open && <RunDiff runId={run.id} />}
        </>
      )}
    </div>
  );
}

/** All runs for one file, newest first. */
function FileHistory({ file, runs, onRerun, busy }: {
  file: BatchFile; runs: QCHistoryRun[];
  onRerun?: (fileId: number) => void; busy?: boolean;
}) {
  // Newest run first — the backend returns them by processedAt; sort defensively.
  const ordered = [...runs].sort((a, b) => {
    const ta = a.processedAt ? Date.parse(a.processedAt) : 0;
    const tb = b.processedAt ? Date.parse(b.processedAt) : 0;
    return tb - ta;
  });
  return (
    <section className="rounded-lg border border-white/10 bg-sunken/40 p-3">
      <div className="flex items-center gap-2">
        <FileStack size={13} className="text-slate-500" />
        <span className="truncate text-xs font-medium text-slate-200" title={file.filename}>{file.filename}</span>
        <span className="rounded border border-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-slate-500">{file.fileType}</span>
        <div className="ml-auto flex items-center gap-2">
          {/* Per-file re-run (only appraisal files that have been QC'd). Re-runs the full
              matched document set (appraisal + engagement + contract) through Python OCR; QC
              findings are updated for this appraisal only — other appraisals keep their results. */}
          {onRerun && ordered.length > 0 && (
            <button
              type="button"
              onClick={() => onRerun(file.id)}
              disabled={busy}
              title="Re-run QC for this appraisal — the matched document set is re-read by the OCR service; QC findings are updated for this file only"
              className="inline-flex items-center gap-1 rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-indigo-300 transition-colors hover:bg-white/[0.04] hover:text-indigo-200 disabled:opacity-50"
            >
              <RefreshCw size={10} className={busy ? "animate-spin" : ""} />
              {busy ? "Re-running…" : "Re-run file"}
            </button>
          )}
          <span className="text-[10px] text-slate-500">{ordered.length} run{ordered.length === 1 ? "" : "s"}</span>
        </div>
      </div>
      {ordered.length === 0 ? (
        <div className="mt-2 text-[11px] text-slate-500">No QC runs yet for this document.</div>
      ) : (
        <div className="mt-2 space-y-1.5">
          {ordered.map((run, i) => (
            <RunCard key={run.id} run={run} index={ordered.length - i} />
          ))}
        </div>
      )}
    </section>
  );
}

export interface BatchHistoryDrawerProps {
  batch: Batch | null;
  onClose: () => void;
}

export function BatchHistoryDrawer({ batch, onClose }: BatchHistoryDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<BatchFile[]>([]);
  const [historyByFile, setHistoryByFile] = useState<Record<number, QCHistoryRun[]>>({});
  const [downloading, setDownloading] = useState<"json" | "csv" | null>(null);
  const [rerunning, setRerunning] = useState<Set<number>>(new Set());

  const handleExport = useCallback(async (fmt: "json" | "csv") => {
    if (!batch) return;
    setDownloading(fmt);
    try {
      await downloadFindingsExport(batch.id, batch.parentBatchId, fmt);
    } catch (e) {
      toast.error("Findings export failed", e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading(null);
    }
  }, [batch]);

  const loadHistory = useCallback(async (batchId: number) => {
    setLoading(true);
    setError(null);
    try {
      const full = await getBatchById(batchId);
      const fs = full.files ?? [];
      setFiles(fs);
      const entries = await Promise.all(
        fs.map(async f => [f.id, await getQCHistory(f.id).catch(() => [])] as const),
      );
      setHistoryByFile(Object.fromEntries(entries));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRerunFile = useCallback(async (fileId: number) => {
    if (!batch) return;
    // Re-QC is order-scoped now — resolve the file's owning Order and run QC for it.
    const orderId = files.find(f => f.id === fileId)?.resolvedOrderId;
    if (!orderId) {
      toast.error("Re-run unavailable", "This file isn't linked to an order yet — assign it first.");
      return;
    }
    setRerunning(prev => new Set(prev).add(fileId));
    try {
      await processOrderQC(orderId);
      toast.success(
        "Re-run started for this order",
        "The matched document set (appraisal + engagement + contract) is re-read by the OCR service and the order's QC findings are updated.",
      );
      // Give the worker a moment, then refresh this file's run chain.
      window.setTimeout(() => { void loadHistory(batch.id); }, 2500);
    } catch (e) {
      toast.error("File re-run failed", e instanceof Error ? e.message : String(e));
    } finally {
      setRerunning(prev => { const n = new Set(prev); n.delete(fileId); return n; });
    }
  }, [batch, files, loadHistory]);

  useEffect(() => {
    if (!batch) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timer = window.setTimeout(() => drawerRef.current?.focus(), 0);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadHistory(batch.id);
    return () => {
      window.clearTimeout(timer);
      previousFocusRef.current?.focus();
      setFiles([]);
      setHistoryByFile({});
      setError(null);
    };
  }, [batch, loadHistory]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const focusable = drawerRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  if (!batch) return null;

  const totalRuns = Object.values(historyByFile).reduce((n, r) => n + r.length, 0);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <aside
        ref={drawerRef}
        className="relative flex h-full w-full max-w-xl flex-col border-l border-white/10 bg-sunken shadow-[0_0_60px_rgba(0,0,0,0.5)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-history-title"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-start gap-3 border-b border-white/10 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-indigo-500/25 bg-indigo-950/40 text-indigo-300">
            <History size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="batch-history-title" className="text-sm font-semibold text-white">QC history &amp; version diff</h2>
            <div className="mt-1 truncate font-mono text-xs text-slate-400" title={batch.parentBatchId}>
              {batch.parentBatchId}
            </div>
          </div>
          <button
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-white/[0.04] hover:text-slate-300"
            aria-label="Close history drawer"
          >
            <XCircle size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <RefreshCw size={14} className="animate-spin" /> Loading QC run history…
            </div>
          ) : error ? (
            <div className="rounded-lg border border-red-500/25 bg-red-950/20 p-4 text-sm text-red-200">
              Could not load history: {error}
            </div>
          ) : files.length === 0 ? (
            <div className="text-sm text-slate-500">No documents found for this batch.</div>
          ) : totalRuns === 0 ? (
            <div className="rounded-lg border border-white/10 bg-surface/60 p-4 text-sm text-slate-400">
              This batch has no completed QC runs yet. Run QC, then re-run it to compare versions here.
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-[11px] leading-relaxed text-slate-500">
                Each run is stamped with the rule-engine version. Expand a re-run to see which findings were added, removed,
                or changed versus the run it replaced — and whether the rule engine itself changed between them.
              </p>
              {files.map(f => (
                <FileHistory key={f.id} file={f} runs={historyByFile[f.id] ?? []}
                  onRerun={handleRerunFile} busy={rerunning.has(f.id)} />
              ))}
            </div>
          )}
        </div>

        {/* Findings export — the artifact the admin sends to the AMC manually. */}
        <div className="border-t border-white/10 p-4">
          <div className="mb-2 text-[11px] text-slate-500">
            Download structured findings (reviewer decisions reflected):
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => void handleExport("json")}
              disabled={downloading !== null}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 bg-surface px-3 text-sm text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white disabled:opacity-50"
            >
              <Download size={14} className={downloading === "json" ? "animate-pulse" : ""} /> JSON
            </button>
            <button
              type="button"
              onClick={() => void handleExport("csv")}
              disabled={downloading !== null}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-indigo-400/30 bg-indigo-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
            >
              <Download size={14} className={downloading === "csv" ? "animate-pulse" : ""} /> CSV
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

export default BatchHistoryDrawer;
