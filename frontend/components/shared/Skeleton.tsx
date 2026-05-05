import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("foundation-shimmer rounded", className)} />
  );
}

export function TableSkeleton({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-0 divide-y divide-slate-800">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 px-4 py-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton
              key={c}
              className={`h-4 ${c === 0 ? "w-32" : c === cols - 1 ? "w-20" : "flex-1"}`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="rounded-lg border border-white/10 bg-[#11161C] p-4 space-y-3">
      <Skeleton className="h-7 w-16" />
      <Skeleton className="h-4 w-28" />
    </div>
  );
}
