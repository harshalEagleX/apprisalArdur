import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface SpinnerProps {
  size?: number;
  className?: string;
}

export default function Spinner({ size = 16, className }: SpinnerProps) {
  return <Loader2 size={size} className={cn("animate-spin", className)} />;
}

export function PageSpinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <Loader2 size={24} className="animate-spin text-blue-500" />
      <span className="text-slate-500 text-sm">{label}</span>
    </div>
  );
}

export function InlineSpinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-slate-400 text-sm">
      <Loader2 size={13} className="animate-spin" />
      {label}
    </span>
  );
}
