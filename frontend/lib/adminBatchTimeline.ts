const FLOW = "admin_batches";
const PID = typeof window === "undefined"
  ? "server"
  : `browser-${Math.random().toString(36).slice(2, 8)}`;

export function adminBatchTimeline(event: string, payload: Record<string, unknown> = {}) {
  if (typeof window === "undefined") return;

  const entry = {
    flow: FLOW,
    event,
    ist: new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }),
    pid: PID,
    path: window.location.pathname + window.location.search,
    ...payload,
  };

  console.log("[admin-batches-timeline]", entry);
}

export function elapsedMs(startedAt: number) {
  return Math.round(performance.now() - startedAt);
}
