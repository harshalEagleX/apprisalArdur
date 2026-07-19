/**
 * Background-job tracker.
 *
 * The behaviour worth protecting is stated in trackJob's own comment: a remount
 * must RESUME a job, not reset it. Get that wrong and the progress bar visibly
 * snaps back to 0% every time the reviewer switches tabs — which reads as "the
 * system restarted my work".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  type ActiveJob,
  removeJob,
  subscribeJobs,
  trackJob,
  updateJob,
} from "@/lib/jobs";

function job(over: Partial<ActiveJob> = {}): ActiveJob {
  return {
    id: "qc-1", label: "Processing batch", current: 0, total: 10,
    batchId: 1, startedAt: 1_000, ...over,
  };
}

/** Read current jobs via a one-shot subscription (the module has no getter). */
function current(): ActiveJob[] {
  let seen: ActiveJob[] = [];
  const off = subscribeJobs(j => { seen = j; });
  off();
  return seen;
}

afterEach(() => {
  for (const j of current()) removeJob(j.id);
});

describe("trackJob", () => {
  it("adds a new job", () => {
    trackJob(job());
    expect(current()).toHaveLength(1);
    expect(current()[0].id).toBe("qc-1");
  });

  it("keeps the ORIGINAL startedAt on re-track so elapsed keeps counting", () => {
    trackJob(job({ startedAt: 1_000 }));
    trackJob(job({ startedAt: 9_999 }));   // remount re-tracks the same id
    expect(current()[0].startedAt).toBe(1_000);
  });

  it("never regresses progress on re-track", () => {
    // The reset-to-0% bug: a remount re-tracks with current=0 before the next
    // poll refills it. Max() is what keeps the bar from snapping backwards.
    trackJob(job({ current: 7 }));
    trackJob(job({ current: 0 }));
    expect(current()[0].current).toBe(7);
  });

  it("keeps existing smoothedPercent / subPercent / message when the new job omits them", () => {
    trackJob(job({ smoothedPercent: 0.6, subPercent: 0.3, message: "reading" }));
    trackJob(job({}));
    const j = current()[0];
    expect(j.smoothedPercent).toBe(0.6);
    expect(j.subPercent).toBe(0.3);
    expect(j.message).toBe("reading");
  });

  it("takes the NEW value when the re-track supplies one", () => {
    trackJob(job({ smoothedPercent: 0.2, message: "old" }));
    trackJob(job({ smoothedPercent: 0.8, message: "new" }));
    const j = current()[0];
    expect(j.smoothedPercent).toBe(0.8);
    expect(j.message).toBe("new");
  });

  it("does not duplicate a job id", () => {
    trackJob(job());
    trackJob(job());
    expect(current()).toHaveLength(1);
  });

  it("keeps separate jobs apart", () => {
    trackJob(job({ id: "qc-1" }));
    trackJob(job({ id: "qc-2" }));
    expect(current().map(j => j.id).sort()).toEqual(["qc-1", "qc-2"]);
  });
});

describe("updateJob", () => {
  it("updates progress and keeps total when not supplied", () => {
    trackJob(job({ current: 1, total: 10 }));
    updateJob("qc-1", 5);
    expect(current()[0]).toMatchObject({ current: 5, total: 10 });
  });

  it("updates total when supplied and merges a patch", () => {
    trackJob(job());
    updateJob("qc-1", 3, 20, { stage: "rules", message: "checking" });
    expect(current()[0]).toMatchObject({ current: 3, total: 20, stage: "rules", message: "checking" });
  });

  it("is a no-op for an unknown id", () => {
    trackJob(job());
    updateJob("nope", 99);
    expect(current()[0].current).toBe(0);
  });
});

describe("removeJob", () => {
  it("removes only the named job", () => {
    trackJob(job({ id: "qc-1" }));
    trackJob(job({ id: "qc-2" }));
    removeJob("qc-1");
    expect(current().map(j => j.id)).toEqual(["qc-2"]);
  });
});

describe("subscribeJobs", () => {
  it("pushes the current list immediately on subscribe", () => {
    trackJob(job());
    const fn = vi.fn();
    const off = subscribeJobs(fn);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn.mock.calls[0][0]).toHaveLength(1);
    off();
  });

  it("notifies every subscriber on change", () => {
    const a = vi.fn(); const b = vi.fn();
    const offA = subscribeJobs(a); const offB = subscribeJobs(b);
    trackJob(job());
    expect(a).toHaveBeenCalledTimes(2);   // initial + change
    expect(b).toHaveBeenCalledTimes(2);
    offA(); offB();
  });

  it("stops notifying after unsubscribe", () => {
    const fn = vi.fn();
    subscribeJobs(fn)();                  // subscribe then immediately unsubscribe
    trackJob(job());
    expect(fn).toHaveBeenCalledTimes(1);  // only the initial push
  });

  it("hands out a COPY so a subscriber cannot mutate internal state", () => {
    trackJob(job());
    const seen = current();
    seen.length = 0;
    expect(current()).toHaveLength(1);
  });
});
