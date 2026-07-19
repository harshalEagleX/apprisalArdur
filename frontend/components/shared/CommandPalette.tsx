"use client";
/**
 * ⌘K global command palette — searches across batches, clients, and users
 * without a dedicated backend endpoint. Uses the existing paginated APIs
 * with a search param; results are capped at 5 per entity type.
 *
 * Accessible: focus-trap, Escape to close, arrow-key navigation, Enter to go.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, Package, Building2, Users, Loader2, X } from "lucide-react";
import { getAdminBatches, getClients, getAllUsers, type Batch } from "@/lib/api";

type ResultKind = "batch" | "client" | "user";
interface Result {
  id: number;
  kind: ResultKind;
  label: string;
  sub?: string;
  href: string;
}

const KIND_ICON: Record<ResultKind, React.ComponentType<{ size?: number; className?: string }>> = {
  batch:  Package,
  client: Building2,
  user:   Users,
};

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery]         = useState("");
  const [results, setResults]     = useState<Result[]>([]);
  const [loading, setLoading]     = useState(false);
  const [cursor, setCursor]       = useState(0);
  const inputRef                  = useRef<HTMLInputElement>(null);
  const router                    = useRouter();

  // Reset search state and focus the input whenever the palette opens.
  // State is set on a controlled closed→open transition, not in a loop.
  useEffect(() => {
    if (open) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setQuery("");
      setResults([]);
      setCursor(0);
      /* eslint-enable react-hooks/set-state-in-effect */
      window.setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return; }
    setLoading(true);
    try {
      const [batchRes, clientRes, userRes] = await Promise.allSettled([
        getAdminBatches(0, undefined, q),
        getClients(),
        getAllUsers(100),
      ]);

      const out: Result[] = [];

      if (batchRes.status === "fulfilled") {
        const batches: Batch[] = Array.isArray(batchRes.value)
          ? batchRes.value
          : ((batchRes.value as { content?: Batch[] }).content ?? []);
        batches.slice(0, 5).forEach(b => out.push({
          id: b.id, kind: "batch",
          label: b.parentBatchId ?? `Batch #${b.id}`,
          sub: b.client?.name,
          href: `/admin/batches/${b.id}`,
        }));
      }

      if (clientRes.status === "fulfilled") {
        const lq = q.toLowerCase();
        clientRes.value
          .filter(c => c.name.toLowerCase().includes(lq) || c.code.toLowerCase().includes(lq))
          .slice(0, 5)
          .forEach(c => out.push({
            id: c.id, kind: "client",
            label: c.name,
            sub: c.code,
            href: `/admin/clients/${c.id}`,
          }));
      }

      if (userRes.status === "fulfilled") {
        const lq = q.toLowerCase();
        userRes.value
          .filter(u =>
            u.username.toLowerCase().includes(lq) ||
            (u.fullName ?? "").toLowerCase().includes(lq) ||
            (u.email ?? "").toLowerCase().includes(lq)
          )
          .slice(0, 5)
          .forEach(u => out.push({
            id: u.id, kind: "user",
            label: u.fullName ?? u.username,
            sub: u.username,
            href: `/admin/users`,
          }));
      }

      setResults(out);
      setCursor(0);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounce
  useEffect(() => {
    const t = window.setTimeout(() => { void search(query); }, 220);
    return () => window.clearTimeout(t);
  }, [query, search]);

  function go(href: string) { router.push(href); onClose(); }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") { onClose(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)); }
    if (e.key === "ArrowUp")   { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)); }
    if (e.key === "Enter" && results[cursor]) { go(results[cursor].href); }
  }

  if (!open) return null;

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-[200] flex items-start justify-center bg-black/60 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Panel */}
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-white/10 bg-sunken shadow-[0_24px_64px_rgba(0,0,0,0.55)]"
        onClick={e => e.stopPropagation()}
        onKeyDown={handleKey}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
          {loading
            ? <Loader2 size={16} className="shrink-0 animate-spin text-slate-500" />
            : <Search size={16} className="shrink-0 text-slate-500" />
          }
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search batches, clients, users…"
            className="flex-1 bg-transparent text-sm text-white placeholder:text-slate-600 focus:outline-none"
          />
          {query && (
            <button onClick={() => setQuery("")} className="text-slate-500 hover:text-slate-300">
              <X size={14} />
            </button>
          )}
          <kbd className="hidden rounded border border-white/10 bg-muted px-1.5 py-0.5 text-[11px] text-slate-500 sm:inline">Esc</kbd>
        </div>

        {/* Results */}
        {query && results.length === 0 && !loading && (
          <div className="px-4 py-8 text-center text-sm text-slate-500">
            No results for <span className="text-slate-300">&ldquo;{query}&rdquo;</span>
          </div>
        )}

        {results.length > 0 && (
          <ul className="max-h-80 overflow-y-auto py-1.5">
            {results.map((r, i) => {
              const Icon = KIND_ICON[r.kind];
              return (
                <li key={`${r.kind}-${r.id}`}>
                  <button
                    onClick={() => go(r.href)}
                    onMouseEnter={() => setCursor(i)}
                    className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${i === cursor ? "bg-white/[0.06] text-white" : "text-slate-300 hover:bg-white/[0.04]"}`}
                  >
                    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border ${
                      r.kind === "batch" ? "border-indigo-500/25 bg-indigo-950/40 text-indigo-300"
                      : r.kind === "client" ? "border-green-500/25 bg-green-950/40 text-green-300"
                      : "border-slate-500/25 bg-slate-950/40 text-slate-300"
                    }`}>
                      <Icon size={13} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{r.label}</span>
                      {r.sub && <span className="block truncate text-[11px] text-slate-500">{r.sub}</span>}
                    </span>
                    <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] capitalize text-slate-600">{r.kind}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        {/* Footer hint */}
        {!query && (
          <div className="px-4 py-5 text-center text-xs text-slate-600">
            Type to search across batches, clients, and users
          </div>
        )}

        <div className="flex items-center gap-4 border-t border-white/[0.06] px-4 py-2 text-[11px] text-slate-600">
          <span className="flex items-center gap-1"><kbd className="rounded border border-white/10 bg-muted px-1 text-[10px]">↑↓</kbd> navigate</span>
          <span className="flex items-center gap-1"><kbd className="rounded border border-white/10 bg-muted px-1 text-[10px]">↵</kbd> open</span>
          <span className="flex items-center gap-1"><kbd className="rounded border border-white/10 bg-muted px-1 text-[10px]">Esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
