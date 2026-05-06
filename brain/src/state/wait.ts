export async function waitFor<T>(
  label: string,
  poll: () => Promise<T>,
  accept: (value: T) => boolean,
  options: { timeoutMs: number; intervalMs?: number }
): Promise<T> {
  const started = Date.now();
  const intervalMs = options.intervalMs ?? 3_000;
  let lastValue: T | undefined;
  while (Date.now() - started < options.timeoutMs) {
    lastValue = await poll();
    if (accept(lastValue)) return lastValue;
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out waiting for ${label}. Last value: ${JSON.stringify(lastValue)}`);
}
