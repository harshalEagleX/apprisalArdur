"use client";

/**
 * Checklist editor — the AMC's QC questions, per client and per form version.
 *
 * These questions used to live in a YAML file that only a deploy could change.
 * This screen is where they are authored instead.
 *
 * Two things drive the layout:
 *
 *  - **A checklist is reviewed and saved as a SET.** Edits are held locally and
 *    written in one call, because a half-saved checklist is a state nobody
 *    signed off on. The unsaved count is always visible so nobody navigates
 *    away thinking their work landed.
 *  - **Polarity is the dangerous field.** It decides whether "no" means a clean
 *    report or a failing one, so getting it backwards rejects good appraisals.
 *    It is a labelled dropdown rather than free text, and "Unknown" is offered
 *    as a first-class safe answer — an item with unknown polarity can raise a
 *    review but can never fail.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Camera, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import {
  getChecklist, getChecklists, saveChecklist, seedChecklist,
  type ChecklistDetail, type ChecklistItem, type ChecklistSummary,
} from "@/lib/api";
import { toast } from "@/lib/toast";

const POLARITY: { value: "yes" | "no" | "unknown"; label: string; hint: string }[] = [
  { value: "yes", label: "Yes = compliant",
    hint: "A good report answers YES. Answering no is a finding." },
  { value: "no", label: "No = compliant",
    hint: "A problem-free property answers NO. Answering yes needs a reviewer." },
  { value: "unknown", label: "Unknown (safe)",
    hint: "Depends on circumstances. Can raise a review, can never fail." },
];

export default function ChecklistsPage() {
  const [summaries, setSummaries] = useState<ChecklistSummary[]>([]);
  const [selected, setSelected] = useState<{ amc: string; version: string } | null>(null);
  const [detail, setDetail] = useState<ChecklistDetail | null>(null);
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState("");

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getChecklists();
      setSummaries(res.checklists);
      if (!selected && res.checklists.length) {
        setSelected({ amc: res.checklists[0].amc_code,
                      version: res.checklists[0].uad_version });
      }
    } catch {
      toast.error("Could not load checklists — is the QC service running?");
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => { void loadList(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await getChecklist(selected.amc, selected.version);
        if (cancelled) return;
        setDetail(d);
        setItems(d.items);
        setDirty(false);
      } catch {
        if (!cancelled) toast.error(`Could not load ${selected.amc} ${selected.version}`);
      }
    })();
    return () => { cancelled = true; };
  }, [selected]);

  const update = (index: number, patch: Partial<ChecklistItem>) => {
    setItems(prev => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
    setDirty(true);
  };

  const addItem = () => {
    // A new question starts with UNKNOWN polarity on purpose: until a person
    // says what a compliant answer looks like, it must not be able to fail.
    const n = Math.max(0, ...items.map(i => Number(i.checklist_number) || 0)) + 1;
    setItems(prev => [...prev, {
      rule_id: `NEW-${n}`, checklist_number: n, section: "other",
      requirement: "", polarity: "unknown", evidence_kind: "text", proof: "none",
      requires_documents: [], classified: false,
    }]);
    setDirty(true);
  };

  const removeItem = (index: number) => {
    setItems(prev => prev.filter((_, i) => i !== index));
    setDirty(true);
  };

  const save = async () => {
    if (!selected) return;
    const blank = items.findIndex(i => !String(i.requirement ?? "").trim());
    if (blank >= 0) {
      toast.error(`Item ${blank + 1} has no question text — it cannot be answered.`);
      return;
    }
    setSaving(true);
    try {
      const res = await saveChecklist(selected.amc, selected.version, items);
      toast.success(`Saved ${res.items} items to ${res.file}`);
      setDirty(false);
      void loadList();
    } catch (e) {
      // SHALqc's validation messages are written for the operator; show them.
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const seed = async () => {
    if (!selected) return;
    try {
      const res = await seedChecklist(selected.amc, selected.version);
      toast.success(res.status === "seeded"
        ? `Created an editable copy (${res.items} items)`
        : res.detail ?? "Already has its own copy");
      void loadList();
      setSelected({ ...selected });
    } catch {
      toast.error("Could not create an editable copy");
    }
  };

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return items.map((it, i) => ({ it, i }));
    return items.map((it, i) => ({ it, i })).filter(({ it }) =>
      String(it.requirement ?? "").toLowerCase().includes(q) ||
      String(it.rule_id ?? "").toLowerCase().includes(q) ||
      String(it.section ?? "").toLowerCase().includes(q));
  }, [items, filter]);

  const unknownCount = items.filter(i => (i.polarity ?? "unknown") === "unknown").length;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">QC Checklists</h1>
          <p className="text-sm text-slate-400">
            The questions each client&apos;s reports are checked against. Separate
            per form version — 2.6 and 3.6 are different documents.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => void loadList()}
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800">
            <RefreshCw size={14} /> Reload
          </button>
          <button onClick={() => void save()} disabled={!dirty || saving}
                  className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
            <Save size={14} /> {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        {summaries.map(s => {
          const active = selected?.amc === s.amc_code && selected?.version === s.uad_version;
          return (
            <button key={`${s.amc_code}-${s.uad_version}`}
                    onClick={() => {
                      if (dirty && !confirm("Discard unsaved changes?")) return;
                      setSelected({ amc: s.amc_code, version: s.uad_version });
                    }}
                    className={`rounded-md border px-3 py-2 text-left text-sm ${
                      active ? "border-sky-500 bg-sky-950/40 text-sky-100"
                             : "border-slate-700 text-slate-300 hover:bg-slate-800"}`}>
              <div className="font-medium">{s.amc_code}</div>
              <div className="text-xs text-slate-400">
                UAD {s.uad_version} · {s.items} items
                {!s.customised && " · using default"}
              </div>
            </button>
          );
        })}
      </div>

      {detail && !detail.customised && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-950/30 p-3 text-sm text-amber-200">
          <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
          <div>
            This client is still using the built-in checklist. Editing it would
            change every client that has not been customised, so saving will
            create this client&apos;s own copy first.
            <button onClick={() => void seed()} className="ml-2 underline">
              Create an editable copy now
            </button>
          </div>
        </div>
      )}

      {unknownCount > 0 && (
        <div className="rounded-md border border-slate-700 bg-slate-900/60 p-3 text-sm text-slate-300">
          <strong className="text-slate-100">{unknownCount}</strong> item
          {unknownCount === 1 ? " has" : "s have"} an unknown compliant answer.
          Those can raise a review but will never fail a report — set the
          polarity once you are sure which answer means &ldquo;clean&rdquo;.
        </div>
      )}

      <input value={filter} onChange={e => setFilter(e.target.value)}
             placeholder="Filter by question, id or section…"
             className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500" />

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <div className="space-y-2">
          {shown.map(({ it, i }) => (
            <div key={`${it.rule_id}-${i}`}
                 className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono">
                  {it.rule_id}
                </span>
                <input value={it.section ?? ""} onChange={e => update(i, { section: e.target.value })}
                       className="w-40 rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs"
                       aria-label="Section" />
                {it.evidence_kind === "photo" && (
                  <span className="inline-flex items-center gap-1 text-sky-300">
                    <Camera size={11} /> photo
                  </span>
                )}
                {(it.requires_documents?.length ?? 0) > 0 && (
                  <span className="rounded bg-amber-950/50 px-1.5 py-0.5 text-amber-200">
                    needs {it.requires_documents!.join(", ")}
                  </span>
                )}
                <button onClick={() => removeItem(i)}
                        className="ml-auto text-slate-500 hover:text-rose-300"
                        aria-label="Remove item">
                  <Trash2 size={14} />
                </button>
              </div>

              <textarea value={String(it.requirement ?? "")} rows={2}
                        onChange={e => update(i, { requirement: e.target.value })}
                        placeholder="The question a reviewer is answering…"
                        className="mt-2 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-200" />

              <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                <label className="flex items-center gap-1.5 text-slate-400">
                  A compliant report answers
                  <select value={it.polarity ?? "unknown"}
                          onChange={e => update(i, { polarity: e.target.value as ChecklistItem["polarity"] })}
                          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200">
                    {POLARITY.map(p => (
                      <option key={p.value} value={p.value} title={p.hint}>{p.label}</option>
                    ))}
                  </select>
                </label>
                <span className="text-slate-500">
                  {POLARITY.find(p => p.value === (it.polarity ?? "unknown"))?.hint}
                </span>
              </div>
            </div>
          ))}

          <button onClick={addItem}
                  className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-slate-700 px-3 py-2 text-sm text-slate-400 hover:bg-slate-800">
            <Plus size={14} /> Add a question
          </button>
        </div>
      )}
    </div>
  );
}
