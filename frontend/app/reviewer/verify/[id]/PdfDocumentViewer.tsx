"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { PageSpinner } from "@/components/shared/Spinner";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

// Pages this far (in px) above/below the scroll viewport are mounted; everything
// else is a cheap fixed-height placeholder. A large appraisal PDF can be 30+ pages
// and mounting every page's canvas + text layer at once locks up the main thread.
// Virtualizing to the visible window keeps the DOM (and scrolling) responsive.
const RENDER_MARGIN_PX = 1600;
// Fallback page aspect ratio (US Letter) used to size placeholders before a page
// has ever rendered, so scroll height is stable and scroll position doesn't jump.
const DEFAULT_PAGE_RATIO = 11 / 8.5;

export function PdfDocumentViewer({
  fileUrl,
  targetPage,
  targetBox,
  focusNonce = 0,
  width,
  highlighting,
  onLoadSuccess,
  onLoadError,
}: {
  fileUrl?: string;
  targetPage: number;
  targetBox?: { x: number; y: number; w: number; h: number } | null;
  /** Bumped by the parent on every focus action, so a re-click on the same
   *  finding re-scrolls even when page/box are unchanged. */
  focusNonce?: number;
  width: number;
  highlighting: boolean;
  onLoadSuccess: (numPages: number) => void;
  onLoadError: () => void;
}) {
  const pdfOptions = useMemo(() => ({ withCredentials: true }), []);
  const [numPages, setNumPages] = useState(0);
  const [visiblePages, setVisiblePages] = useState<Set<number>>(() => new Set([1]));
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const highlightRef = useRef<HTMLDivElement | null>(null);
  const scrollRootRef = useRef<HTMLElement | null>(null);
  const rootMarkerRef = useRef<HTMLDivElement | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  // Last measured height per page, so an unmounted page's placeholder keeps its
  // real size and scrolling past it doesn't cause the content to jump.
  // Tagged with the width each height was measured at, so a zoom change makes
  // old entries self-evidently stale. That removes the need to clear the cache
  // when width changes — which would mean mutating a ref during render.
  const pageHeights = useRef<Record<number, { width: number; height: number }>>({});
  // The real rendered height of a page at the current width. Report pages are a
  // UNIFORM size, so once ONE page has rendered we use its true height for every
  // not-yet-rendered page's placeholder — instead of the US-Letter GUESS, which
  // is ~250px too short on the common legal-size (8.5×14) report. A wrong guess
  // made every page grow when it rendered, shoving the just-jumped-to finding
  // down the page and forcing a second, disruptive re-scroll to correct it.
  const [measuredHeight, setMeasuredHeight] = useState<number | null>(null);

  const estimatedHeight = Math.round(width * DEFAULT_PAGE_RATIO);

  // Switching documents needs no reset effect: the parent mounts this component
  // with key={activeDocument.id}, so a different file remounts it and every ref
  // and state value starts fresh. The effect that used to do this by hand was
  // redundant, and it reset state from inside an effect for no reason.

  // Zoom changes the render width, so the measured height no longer applies.
  // Adjusting during render (React's documented pattern for "reset state when a
  // prop changes") drops it before the pages paint, rather than painting once at
  // the old height and then correcting.
  const [renderedWidth, setRenderedWidth] = useState(width);
  if (renderedWidth !== width) {
    setRenderedWidth(width);
    setMeasuredHeight(null);
  }

  // Find the scrollable ancestor (the viewer's overflow-auto container) so the
  // IntersectionObserver measures against what the user actually scrolls.
  const resolveScrollRoot = useCallback(() => {
    let el: HTMLElement | null = rootMarkerRef.current?.parentElement ?? null;
    while (el) {
      const style = window.getComputedStyle(el);
      if (/(auto|scroll)/.test(style.overflowY) || /(auto|scroll)/.test(style.overflow)) return el;
      el = el.parentElement;
    }
    return null;
  }, []);

  // (Re)build the observer whenever the page count changes.
  useEffect(() => {
    if (numPages === 0) return;
    const root = scrollRootRef.current ?? resolveScrollRoot();
    scrollRootRef.current = root;

    const observer = new IntersectionObserver(entries => {
      setVisiblePages(prev => {
        const next = new Set(prev);
        let changed = false;
        for (const entry of entries) {
          const page = Number((entry.target as HTMLElement).dataset.page);
          if (!page) continue;
          if (entry.isIntersecting) {
            if (!next.has(page)) { next.add(page); changed = true; }
          } else if (next.has(page)) {
            next.delete(page); changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, { root, rootMargin: `${RENDER_MARGIN_PX}px 0px`, threshold: 0 });

    observerRef.current = observer;
    for (let p = 1; p <= numPages; p++) {
      const node = pageRefs.current[p];
      if (node) observer.observe(node);
    }
    return () => { observer.disconnect(); observerRef.current = null; };
  }, [numPages, resolveScrollRoot]);

  const registerPage = useCallback((page: number, node: HTMLDivElement | null) => {
    const prev = pageRefs.current[page];
    if (prev && observerRef.current) observerRef.current.unobserve(prev);
    pageRefs.current[page] = node;
    if (node && observerRef.current) observerRef.current.observe(node);
  }, []);

  // Set while a focus is awaiting the target page's first render, so the ONE
  // scroll can fire from onRenderSuccess (below) the moment the real height exists.
  const pendingFocusRef = useRef(false);

  // Current width, readable by the scroll effect WITHOUT making width a scroll
  // trigger. See the effect below for why that distinction matters.
  const widthRef = useRef(width);
  useEffect(() => { widthRef.current = width; }, [width]);

  const scrollToTarget = useCallback(() => {
    const page = pageRefs.current[targetPage];
    const target = (targetBox && highlightRef.current) ? highlightRef.current : page;
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [targetPage, targetBox]);

  // Scroll the target finding into view EXACTLY ONCE per focus, and only once the
  // target page has its REAL height — so the landing is accurate and never needs a
  // second (disruptive) correction that shoves the document up/down after the jump.
  // If the page is already rendered, scroll now; otherwise defer the single scroll
  // to onRenderSuccess. `highlighting` is intentionally NOT a dependency — it is a
  // visual ring and must never move the document (its 5s toggle used to re-fire
  // this effect and re-scroll the page out from under the reviewer).
  //
  // `width` is excluded for the same reason, and read through a ref instead: it
  // is needed to tell a stale cached height from a fresh one, but zoom must not
  // re-trigger a scroll. The parent zooms around the cursor anchor, so pulling
  // the document back to the focused box mid-zoom would fight the reviewer.
  useEffect(() => {
    if (!targetPage) return;
    const measured = pageHeights.current[targetPage];
    const ready = pageRefs.current[targetPage] && measured?.width === widthRef.current;
    if (ready) {
      pendingFocusRef.current = false;
      const t = window.setTimeout(scrollToTarget, 60);
      return () => window.clearTimeout(t);
    }
    pendingFocusRef.current = true;   // not rendered yet → onRenderSuccess does the one scroll
  }, [fileUrl, targetPage, targetBox, numPages, focusNonce, scrollToTarget]);

  // The focus target must be mounted for the scroll above to have something to
  // land on. Deriving that — rather than pushing targetPage into visiblePages
  // from the effect — keeps the mounted set a pure function of "what the
  // observer sees" plus "where we are being sent".
  const mountedPages = useMemo(() => {
    if (!targetPage || visiblePages.has(targetPage)) return visiblePages;
    return new Set(visiblePages).add(targetPage);
  }, [visiblePages, targetPage]);

  return (
    <Document
      file={fileUrl}
      options={pdfOptions}
      loading={<PageSpinner label="Loading document..." />}
      error={<DocumentError />}
      onLoadSuccess={({ numPages }) => {
        setNumPages(numPages);
        onLoadSuccess(numPages);
      }}
      onLoadError={onLoadError}
    >
      <div ref={rootMarkerRef} className="flex flex-col items-center gap-6">
        {Array.from({ length: numPages }, (_, index) => {
          const pageNumber = index + 1;
          const isVisible = mountedPages.has(pageNumber);
          // Report pages are a uniform size, so the first measured height sizes
          // every placeholder. Reading the per-page `pageHeights` ref here instead
          // made render depend on a value React does not track — and for an
          // unmounted page (the only case a placeholder is shown) that ref entry
          // is unset anyway, so this is the same number by a legal route.
          const placeholderHeight = measuredHeight ?? estimatedHeight;
          return (
            <div
              key={`${fileUrl}-${pageNumber}`}
              data-page={pageNumber}
              ref={node => registerPage(pageNumber, node)}
              className="relative"
              style={{ width, minHeight: isVisible ? undefined : placeholderHeight }}
            >
              {highlighting && targetPage === pageNumber && targetBox && (
                <div
                  ref={highlightRef}
                  className="pointer-events-none absolute z-20 rounded-[3px] border-2 border-amber-300 bg-amber-300/18 shadow-[0_0_28px_rgba(245,158,11,0.36)] transition-all"
                  style={{
                    left: `${targetBox.x * 100}%`,
                    top: `${targetBox.y * 100}%`,
                    width: `${targetBox.w * 100}%`,
                    height: `${targetBox.h * 100}%`,
                  }}
                />
              )}
              {isVisible ? (
                <Page
                  pageNumber={pageNumber}
                  width={width}
                  loading={<PagePlaceholder height={placeholderHeight} label="Loading page..." />}
                  renderAnnotationLayer
                  renderTextLayer
                  onRenderSuccess={() => {
                    const node = pageRefs.current[pageNumber];
                    if (node) {
                      pageHeights.current[pageNumber] = { width, height: node.offsetHeight };
                      // First real height → use it for every un-rendered page's
                      // placeholder so later renders don't shift the layout.
                      if (measuredHeight == null) setMeasuredHeight(node.offsetHeight);
                    }
                    // The ONE scroll for a pending focus, now that the target page
                    // has its real height — a single accurate landing, never a
                    // jump-then-correct.
                    if (pendingFocusRef.current && pageNumber === targetPage) {
                      pendingFocusRef.current = false;
                      window.setTimeout(scrollToTarget, 60);
                    }
                  }}
                  className="overflow-hidden rounded-md bg-white shadow-[0_18px_48px_rgba(0,0,0,0.46)]"
                />
              ) : (
                <PagePlaceholder height={placeholderHeight} />
              )}
            </div>
          );
        })}
      </div>
    </Document>
  );
}

function PagePlaceholder({ height, label }: { height: number; label?: string }) {
  return (
    <div
      className="flex items-center justify-center rounded-md border border-white/5 bg-slate-900/40"
      style={{ height }}
    >
      {label ? <PageSpinner label={label} /> : null}
    </div>
  );
}

function DocumentError() {
  return (
    <div className="flex min-h-80 flex-col items-center justify-center gap-2 rounded-lg border border-amber-500/25 bg-amber-950/10 px-6 text-center text-slate-400">
      <AlertTriangle size={18} className="text-amber-500" />
      <div className="text-sm">Document could not be loaded</div>
      <div className="max-w-md text-xs text-slate-500">Check that the reviewer is assigned to this order and that the PDF file exists.</div>
    </div>
  );
}

export default PdfDocumentViewer;
