export function adminBatchTimeline(_event: string, _payload: Record<string, unknown> = {}) {
  // intentionally no-op in all environments — timeline tracing removed
}

export function elapsedMs(startedAt: number) {
  return Math.round(performance.now() - startedAt);
}
