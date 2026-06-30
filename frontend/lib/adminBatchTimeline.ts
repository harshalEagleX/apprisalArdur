export function adminBatchTimeline(...args: unknown[]) {
  void args;
  // intentionally no-op in all environments — timeline tracing removed
}

export function elapsedMs(startedAt: number) {
  return Math.round(performance.now() - startedAt);
}
