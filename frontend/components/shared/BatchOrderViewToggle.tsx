"use client";
import { useRouter } from "next/navigation";

/**
 * Slider between the Batch view (logistics: what got uploaded, when, by whom)
 * and the Order view (the business entity: one row per real-world order, with
 * its documents/QC/status regardless of which batch(es) it came through).
 * Both views live under the single "Batches / Orders" nav item.
 */
export default function BatchOrderViewToggle({ active }: { active: "batch" | "order" }) {
  const router = useRouter();
  return (
    <div className="inline-flex items-center rounded-full border border-white/10 bg-[#0B0F14]/70 p-1 text-xs">
      <button
        onClick={() => router.push("/admin/batches")}
        className={`rounded-full px-3 py-1.5 font-medium transition-colors ${
          active === "batch" ? "bg-slate-600 text-white shadow-[0_0_14px_rgba(226,232,240,0.16)]" : "text-slate-500 hover:text-slate-300"
        }`}
      >
        Batch view
      </button>
      <button
        onClick={() => router.push("/admin/orders")}
        className={`rounded-full px-3 py-1.5 font-medium transition-colors ${
          active === "order" ? "bg-slate-600 text-white shadow-[0_0_14px_rgba(226,232,240,0.16)]" : "text-slate-500 hover:text-slate-300"
        }`}
      >
        Order view
      </button>
    </div>
  );
}
