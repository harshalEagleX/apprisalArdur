"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getBatchStatus,
  getBatchQCProgress,
  type Batch,
} from "@/lib/api";
import { trackJob, updateJob, removeJob } from "@/lib/jobs";
import { toast } from "@/lib/toast";

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

function batchPollingLog(event: string, payload?: unknown) {
  if (process.env.NODE_ENV !== "production") {
    console.log(`[useBatchPolling] ${event}`, payload ?? "");
  }
}

export function useBatchPolling(
  batches: Batch[],
  onBatchComplete: (batchId: number, status: string) => void,
): UseBatchPollingReturn {
  const [progress, setProgress] = useState<Record<number, BatchProgress>>({});
  const [startedAt, setStartedAt] = useState<Record<number, number>>({});
  const pollingRef = useRef<Record<number, ReturnType<typeof setInterval>>>({});
  // Keep a stable ref to the latest onBatchComplete to avoid stale closure in poll()
  const onBatchCompleteRef = useRef(onBatchComplete);
  onBatchCompleteRef.current = onBatchComplete;

  const stopPolling = useCallback((batchId: number) => {
    const jobKey = `qc-${batchId}`;
    if (pollingRef.current[batchId]) {
      clearInterval(pollingRef.current[batchId]);
      delete pollingRef.current[batchId];
    }
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

    batchPollingLog("poll:start", { batchId, parentBatchId: batch.parentBatchId });

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
      }
    };

    void poll();
    const interval = setInterval(poll, 2000);
    pollingRef.current[batchId] = interval;
  }, [stopPolling]);

  // Auto-start polling for any batch already in QC_PROCESSING when the list loads
  useEffect(() => {
    batches.forEach(b => {
      if (b.status === "QC_PROCESSING" && !pollingRef.current[b.id]) {
        batchPollingLog("poll:auto-start", { batchId: b.id, parentBatchId: b.parentBatchId });
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
