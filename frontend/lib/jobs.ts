/**
 * Client-side job tracker for background operations.
 * Tracks active QC processing jobs so any component can show progress.
 */
export interface ActiveJob {
  id: string;           // unique key (e.g. "qc-42")
  label: string;        // "Processing batch EQSS-2024"
  current: number;      // files processed
  total: number;        // total files in batch
  batchId: number;
  startedAt: number;    // Date.now()
}

type Listener = (jobs: ActiveJob[]) => void;

let jobs: ActiveJob[] = [];
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach(fn => fn([...jobs]));
}

export function trackJob(job: ActiveJob) {
  jobs = [...jobs.filter(j => j.id !== job.id), job];
  notify();
}

export function updateJob(id: string, current: number) {
  jobs = jobs.map(j => j.id === id ? { ...j, current } : j);
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
