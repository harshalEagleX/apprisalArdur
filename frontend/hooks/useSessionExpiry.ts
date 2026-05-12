"use client";
import { useEffect, useState, useCallback } from "react";
import { sessionMsRemaining, logout } from "@/lib/api";

const WARNING_THRESHOLD_MS = 10 * 60 * 1_000; // show banner at 10 min remaining
const CHECK_INTERVAL_MS    =       60 * 1_000; // check every 60 s

export interface SessionExpiryState {
  /** Milliseconds until the session expires, or null if unknown. */
  msRemaining: number | null;
  /** True when < 10 minutes remain — use to show a warning banner. */
  isExpiringSoon: boolean;
  /** Logs out immediately and redirects to /login. */
  logoutNow: () => Promise<void>;
}

/**
 * Tracks the expected JWT cookie expiry time (stored in sessionStorage on login)
 * and raises isExpiringSoon when less than 10 minutes remain.
 *
 * Usage:
 *   const { isExpiringSoon, msRemaining, logoutNow } = useSessionExpiry();
 *   if (isExpiringSoon) show a "<X min> until session expires — save your work" banner.
 *
 * Note: because the JWT is stored in an HttpOnly cookie, JavaScript cannot inspect
 * the real cookie expiry. We track an estimated expiry from login time + 24 h.
 * A server-side 401 response (handled in apiFetch) is the authoritative signal.
 */
export function useSessionExpiry(): SessionExpiryState {
  const [msRemaining, setMsRemaining] = useState<number | null>(null);

  const tick = useCallback(() => {
    const ms = sessionMsRemaining();
    setMsRemaining(ms);
    if (ms !== null && ms <= 0) {
      // Session expired — redirect to login so the user gets a clear signal
      // rather than silent 401 failures on their next action.
      window.location.href = "/login?expired=1";
    }
  }, []);

  useEffect(() => {
    tick();
    const timer = setInterval(tick, CHECK_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [tick]);

  const logoutNow = useCallback(async () => {
    await logout();
    window.location.href = "/login";
  }, []);

  return {
    msRemaining,
    isExpiringSoon: msRemaining !== null && msRemaining <= WARNING_THRESHOLD_MS,
    logoutNow,
  };
}
