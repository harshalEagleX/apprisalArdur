"use client";
import React from "react";
import type { Batch, User } from "@/lib/api";

function displayUser(user: User): string {
  return user.fullName || user.username;
}

function formatAge(value?: string): string {
  if (!value) return "Age unknown";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "Just updated";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${Math.max(minutes, 1)}m waiting`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h waiting`;
  return `${Math.floor(hours / 24)}d waiting`;
}

export interface ReviewerAssignControlProps {
  batch: Batch;
  reviewers: User[];
  workload: Record<string, number>;
  disabled: boolean;
  onAssign: (reviewerId: number) => void;
}

export function ReviewerAssignControl({
  batch,
  reviewers,
  workload,
  disabled,
  onAssign,
}: ReviewerAssignControlProps) {
  const ranked = reviewers
    .map(reviewer => {
      const active = Number(workload[String(reviewer.id)] ?? workload[reviewer.id] ?? 0);
      const sameClient = Boolean(
        reviewer.client?.id && batch.client?.id && reviewer.client.id === batch.client.id
      );
      return { reviewer, active, sameClient };
    })
    .sort(
      (a, b) =>
        Number(b.sameClient) - Number(a.sameClient) ||
        a.active - b.active ||
        displayUser(a.reviewer).localeCompare(displayUser(b.reviewer))
    );

  const recommended = ranked[0];
  const age = formatAge(batch.updatedAt ?? batch.createdAt);

  return (
    <div className="min-w-[210px] rounded-md border border-slate-800 bg-slate-950/60 p-2">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wide text-slate-500">Assign reviewer</span>
        <span className="text-[10px] text-amber-300">{age}</span>
      </div>
      <select
        defaultValue=""
        onChange={e => e.target.value && onAssign(Number(e.target.value))}
        disabled={disabled}
        className="h-8 w-full rounded-md border border-slate-700 bg-slate-800 px-2 text-xs text-slate-300 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-40"
        aria-label={`Assign reviewer for ${batch.parentBatchId}`}
      >
        <option value="">Assign…</option>
        {ranked.map(({ reviewer, active, sameClient }) => (
          <option key={reviewer.id} value={reviewer.id}>
            {displayUser(reviewer)} · {active} active{sameClient ? " · client fit" : ""}
          </option>
        ))}
      </select>
      {recommended && (
        <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px]">
          <span className="truncate text-blue-300">
            Recommended: {displayUser(recommended.reviewer)}
          </span>
          <span className="shrink-0 text-slate-500">{recommended.active} active</span>
        </div>
      )}
    </div>
  );
}

export default ReviewerAssignControl;
