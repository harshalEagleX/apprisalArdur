/**
 * Client-side job tracker for background operations.
 * Tracks active QC processing jobs so any component can show progress.
 */
export interface ActiveJob {
  id: string;           // unique key (e.g. "qc-42")
  label: string;        // "Processing batch EQSS-2024"
  current: number;      // processing units completed
  total: number;        // total processing units
  batchId: number;
  startedAt: number;    // Date.now()
  message?: string;
  stage?: string;
  modelLabel?: string;
  unitLabel?: string;
  detail?: string;
  subStage?: string | null;       // Python pipeline sub-stage (ocr_engagement, llm_enrichment, …)
  subMessage?: string | null;     // human-readable sub-stage description
  subPercent?: number;            // 0..1 progress within current sub-stage
  smoothedPercent?: number;       // server-computed smooth percent across files+sub-stage
}

type Listener = (jobs: ActiveJob[]) => void;

let jobs: ActiveJob[] = [];
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach(fn => fn([...jobs]));
}

export function trackJob(job: ActiveJob) {
  // Resume, don't reset: when the batches page remounts after a nav change it
  // re-tracks the same job id. Preserve the original startedAt (so elapsed keeps
  // counting) and never regress current/percent — otherwise the bar visibly
  // resets to 0% on every tab switch. The next poll fills in fresh values.
  const existing = jobs.find(j => j.id === job.id);
  const merged: ActiveJob = existing
    ? {
        ...existing,
        ...job,
        startedAt: existing.startedAt,
        current: Math.max(existing.current, job.current),
        smoothedPercent: job.smoothedPercent ?? existing.smoothedPercent,
        subPercent: job.subPercent ?? existing.subPercent,
        message: job.message ?? existing.message,
      }
    : job;
  jobs = [...jobs.filter(j => j.id !== job.id), merged];
  notify();
}

export function updateJob(id: string, current: number, total?: number, patch: Partial<ActiveJob> = {}) {
  jobs = jobs.map(j => j.id === id ? { ...j, ...patch, current, total: total ?? j.total } : j);
  notify();
}

export function removeJob(id: string) {
  jobs = jobs.filter(j => j.id !== id);
  notify();
}

export function subscribeJobs(fn: Listener) {
  listeners.add(fn);
  fn([...jobs]);
  return () => listeners.delete(fn);
}
