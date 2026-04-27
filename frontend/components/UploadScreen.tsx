"use client";

import { useState, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import type { QCResults } from "@/lib/legacy-types";

const API = process.env.NEXT_PUBLIC_PYTHON_URL || "http://localhost:5001";

type FileEntry = { file: File; key: string };
type Stage = "idle" | "uploading" | "ocr" | "rules" | "done" | "error";

type Props = { onResults: (data: QCResults, filename: string) => void };

export default function UploadScreen({ onResults }: Props) {
  const [appraisal,    setAppraisal]    = useState<FileEntry | null>(null);
  const [engagement,   setEngagement]   = useState<FileEntry | null>(null);
  const [contract,     setContract]     = useState<FileEntry | null>(null);
  const [stage,        setStage]        = useState<Stage>("idle");
  const [progress,     setProgress]     = useState(0);
  const [progressMsg,  setProgressMsg]  = useState("");
  const [error,        setError]        = useState("");
  const appraisalRef = useRef<HTMLInputElement>(null);
  const engRef       = useRef<HTMLInputElement>(null);
  const conRef       = useRef<HTMLInputElement>(null);

  const acceptPDF = (f: File) => f.name.toLowerCase().endsWith(".pdf");

  const pickFile = (
    e: React.ChangeEvent<HTMLInputElement>,
    setter: (v: FileEntry | null) => void
  ) => {
    const f = e.target.files?.[0];
    if (f && acceptPDF(f)) setter({ file: f, key: f.name });
    e.target.value = "";
  };

  const dropFile = useCallback(
    (e: React.DragEvent, setter: (v: FileEntry | null) => void) => {
      e.preventDefault();
      const f = e.dataTransfer.files[0];
      if (f && acceptPDF(f)) setter({ file: f, key: f.name });
    },
    []
  );

  const runQC = async () => {
    if (!appraisal) return;
    setError("");
    setStage("uploading");
    setProgress(5);
    setProgressMsg("Uploading files to server…");

    try {
      const fd = new FormData();
      fd.append("file", appraisal.file);
      if (engagement) fd.append("engagement_letter", engagement.file);
      if (contract)   fd.append("contract_file",     contract.file);

      setStage("ocr");
      setProgress(20);
      setProgressMsg("Extracting text (OCR)… this takes 15–30 s on first run, instant on repeat");

      const res = await fetch(`${API}/qc/process`, { method: "POST", body: fd });

      setStage("rules");
      setProgress(85);
      setProgressMsg("Running 31 compliance rules…");

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.message || `Server error ${res.status}`);
      }

      const data: QCResults = await res.json();
      setProgress(100);
      setStage("done");
      onResults(data, appraisal.file.name);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setStage("error");
      setProgress(0);
    }
  };

  const canRun = !!appraisal && stage === "idle";
  const running = stage === "uploading" || stage === "ocr" || stage === "rules";

  return (
    <div className="max-w-xl mx-auto space-y-6">

      {/* Hero */}
      <div className="text-center">
        <h1 className="text-3xl font-bold text-slate-900">Appraisal QC Check</h1>
        <p className="mt-1 text-slate-500 text-sm">
          Upload your PDFs → click <strong>Run QC</strong> → get results in seconds
        </p>
      </div>

      {/* File slots */}
      <div className="space-y-3">
        <FileSlot
          label="Appraisal Report"
          required
          entry={appraisal}
          inputRef={appraisalRef}
          onPick={e => pickFile(e, setAppraisal)}
          onDrop={e => dropFile(e, setAppraisal)}
          onClear={() => setAppraisal(null)}
        />
        <FileSlot
          label="Engagement Letter / Order Form"
          entry={engagement}
          inputRef={engRef}
          onPick={e => pickFile(e, setEngagement)}
          onDrop={e => dropFile(e, setEngagement)}
          onClear={() => setEngagement(null)}
        />
        <FileSlot
          label="Purchase Contract"
          entry={contract}
          inputRef={conRef}
          onPick={e => pickFile(e, setContract)}
          onDrop={e => dropFile(e, setContract)}
          onClear={() => setContract(null)}
        />
      </div>

      {/* Progress */}
      {running && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-sm text-blue-700 font-medium">
            <Spinner />
            {progressMsg}
          </div>
          <div className="w-full bg-blue-200 rounded-full h-2 overflow-hidden">
            <div
              className="h-full bg-blue-600 rounded-full transition-all duration-700"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-blue-500">
            {stage === "ocr"
              ? "First run: OCR processes every page (~15–30 s). Repeat uploads are instant (cached)."
              : "Almost done…"}
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-red-700 text-sm">
          <strong>Error:</strong> {error}
          <button
            className="ml-3 underline text-red-500"
            onClick={() => { setError(""); setStage("idle"); }}
          >
            Try again
          </button>
        </div>
      )}

      {/* THE BUTTON — always visible, styled prominently */}
      <Button
        size="lg"
        className="w-full text-base h-12"
        onClick={runQC}
        disabled={!canRun || running}
      >
        {running ? (
          <span className="flex items-center gap-2"><Spinner /> Processing…</span>
        ) : (
          appraisal ? "▶  Run QC Check" : "Select appraisal PDF above to start"
        )}
      </Button>

      {!appraisal && (
        <p className="text-center text-xs text-slate-400">
          Only the Appraisal Report is required. The other two files improve accuracy.
        </p>
      )}
    </div>
  );
}

/* ── File drop slot ──────────────────────────────────────────────────────── */

type SlotProps = {
  label: string;
  required?: boolean;
  entry: FileEntry | null;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onPick: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDrop: (e: React.DragEvent) => void;
  onClear: () => void;
};

function FileSlot({ label, required, entry, inputRef, onPick, onDrop, onClear }: SlotProps) {
  const [hover, setHover] = useState(false);

  if (entry) {
    return (
      <div className="flex items-center gap-3 bg-green-50 border border-green-300 rounded-xl px-4 py-3">
        <span className="text-green-600 text-lg">✓</span>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-green-600 uppercase tracking-wide">{label}</div>
          <div className="text-sm font-medium text-slate-800 truncate">{entry.file.name}</div>
          <div className="text-xs text-slate-400">{(entry.file.size / 1024 / 1024).toFixed(1)} MB</div>
        </div>
        <button
          onClick={onClear}
          className="text-slate-400 hover:text-red-500 text-lg leading-none transition-colors"
          title="Remove"
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setHover(true); }}
      onDragLeave={() => setHover(false)}
      onDrop={e => { setHover(false); onDrop(e); }}
      onClick={() => inputRef.current?.click()}
      className={`
        border-2 border-dashed rounded-xl px-4 py-4 cursor-pointer transition-all select-none
        ${hover ? "border-blue-500 bg-blue-50" : "border-slate-200 hover:border-blue-300 bg-white hover:bg-slate-50"}
      `}
    >
      <input ref={inputRef} type="file" accept=".pdf" className="hidden" onChange={onPick} />
      <div className="flex items-center gap-3 text-slate-500">
        <span className="text-2xl">📄</span>
        <div>
          <div className="text-sm font-medium text-slate-700">
            {label} {required && <span className="text-red-500 text-xs">required</span>}
          </div>
          <div className="text-xs text-slate-400">Click or drag PDF here</div>
        </div>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
    </svg>
  );
}
