import { cn } from "@/lib/utils";

interface SpinnerProps {
  size?: number;
  className?: string;
}

export default function Spinner({ size = 16, className }: SpinnerProps) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block animate-spin rounded-full border-2 border-current border-t-transparent", className)}
      style={{ width: size, height: size }}
    />
  );
}

export function PageSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <Spinner size={24} className="text-blue-500" />
      <span className="text-slate-500 text-sm">{label}</span>
    </div>
  );
}

export function InlineSpinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-slate-400 text-sm">
      <Spinner size={13} />
      {label}
    </span>
  );
}
