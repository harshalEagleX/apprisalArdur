"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getBatchStatus,
  getBatchQCProgress,
  type Batch,
} from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import { trackJob, updateJob, removeJob } from "@/lib/jobs";
import { toast } from "@/lib/toast";
import { adminBatchTimeline, elapsedMs } from "@/lib/adminBatchTimeline";

export interface BatchProgress {
  current: number;
  total: number;
  message: string;
  stage: string;
  percent: number;
  modelProvider?: string;
  modelName?: string;
  visionModel?: string;
  subStage?: string | null;
  subMessage?: string | null;
  subPercent?: number;
  smoothedPercent?: number;
}

export interface UseBatchPollingReturn {
  progress: Record<number, BatchProgress>;
  startedAt: Record<number, number>;
  startPolling: (batch: Batch) => void;
  stopPolling: (batchId: number) => void;
}

function batchPollingLog(...args: unknown[]) {
  void args;
  // no-op
}

export function useBatchPolling(
  batches: Batch[],
  onBatchComplete: (batchId: number, status: string) => void,
): UseBatchPollingReturn {
  const [progress, setProgress] = useState<Record<number, BatchProgress>>({});
  const [startedAt, setStartedAt] = useState<Record<number, number>>({});
  const pollingRef = useRef<Record<number, ReturnType<typeof setInterval>>>({});
  const pollingStartedPerfRef = useRef<Record<number, number>>({});
  // Per-batch refresh fn so a WebSocket progress event can pull fresh state on
  // demand; the active-batch ids drive the WS topic subscriptions below.
  const refreshFnRef = useRef<Record<number, () => void>>({});
  const [activeIds, setActiveIds] = useState<number[]>([]);
  // Keep a stable ref to the latest onBatchComplete to avoid stale closure in poll()
  const onBatchCompleteRef = useRef(onBatchComplete);

  useEffect(() => {
    onBatchCompleteRef.current = onBatchComplete;
  }, [onBatchComplete]);

  const stopPolling = useCallback((batchId: number) => {
    const jobKey = `qc-${batchId}`;
    adminBatchTimeline("frontend_poll_stop", {
      batch_id: batchId,
      elapsed_ms: pollingStartedPerfRef.current[batchId] ? elapsedMs(pollingStartedPerfRef.current[batchId]) : undefined,
    });
    if (pollingRef.current[batchId]) {
      clearInterval(pollingRef.current[batchId]);
      delete pollingRef.current[batchId];
    }
    delete pollingStartedPerfRef.current[batchId];
    delete refreshFnRef.current[batchId];
    setActiveIds(ids => ids.filter(x => x !== batchId));
    removeJob(jobKey);
    setProgress(p => {
      const n = { ...p };
      delete n[batchId];
      return n;
    });
    setStartedAt(p => {
      const n = { ...p };
      delete n[batchId];
      return n;
    });
  }, []);

  const startPolling = useCallback((batch: Batch) => {
    const batchId = batch.id;
    if (pollingRef.current[batchId]) return; // already polling

    const jobKey = `qc-${batchId}`;
    const appraisalFiles = batch.files?.filter(f => f.fileType === "APPRAISAL") ?? [];
    const initialTotal = appraisalFiles.length > 0 ? appraisalFiles.length : 1;
    const batchFileCount = batch.fileCount ?? batch.files?.length ?? 0;
    const now = Date.now();
    const startedPerf = performance.now();
    pollingStartedPerfRef.current[batchId] = startedPerf;

    batchPollingLog("poll:start", { batchId, parentBatchId: batch.parentBatchId });
    adminBatchTimeline("frontend_poll_start", {
      batch_id: batchId,
      batch_ref: batch.parentBatchId,
      current_status: batch.status,
      appraisal_file_count: appraisalFiles.length,
      uploaded_file_count: batchFileCount,
    });

    trackJob({
      id: jobKey,
      label: `QC: ${batch.parentBatchId}`,
      current: 0,
      total: initialTotal,
      batchId,
      startedAt: now,
      message: "Starting QC processing",
      unitLabel: "appraisal set",
      detail: `${batchFileCount} uploaded file${batchFileCount === 1 ? "" : "s"} in this batch`,
    });

    setStartedAt(p => ({ ...p, [batchId]: now }));

    const poll = async () => {
      try {
        const [statusRes, progressRes] = await Promise.all([
          getBatchStatus(batchId),
          getBatchQCProgress(batchId),
        ]);
        batchPollingLog("poll:tick", { batchId, status: statusRes.status });

        const total = Math.max(
          progressRes.total || statusRes.processingTotalFiles || appraisalFiles.length || 1,
          1
        );
        const done = Math.min(Math.max(progressRes.current, statusRes.completedFiles ?? 0), total);
        const modelLabel = progressRes.modelName
          ? `${progressRes.modelProvider ?? "model"}: ${progressRes.modelName}`
          : undefined;
        const subPercent = Math.max(0, Math.min(1, progressRes.subPercent ?? 0));
        const clientSmoothed = Math.min(100, Math.round(((done + subPercent) / total) * 100));
        const smoothedPercent = progressRes.smoothedPercent ?? clientSmoothed;
        adminBatchTimeline("frontend_poll_tick", {
          batch_id: batchId,
          batch_ref: batch.parentBatchId,
          status: statusRes.status,
          stage: progressRes.stage,
          message: progressRes.message,
          current: done,
          total,
          percent: progressRes.percent,
          smoothed_percent: smoothedPercent,
          sub_stage: progressRes.subStage,
          sub_percent: progressRes.subPercent,
          elapsed_ms: elapsedMs(startedPerf),
        });

        updateJob(jobKey, done, total, {
          message: progressRes.message || "QC processing is running",
          stage: progressRes.stage || "processing",
          modelLabel,
          unitLabel: total === 1 ? "appraisal set" : "appraisal sets",
          detail: `${statusRes.totalFiles ?? batchFileCount} uploaded file${(statusRes.totalFiles ?? batchFileCount) === 1 ? "" : "s"} in this batch`,
          subStage: progressRes.subStage ?? null,
          subMessage: progressRes.subMessage ?? null,
          subPercent,
          smoothedPercent,
        });

        setProgress(p => ({
          ...p,
          [batchId]: {
            current: done,
            total,
            message: progressRes.message || "QC processing is running",
            stage: progressRes.stage || "processing",
            percent: progressRes.percent ?? Math.round((done / total) * 100),
            smoothedPercent,
            subStage: progressRes.subStage ?? null,
            subMessage: progressRes.subMessage ?? null,
            subPercent,
            modelProvider: progressRes.modelProvider,
            modelName: progressRes.modelName,
            visionModel: progressRes.visionModel,
          },
        }));

        if (statusRes.status !== "QC_PROCESSING") {
          adminBatchTimeline("frontend_poll_complete", {
            batch_id: batchId,
            batch_ref: batch.parentBatchId,
            final_status: statusRes.status,
            current: done,
            total,
            elapsed_ms: elapsedMs(startedPerf),
          });
          stopPolling(batchId);

          if (statusRes.status === "COMPLETED" || statusRes.status === "REVIEW_PENDING") {
            toast.success(
              `Batch "${batch.parentBatchId}" QC complete`,
              `${done} file${done !== 1 ? "s" : ""} processed`
            );
          } else if (statusRes.status === "ERROR") {
            toast.error(
              `Batch "${batch.parentBatchId}" failed`,
              "Check the error details in the batch list"
            );
          } else if (statusRes.status === "UPLOADED") {
            toast.info(
              `Batch "${batch.parentBatchId}" QC stopped`,
              "Run QC is available again"
            );
          }

          onBatchCompleteRef.current(batchId, statusRes.status);
        }
      } catch (e) {
        batchPollingLog("poll:error", { batchId, error: e });
        adminBatchTimeline("frontend_poll_error", {
          batch_id: batchId,
          batch_ref: batch.parentBatchId,
          elapsed_ms: elapsedMs(startedPerf),
          error: e instanceof Error ? e.message : String(e),
        });
      }
    };

    // WebSocket pushes a progress event the instant the backend records one
    // (QCProcessingService publishes /topic/qc/batch/{id}/progress). On that
    // signal we refresh immediately, so live updates no longer depend on the
    // timer. The interval is now a slow safety net (reconnect gaps + terminal-
    // status detection) rather than the primary mechanism — 2s -> 10s cuts the
    // steady-state request volume ~5x per watched batch.
    refreshFnRef.current[batchId] = () => { void poll(); };
    setActiveIds(ids => (ids.includes(batchId) ? ids : [...ids, batchId]));

    void poll();
    const interval = setInterval(poll, 10000);
    pollingRef.current[batchId] = interval;
  }, [stopPolling]);

  // Live progress over the existing WebSocket pub/sub (same channel the reviewer
  // queue uses). A message on a batch's progress topic triggers an immediate
  // refresh via that batch's poll fn; no payload mapping needed — the proven
  // status+progress fetch supplies the data.
  const progressTopics = useMemo(
    () => activeIds.map(id => `/topic/qc/batch/${id}/progress`),
    [activeIds],
  );
  useWebSocket(
    progressTopics,
    useCallback((topic: string) => {
      const m = topic.match(/\/topic\/qc\/batch\/(\d+)\/progress/);
      if (m) refreshFnRef.current[Number(m[1])]?.();
    }, []),
  );

  // Auto-start polling for any batch already in QC_PROCESSING when the list loads
  useEffect(() => {
    batches.forEach(b => {
      if (b.status === "QC_PROCESSING" && !pollingRef.current[b.id]) {
        batchPollingLog("poll:auto-start", { batchId: b.id, parentBatchId: b.parentBatchId });
        adminBatchTimeline("frontend_poll_auto_start", {
          batch_id: b.id,
          batch_ref: b.parentBatchId,
          status: b.status,
        });
        startPolling(b);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batches]);

  // Cleanup all intervals on unmount
  useEffect(() => {
    const polling = pollingRef.current;
    return () => {
      Object.values(polling).forEach(clearInterval);
    };
  }, []);

  return { progress, startedAt, startPolling, stopPolling };
}

export default useBatchPolling;
