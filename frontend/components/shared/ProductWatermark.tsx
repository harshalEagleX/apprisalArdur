export default function ProductWatermark() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed bottom-5 right-6 z-[90] select-none rounded-md border border-white/[0.06] bg-[#0B0F14]/45 px-2.5 py-1 text-[10px] font-medium tracking-normal text-slate-400/75 shadow-[0_8px_24px_rgba(0,0,0,0.18)] backdrop-blur-sm"
    >
      Product by Ardur Technology
    </div>
  );
}
