"use client";
import { useEffect, useState, useRef } from "react";
import { getClientDashboard, getClientBatches, uploadBatch, getBatchStatus, type Batch } from "@/lib/api";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

export default function ClientPage() {
  const [tab, setTab]           = useState<"dashboard" | "upload" | "batches">("dashboard");
  const [dash, setDash]         = useState<Record<string, unknown>>({});
  const [batches, setBatches]   = useState<Batch[]>([]);
  const [file, setFile]         = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; msg: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getClientDashboard().then(setDash).catch(console.error);
    getClientBatches().then(p => setBatches(p.content)).catch(console.error);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true); setUploadMsg(null);
    try {
      const res = await uploadBatch(file);
      setUploadMsg({ ok: true, msg: `Batch "${res.parentBatchId}" uploaded with ${res.fileCount} files!` });
      setFile(null);
      getClientBatches().then(p => setBatches(p.content)).catch(console.error);
    } catch (err: unknown) {
      setUploadMsg({ ok: false, msg: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setUploading(false);
    }
  }

  const num = (k: string) => Number(dash[k] ?? 0);

  return (
    <div className="min-h-screen bg-slate-950 text-white flex">
      <aside className="w-52 flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-4 flex items-center gap-2 border-b border-slate-800">
          <div className="w-8 h-8 bg-blue-600 rounded font-bold text-sm flex items-center justify-center">A</div>
          <span className="font-semibold text-sm">Apprisal</span>
        </div>
        <nav className="p-2 flex-1 space-y-1">
          {(["dashboard","upload","batches"] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm capitalize transition-colors ${
                tab === t ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white hover:bg-slate-800"
              }`}>
              {t === "dashboard" ? "📊 Overview" : t === "upload" ? "📤 Upload" : "📦 My Batches"}
            </button>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-800">
          <a href="/login" className="text-slate-400 hover:text-white text-xs">Sign out</a>
        </div>
      </aside>

      <main className="flex-1 overflow-auto p-6">
        {tab === "dashboard" && (
          <div>
            <h1 className="text-xl font-bold mb-6">Client Dashboard</h1>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {[
                { label: "Total Batches", val: num("totalBatches"), color: "text-blue-400" },
                { label: "Completed",     val: num("completed"),    color: "text-green-400" },
                { label: "In Review",     val: num("inReview") + num("pendingReview"), color: "text-amber-400" },
                { label: "Processing",    val: num("processingOcr") + num("pendingOcr"), color: "text-cyan-400" },
              ].map(s => (
                <div key={s.label} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                  <div className={`text-2xl font-bold ${s.color}`}>{s.val}</div>
                  <div className="text-slate-400 text-sm mt-1">{s.label}</div>
                </div>
              ))}
            </div>
            <button onClick={() => setTab("upload")}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
              + Upload New Batch
            </button>
          </div>
        )}

        {tab === "upload" && (
          <div className="max-w-lg">
            <h1 className="text-xl font-bold mb-2">Upload Batch</h1>
            <p className="text-slate-400 text-sm mb-6">Upload a ZIP file containing appraisal, engagement letter, and contract PDFs.</p>

            {uploadMsg && (
              <div className={`mb-4 p-3 rounded-lg text-sm ${uploadMsg.ok ? "bg-green-900/40 border border-green-700 text-green-300" : "bg-red-900/40 border border-red-700 text-red-300"}`}>
                {uploadMsg.msg}
              </div>
            )}

            <form onSubmit={submit} className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
              <div
                onClick={() => fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f?.name.endsWith(".zip")) setFile(f); }}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                  file ? "border-blue-500 bg-blue-900/20" : "border-slate-700 hover:border-blue-600"
                }`}
              >
                <input ref={fileRef} type="file" accept=".zip" className="hidden"
                  onChange={e => setFile(e.target.files?.[0] ?? null)} />
                <div className="text-3xl mb-2">📦</div>
                {file ? (
                  <div>
                    <div className="font-medium text-blue-300">{file.name}</div>
                    <div className="text-xs text-slate-400 mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
                  </div>
                ) : (
                  <div>
                    <div className="font-medium text-slate-300">Drop your ZIP file here</div>
                    <div className="text-xs text-slate-500 mt-1">or click to browse</div>
                  </div>
                )}
              </div>

              <div className="bg-slate-800 rounded-lg p-3 text-xs text-slate-400 space-y-1">
                <div className="font-medium text-slate-300 mb-2">Required folder structure:</div>
                <pre className="font-mono text-green-400">{`BATCH_2025_001/
├── appraisal/   ← appraisal PDFs
├── engagement/  ← order form PDFs
└── contract/    ← purchase contract PDFs`}</pre>
              </div>

              <button type="submit" disabled={!file || uploading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white py-2.5 rounded-lg font-medium transition-colors flex items-center justify-center gap-2">
                {uploading ? <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" /> : "📤"}
                {uploading ? "Uploading…" : "Upload Batch"}
              </button>
            </form>
          </div>
        )}

        {tab === "batches" && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h1 className="text-xl font-bold">My Batches</h1>
              <button onClick={() => setTab("upload")} className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg">
                + Upload New
              </button>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-800 text-slate-400 text-xs uppercase">
                  <tr>{["Batch ID","Status","Files","Uploaded","Updated"].map(h => (
                    <th key={h} className="px-4 py-3 text-left">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {batches.length === 0 ? (
                    <tr><td colSpan={5} className="text-center py-8 text-slate-500">
                      No batches yet. <button onClick={() => setTab("upload")} className="text-blue-400">Upload one →</button>
                    </td></tr>
                  ) : batches.map(b => (
                    <tr key={b.id} className="hover:bg-slate-800/40">
                      <td className="px-4 py-3 font-mono text-xs">{b.parentBatchId}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          b.status === "COMPLETED" ? "bg-green-900 text-green-300" :
                          b.status.includes("ERROR") || b.status.includes("FAILED") ? "bg-red-900 text-red-300" :
                          b.status.includes("REVIEW") ? "bg-amber-900 text-amber-300" : "bg-blue-900 text-blue-300"
                        }`}>{b.status}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{b.files?.length ?? 0}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{new Date(b.createdAt).toLocaleDateString()}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{new Date(b.updatedAt).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
