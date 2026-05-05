"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { PageSpinner } from "@/components/shared/Spinner";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

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
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const highlightRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const page = pageRefs.current[targetPage];
    if (!page) return;
    window.setTimeout(() => {
      const target = targetBox ? highlightRef.current : page;
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 80);
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
      <div className="flex flex-col items-center gap-6">
        {Array.from({ length: numPages }, (_, index) => {
          const pageNumber = index + 1;
          return (
            <div
              key={`${fileUrl}-${pageNumber}`}
              ref={node => { pageRefs.current[pageNumber] = node; }}
              className="relative"
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
              <Page
                pageNumber={pageNumber}
                width={width}
                loading={<PageSpinner label="Loading page..." />}
                renderAnnotationLayer
                renderTextLayer
                className="overflow-hidden rounded-md bg-white shadow-[0_18px_48px_rgba(0,0,0,0.46)]"
              />
            </div>
          );
        })}
      </div>
    </Document>
  );
}

function DocumentError() {
  return (
    <div className="flex min-h-80 flex-col items-center justify-center gap-2 rounded-lg border border-amber-500/25 bg-amber-950/10 px-6 text-center text-slate-400">
      <AlertTriangle size={18} className="text-amber-500" />
      <div className="text-sm">Document could not be loaded</div>
      <div className="max-w-md text-xs text-slate-500">Check that the reviewer is assigned to this batch and that the PDF file exists.</div>
    </div>
  );
}

export default PdfDocumentViewer;
