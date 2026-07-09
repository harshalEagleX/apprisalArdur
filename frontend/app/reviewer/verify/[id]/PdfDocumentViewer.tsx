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
  width,
  highlighting,
  onLoadSuccess,
  onLoadError,
}: {
  fileUrl?: string;
  targetPage: number;
  targetBox?: { x: number; y: number; w: number; h: number } | null;
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
  const pageHeights = useRef<Record<number, number>>({});

  const estimatedHeight = Math.round(width * DEFAULT_PAGE_RATIO);

  // Reset virtualization when the document changes.
  useEffect(() => {
    pageHeights.current = {};
    setVisiblePages(new Set([Math.max(1, targetPage)]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileUrl]);

  // Zoom changes the render width, so cached placeholder heights are stale —
  // drop them (visible pages re-measure on render; the estimate covers the rest).
  useEffect(() => {
    pageHeights.current = {};
  }, [width]);

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

  // Keep the target (highlighted) page mounted and scroll it into view.
  useEffect(() => {
    if (!targetPage) return;
    setVisiblePages(prev => prev.has(targetPage) ? prev : new Set(prev).add(targetPage));
    const page = pageRefs.current[targetPage];
    if (!page) return;
    window.setTimeout(() => {
      const target = targetBox ? highlightRef.current : page;
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
  }, [fileUrl, targetPage, targetBox, highlighting, numPages]);

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
          const isVisible = visiblePages.has(pageNumber);
          const placeholderHeight = pageHeights.current[pageNumber] ?? estimatedHeight;
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
                    if (node) pageHeights.current[pageNumber] = node.offsetHeight;
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
