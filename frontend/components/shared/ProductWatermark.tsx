export default function ProductWatermark() {
  return (
    <div
      aria-hidden="true"
      // Bottom-LEFT + low z so this decorative mark never collides with (or sits above) the
      // interactive bottom-right overlays (ActivityMonitor pill, toasts). pointer-events-none
      // means it can never block a click regardless.
      className="pointer-events-none fixed bottom-4 left-4 z-20 select-none rounded-md border border-white/[0.06] bg-[#0B0F14]/45 px-2.5 py-1 text-[10px] font-medium tracking-normal text-slate-400/75 shadow-[0_8px_24px_rgba(0,0,0,0.18)] backdrop-blur-sm"
    >
      Product by Ardur Technology
    </div>
  );
}
