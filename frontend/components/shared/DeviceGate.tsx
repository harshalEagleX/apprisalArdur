"use client";
import { Monitor, Tablet, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

interface DeviceGateProps {
  children: React.ReactNode;
  minWidth?: number;
  title?: string;
  message?: string;
  allowTablet?: boolean;
}

export default function DeviceGate({
  children,
  minWidth = 768,
  title = "This workspace needs a larger screen",
  message = "This application is built for tablet and desktop workflows. Please switch to a tablet, laptop, or desktop for a reliable review experience.",
  allowTablet = true,
}: DeviceGateProps) {
  const [width, setWidth] = useState<number | null>(null);

  useEffect(() => {
    const update = () => setWidth(window.innerWidth);
    update();
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
    };
  }, []);

  if (width == null) {
    return <div className="foundation-grid min-h-screen bg-slate-950" />;
  }

  if (width < minWidth) {
    return (
      <main className="foundation-grid relative min-h-screen overflow-hidden bg-slate-950 px-5 py-8 text-white">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_25%,rgba(59,130,246,0.1),transparent_34%),linear-gradient(to_bottom,rgba(11,15,20,0.2),#0B0F14_78%)]" />
        <div className="relative mx-auto flex min-h-[calc(100vh-4rem)] max-w-sm flex-col justify-center">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-lg border border-blue-500/25 bg-blue-950/35 shadow-[0_0_28px_rgba(59,130,246,0.16)]">
            {allowTablet ? <Tablet size={22} className="text-blue-300" /> : <Monitor size={22} className="text-blue-300" />}
          </div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">Workspace guard</div>
          <h1 className="text-xl font-semibold leading-tight text-white">{title}</h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">{message}</p>

          <div className="mt-6 rounded-lg border border-white/10 bg-[#11161C]/95 p-4 shadow-[0_18px_45px_rgba(0,0,0,0.3)]">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <Monitor size={15} className="text-blue-300" />
              Supported screens
            </div>
            <div className="mt-3 grid gap-2 text-sm text-slate-400">
              {allowTablet && <SupportRow label="Tablet" value="768px and wider" />}
              <SupportRow label="Laptop" value="1024px and wider" />
              <SupportRow label="Desktop" value="1280px and wider" />
            </div>
          </div>

          <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-950/25 px-3 py-2 text-xs leading-relaxed text-amber-100">
            <RotateCcw size={14} className="mt-0.5 shrink-0" />
            <span>Rotating a tablet to landscape may unlock the workspace. Phone layouts are intentionally blocked to prevent broken review decisions.</span>
          </div>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}

function SupportRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-white/10 bg-[#161B22] px-3 py-2">
      <span>{label}</span>
      <span className="font-mono text-xs text-slate-500">{value}</span>
    </div>
  );
}
