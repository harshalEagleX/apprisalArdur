"use client";
import { useCallback, useEffect, useState } from "react";
import { startReviewSession, heartbeatReviewSession } from "@/lib/api";

export interface UseReviewSessionReturn {
  sessionToken: string | null;
  sessionError: string | null;
  sessionAckRequired: boolean;
  isReady: boolean;
  beginSession: (acknowledgeExistingLock?: boolean) => Promise<void>;
  clearError: () => void;
}

export function useReviewSession(qcResultId: number): UseReviewSessionReturn {
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionAckRequired, setSessionAckRequired] = useState(false);

  const beginSession = useCallback(async (acknowledgeExistingLock = false) => {
    try {
      const session = await startReviewSession(qcResultId, acknowledgeExistingLock);
      setSessionToken(session.sessionToken);
      setSessionAckRequired(false);
      const priorCount = Number(session.priorActionCount ?? 0);
      setSessionError(
        session.lockAcknowledged || priorCount > 0
          ? `You are continuing a report with ${priorCount} prior saved decision${priorCount === 1 ? "" : "s"}. Review existing decisions before sign-off.`
          : null
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to start review session.";
      setSessionToken(null);
      setSessionError(message);
      setSessionAckRequired(
        message.includes("previous review session") ||
          message.includes("server-saved decision")
      );
    }
  }, [qcResultId]);

  // Start session on mount
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      beginSession().finally(() => {
        if (cancelled) setSessionToken(null);
      });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [beginSession]);

  // Heartbeat every 120s while session is active
  useEffect(() => {
    if (!sessionToken) return;
    const timer = window.setInterval(() => {
      heartbeatReviewSession(qcResultId, sessionToken).catch(error => {
        setSessionError(
          error instanceof Error
            ? error.message
            : "Review session timed out. Reload to resume."
        );
      });
    }, 120_000);
    return () => window.clearInterval(timer);
  }, [qcResultId, sessionToken]);

  const clearError = useCallback(() => setSessionError(null), []);

  return {
    sessionToken,
    sessionError,
    sessionAckRequired,
    isReady: sessionToken !== null,
    beginSession,
    clearError,
  };
}

export default useReviewSession;
