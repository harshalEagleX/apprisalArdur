"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, ChevronRight, Package, FileText, CheckCircle2,
  AlertCircle, Clock, UserCheck, AlertTriangle, RefreshCw,
} from "lucide-react";
import { getBatchById, getQCResults, type Batch, type QCResult } from "@/lib/api";
import { TableSkeleton, Skeleton } from "@/components/shared/Skeleton";
import StatusBadge from "@/components/shared/StatusBadge";
import EmptyState from "@/components/shared/EmptyState";
import { toast } from "@/lib/toast";
import { displayName } from "@/lib/displayName";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function BatchDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [batch, setBatch]       = useState<Batch | null>(null);
  const [results, setResults]   = useState<QCResult[]>([]);
  const [loading, setLoading]   = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [b, qc] = await Promise.all([
        getBatchById(id),
        getQCResults(id).catch(() => [] as QCResult[]),
      ]);
      setBatch(b);
      setResults(qc);
    } catch {
      toast.error("Failed to load batch detail");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    const t = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(t);
  }, [load]);

  const resultMap = new Map(results.map(r => [r.batchFile?.id, r]));
  const files = batch?.files ?? [];

  const totalFiles = files.length;
  const passed = results.filter(r => r.finalDecision === "PASS").length;
  const failed = results.filter(r => r.finalDecision === "FAIL").length;
  const pending = results.filter(r => !r.finalDecision && r.qcDecision !== "AUTO_PASS").length;

  return (
    <div className="w-full max-w-[1800px] p-6 lg:p-8">
      {/* Breadcrumb */}
      <nav className="mb-4 flex items-center gap-1.5 text-xs text-slate-500">
        <Link href="/admin/batches" className="inline-flex items-center gap-1 transition-colors hover:text-slate-300">
          <ArrowLeft size={12} /> Batches
        </Link>
        <ChevronRight size={12} className="text-slate-600" />
        <span className="text-slate-300 truncate max-w-[320px]">
          {loading ? "Loading…" : batch?.parentBatchId ?? `Batch #${id}`}
        </span>
      </nav>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-[#161B22]">
            <Package size={18} className="text-slate-400" />
          </div>
          <div className="min-w-0">
            {loading ? (
              <Skeleton className="h-6 w-64" />
            ) : (
              <h1 className="font-mono text-lg font-semibold text-white">{batch?.parentBatchId ?? `Batch #${id}`}</h1>
            )}
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              {batch?.client && <span>{batch.client.name}</span>}
              {batch?.assignedReviewer && (
                <>
                  <span className="text-slate-700">·</span>
                  <span className="flex items-center gap-1">
                    <UserCheck size={11} className="text-slate-600" />
                    {batch.assignedReviewer.fullName ?? displayName(batch.assignedReviewer.username)}
                  </span>
                </>
              )}
              {batch?.createdAt && (
                <>
                  <span className="text-slate-700">·</span>
                  <span>{new Date(batch.createdAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {batch?.status && <StatusBadge status={batch.status} />}
          <button
            onClick={() => load()}
            className="flex h-8 items-center gap-1.5 rounded-md border border-white/10 bg-[#11161C] px-3 text-xs text-slate-400 transition-colors hover:text-white"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </header>

      {/* Intake warnings */}
      {batch?.intakeWarnings && (
        <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-amber-500/25 bg-amber-950/20 px-4 py-3 text-sm text-amber-200">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Intake warnings</div>
            <div className="mt-1 text-[12px] leading-relaxed opacity-90 whitespace-pre-line">{batch.intakeWarnings}</div>
          </div>
        </div>
      )}

      {/* Stats row */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Files" value={loading ? "—" : String(totalFiles)} icon={FileText} />
        <Stat label="Passed" value={loading ? "—" : String(passed)} icon={CheckCircle2} tone="text-green-300" />
        <Stat label="Failed" value={loading ? "—" : String(failed)} icon={AlertCircle} tone="text-red-300" />
        <Stat label="Pending" value={loading ? "—" : String(pending)} icon={Clock} tone="text-amber-300" />
      </div>

      {/* Per-file table */}
      <section className="overflow-hidden rounded-xl border border-white/10 bg-[#11161C]">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
            <FileText size={15} className="text-slate-400" /> Files in this batch
            {!loading && <span className="text-[11px] font-normal text-slate-500">({files.length})</span>}
          </h2>
        </div>

        {loading ? (
          <div className="p-4"><TableSkeleton rows={6} cols={5} /></div>
        ) : files.length === 0 ? (
          <EmptyState icon={FileText} title="No files" description="This batch has no attached files." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-[11px] uppercase tracking-wide text-slate-500">
                <th className="px-5 py-2.5 font-medium">File</th>
                <th className="px-4 py-2.5 font-medium">Type</th>
                <th className="px-4 py-2.5 font-medium">QC status</th>
                <th className="px-4 py-2.5 text-right font-medium">Issues / Review / Clear</th>
                <th className="px-4 py-2.5 text-right font-medium">Size</th>
                <th className="px-4 py-2.5 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {files.map(f => {
                const qc = resultMap.get(f.id);
                const hasIssues = (qc?.failedCount ?? 0) > 0;
                return (
                  <tr key={f.id} className="transition-colors hover:bg-white/[0.03]">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span className={`h-2 w-2 shrink-0 rounded-full ${hasIssues ? "bg-red-400" : qc ? "bg-green-400" : "bg-slate-600"}`} />
                        <span className="truncate font-medium text-slate-200 max-w-[280px]" title={f.filename}>{f.filename}</span>
                      </div>
                      {f.orderId && <div className="ml-4 mt-0.5 text-[11px] text-slate-600">Order {f.orderId}</div>}
                    </td>
                    <td className="px-4 py-3 text-[12px] text-slate-500">
                      {f.fileType === "APPRAISAL" ? "Appraisal" : f.fileType === "ENGAGEMENT" ? "Engagement" : "Contract"}
                    </td>
                    <td className="px-4 py-3">
                      {qc ? <StatusBadge status={qc.finalDecision ?? qc.qcDecision} size="xs" /> : (
                        <span className="text-[11px] text-slate-600">{f.status?.replace(/_/g, " ") ?? "—"}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {qc ? (
                        <span className="flex items-center justify-end gap-2 tabular-nums text-[12px]">
                          <span className={qc.failedCount > 0 ? "text-red-300" : "text-slate-600"}>{qc.failedCount}</span>
                          <span className="text-slate-600">/</span>
                          <span className={qc.verifyCount > 0 ? "text-amber-300" : "text-slate-600"}>{qc.verifyCount}</span>
                          <span className="text-slate-600">/</span>
                          <span className="text-green-300">{qc.passedCount}</span>
                        </span>
                      ) : <span className="text-slate-600 text-[12px]">—</span>}
                    </td>
                    <td className="px-4 py-3 text-right text-[11px] text-slate-500 tabular-nums">
                      {f.fileSize ? `${(f.fileSize / 1024 / 1024).toFixed(1)} MB` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {qc && (
                        <Link
                          href={`${JAVA}/api/reviewer/qc/${qc.id}/rules`}
                          className="text-[11px] text-slate-500 transition-colors hover:text-indigo-300"
                          target="_blank"
                        >
                          Rules ↗
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* Error message */}
      {batch?.errorMessage && (
        <div className="mt-5 flex items-start gap-2.5 rounded-lg border border-red-500/25 bg-red-950/20 px-4 py-3 text-sm text-red-200">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Processing error</div>
            <div className="mt-1 font-mono text-[11px] leading-relaxed">{batch.errorMessage}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, icon: Icon, tone = "text-white" }: {
  label: string; value: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-[#11161C] p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        <Icon size={13} /> {label}
      </div>
      <div className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}
