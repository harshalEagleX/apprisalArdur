"use client";
import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  CircleHelp,
  Lightbulb,
  Lock,
  Search,
  Send,
} from "lucide-react";

type Article = {
  id: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  summary: string;
  content: React.ReactNode;
};

const ARTICLES: Article[] = [
  {
    id: "upload",
    Icon: Send,
    title: "How to upload and process a file",
    summary: "Step-by-step guide to getting your appraisal file checked.",
    content: (
      <ol className="space-y-3 text-sm text-slate-300">
        <li className="flex gap-3"><span className="text-blue-400 font-bold">1.</span><span>Go to the <strong>Upload</strong> tab on your dashboard.</span></li>
        <li className="flex gap-3"><span className="text-blue-400 font-bold">2.</span><span>Prepare a <strong>ZIP file</strong> containing your appraisal, engagement letter, and purchase contract in separate folders (<code className="bg-slate-800 px-1 rounded">appraisal/</code>, <code className="bg-slate-800 px-1 rounded">engagement/</code>, <code className="bg-slate-800 px-1 rounded">contract/</code>).</span></li>
        <li className="flex gap-3"><span className="text-blue-400 font-bold">3.</span><span>Drag your ZIP file onto the upload area, or click to browse.</span></li>
        <li className="flex gap-3"><span className="text-blue-400 font-bold">4.</span><span>Click <strong>Upload Batch</strong>. You will see the status change to <em>Processing</em>.</span></li>
        <li className="flex gap-3"><span className="text-blue-400 font-bold">5.</span><span>When processing is complete, the status changes to <em>Review Pending</em> or <em>Completed</em>.</span></li>
        <li className="flex gap-3"><span className="text-blue-400 font-bold">6.</span><span>If you see <em>Review Pending</em>, a reviewer will check the items flagged by the system.</span></li>
      </ol>
    ),
  },
  {
    id: "status",
    Icon: BarChart3,
    title: "Understanding file status labels",
    summary: "What each status means and what action (if any) you need to take.",
    content: (
      <div className="space-y-3 text-sm">
        {[
          { status: "Uploaded",       color: "bg-slate-700 text-slate-200",   meaning: "Your file arrived safely. No action needed.",                         action: "Wait for processing to start." },
          { status: "Processing",     color: "bg-blue-900 text-blue-200",     meaning: "The system is reading your documents. This usually takes under a minute.", action: "Wait — do not re-upload." },
          { status: "Review Pending", color: "bg-amber-900 text-amber-200",   meaning: "Some items need a human reviewer to check.",                          action: "A reviewer will handle this. Nothing for you to do." },
          { status: "In Review",      color: "bg-orange-900 text-orange-200", meaning: "A reviewer is currently examining your file.",                        action: "Wait for the reviewer to finish." },
          { status: "Completed",      color: "bg-green-900 text-green-200",   meaning: "All checks passed. File is fully processed.",                        action: "No further action needed." },
          { status: "Error",          color: "bg-red-900 text-red-200",       meaning: "Something went wrong during processing.",                            action: "See the 'What to do when something goes wrong' section below." },
        ].map(({ status, color, meaning, action }) => (
          <div key={status} className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${color}`}>{status}</span>
            </div>
            <p className="text-slate-300"><strong>What it means:</strong> {meaning}</p>
            <p className="text-slate-400 text-xs mt-1"><strong>Your action:</strong> {action}</p>
          </div>
        ))}
      </div>
    ),
  },
  {
    id: "results",
    Icon: CheckCircle2,
    title: "Understanding your results",
    summary: "What PASS, FAIL, and VERIFY mean for your file.",
    content: (
      <div className="space-y-4 text-sm text-slate-300">
        <div className="bg-green-950 border border-green-800 rounded-lg p-3">
          <div className="font-semibold text-green-300 mb-1">PASS — Everything looks good</div>
          <p>The system found no issues with this item. No action required.</p>
        </div>
        <div className="bg-red-950 border border-red-800 rounded-lg p-3">
          <div className="font-semibold text-red-300 mb-1">FAIL — An issue was found</div>
          <p>The system detected something that does not match expectations — for example, an address mismatch between the appraisal and the engagement letter. A reviewer will check this.</p>
        </div>
        <div className="bg-amber-950 border border-amber-800 rounded-lg p-3">
          <div className="font-semibold text-amber-300 mb-1">? VERIFY — Needs human confirmation</div>
          <p>The system was not fully confident about this item. A reviewer will confirm whether it is correct or not. This is not an error — it just means the system wants a human to double-check.</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-3">
          <div className="font-semibold text-slate-200 mb-1">What happens to FAIL and VERIFY items?</div>
          <p className="text-slate-400">They are sent to a reviewer queue. A qualified reviewer will inspect each flagged item, confirm or reject it, and record a final decision. You will see the batch status change once the review is complete.</p>
        </div>
      </div>
    ),
  },
  {
    id: "errors",
    Icon: AlertTriangle,
    title: "What to do when something goes wrong",
    summary: "Step-by-step guide for handling errors without panicking.",
    content: (
      <div className="space-y-4 text-sm text-slate-300">
        <div className="border border-slate-700 rounded-lg p-4 space-y-3">
          <div className="font-semibold text-white">Step 1 — Note the error ID</div>
          <p>Every error has a unique code shown on screen (e.g. <code className="bg-slate-800 px-1 rounded text-xs">ERR-1042</code>). Write it down or take a screenshot.</p>
        </div>
        <div className="border border-slate-700 rounded-lg p-4 space-y-3">
          <div className="font-semibold text-white">Step 2 — Check the common causes</div>
          <ul className="space-y-1 text-slate-400 text-xs">
            <li>ZIP file is missing required folders (<code className="bg-slate-800 px-1 rounded">appraisal/</code>, <code className="bg-slate-800 px-1 rounded">engagement/</code>)</li>
            <li>PDF file is corrupted or password-protected</li>
            <li>File size exceeds 100 MB limit</li>
            <li>You are not connected to the network</li>
          </ul>
        </div>
        <div className="border border-slate-700 rounded-lg p-4 space-y-3">
          <div className="font-semibold text-white">Step 3 — Try again</div>
          <p>Fix the issue and re-upload. Most errors are resolved by correcting the file structure.</p>
        </div>
        <div className="border border-slate-700 rounded-lg p-4 space-y-3">
          <div className="font-semibold text-white">Step 4 — Still not working?</div>
          <p>Contact your system administrator with the <strong>error ID</strong> from Step 1. Do not share the file contents — just the error ID is enough.</p>
        </div>
      </div>
    ),
  },
  {
    id: "access",
    Icon: Lock,
    title: "Access and permissions",
    summary: "Why you might see Access Denied and what to do.",
    content: (
      <div className="space-y-4 text-sm text-slate-300">
        <p>Different users have different levels of access. If you see <strong>Access Denied</strong> or a page says you do not have permission:</p>
        <ul className="space-y-2">
          <li className="flex gap-2">
            <span className="text-blue-400">→</span>
            <span>You are trying to access a page or feature that your account type does not include.</span>
          </li>
          <li className="flex gap-2">
            <span className="text-blue-400">→</span>
            <span>This is normal — not every user needs access to every section.</span>
          </li>
          <li className="flex gap-2">
            <span className="text-blue-400">→</span>
            <span>If you believe you need access, contact your administrator and explain what you need to do.</span>
          </li>
        </ul>
        <div className="bg-slate-800 rounded-lg p-3 text-xs">
          <div className="font-semibold text-slate-200 mb-1">Account types</div>
          <div className="space-y-1 text-slate-400">
            <p><strong className="text-slate-300">Operator / Client</strong> — Upload files and view your own batches.</p>
            <p><strong className="text-slate-300">Reviewer</strong> — Check flagged items and make final decisions.</p>
            <p><strong className="text-slate-300">Admin</strong> — Manage users, clients, and view all data.</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "tips",
    Icon: Lightbulb,
    title: "Best practices for faster processing",
    summary: "Simple tips to get the best results from the system.",
    content: (
      <ul className="space-y-3 text-sm text-slate-300">
        {[
          { tip: "Use the correct folder names", detail: "Folders must be named exactly: appraisal, engagement, contract (lowercase). The system won't recognise misspellings." },
          { tip: "Send clear, unprotected PDFs", detail: "Password-protected or scanned documents with poor image quality reduce accuracy. Higher quality = faster processing." },
          { tip: "Don't re-upload the same file", detail: "The system remembers previously processed files and returns results instantly. Re-uploading wastes your time." },
          { tip: "Upload during business hours", detail: "The review queue is monitored during business hours. Uploading then means faster final decisions." },
          { tip: "Check your batch status before asking for help", detail: "Most 'missing' files are actually still processing. Check the Batches tab before contacting support." },
        ].map(({ tip, detail }) => (
          <li key={tip} className="bg-slate-900 border border-slate-800 rounded-lg p-3">
            <div className="flex items-center gap-2 font-medium text-slate-200 mb-1">
              <CheckCircle2 size={14} className="text-emerald-400" />
              <span>{tip}</span>
            </div>
            <div className="text-slate-400 text-xs">{detail}</div>
          </li>
        ))}
      </ul>
    ),
  },
];

export default function HelpPage() {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-slate-800 px-6 py-5">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center justify-between mb-1">
            <h1 className="text-xl font-bold">Help &amp; Guidance</h1>
            <Link href="/" className="inline-flex items-center gap-1.5 text-slate-400 hover:text-white text-sm">
              <ArrowLeft size={14} /> Back
            </Link>
          </div>
          <p className="text-slate-400 text-sm">Simple answers to common questions. No technical jargon.</p>
        </div>
      </header>

      <main className="max-w-3xl mx-auto p-6 space-y-3">
        {/* Search hint */}
        <div className="bg-blue-950 border border-blue-800 rounded-xl p-4 text-sm text-blue-200 flex items-start gap-2">
          <Search size={18} className="mt-0.5 flex-shrink-0" />
          <span>Click any topic below to expand the answer. If you cannot find what you need, contact your administrator.</span>
        </div>

        {ARTICLES.map(a => (
          <div key={a.id} className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setOpen(open === a.id ? null : a.id)}
              className="w-full text-left p-4 flex items-start gap-3 hover:bg-slate-800/40 transition-colors"
            >
              <a.Icon size={20} className="mt-0.5 text-blue-400 flex-shrink-0" />
              <div className="flex-1">
                <div className="font-medium text-white">{a.title}</div>
                <div className="text-slate-400 text-sm mt-0.5">{a.summary}</div>
              </div>
              {open === a.id
                ? <ChevronUp size={18} className="text-slate-500 mt-0.5" />
                : <ChevronDown size={18} className="text-slate-500 mt-0.5" />}
            </button>

            {open === a.id && (
              <div className="px-4 pb-5 border-t border-slate-800 pt-4">
                {a.content}
              </div>
            )}
          </div>
        ))}

        {/* Still stuck */}
        <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 text-center">
          <CircleHelp size={28} className="mx-auto mb-2 text-blue-400" />
          <div className="font-medium text-white mb-1">Still need help?</div>
          <p className="text-slate-400 text-sm">Contact your system administrator. Describe what you were trying to do and what happened — a screenshot helps if possible.</p>
        </div>
      </main>
    </div>
  );
}
