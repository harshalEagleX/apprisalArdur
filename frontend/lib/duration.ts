/**
 * Human-readable duration formatting for the docStats views.
 *
 * The backend stores real measured milliseconds (sub-millisecond precision for
 * fast rules). These helpers turn raw ms into the units a human reads at a
 * glance — µs / ms / s / min — without losing the truth of the measurement.
 */

export function fmtMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1) return `${Math.round(ms * 1000)} µs`;
  if (ms < 1000) return ms < 10 ? `${ms.toFixed(1)} ms` : `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 2 : 1)} s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m} min ${rem} s`;
}

/** LLM $ cost. Per-document costs are fractions of a cent, so show enough
 *  precision to be non-zero (e.g. $0.0043) while keeping larger sums readable. */
export function fmtCost(usd: number | null | undefined): string {
  if (usd == null || Number.isNaN(usd)) return "—";
  if (usd === 0) return "$0";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

/** Token counts: 1234 → "1.2k", 1_200_000 → "1.2M". */
export function fmtTokens(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

/** Compact form for tight table cells (no unit spacing). */
export function fmtMsCompact(ms: number | null | undefined): string {
  return fmtMs(ms).replace(" ", " "); // narrow no-break space
}

/** A tailwind text-color class keyed to how slow something is, for quick scan. */
export function durationTone(ms: number | null | undefined): string {
  if (ms == null) return "text-slate-500";
  if (ms >= 10000) return "text-red-300";
  if (ms >= 1000) return "text-amber-300";
  if (ms >= 100) return "text-sky-300";
  return "text-slate-300";
}
