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
  width,
  highlighting,
  onLoadSuccess,
  onLoadError,
}: {
  fileUrl?: string;
  targetPage: number;
  width: number;
  highlighting: boolean;
  onLoadSuccess: (numPages: number) => void;
  onLoadError: () => void;
}) {
  const pdfOptions = useMemo(() => ({ withCredentials: true }), []);
  const [numPages, setNumPages] = useState(0);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    const page = pageRefs.current[targetPage];
    if (!page) return;
    window.setTimeout(() => {
      page.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  }, [fileUrl, targetPage, numPages]);

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
              {highlighting && targetPage === pageNumber && (
                <div className="pointer-events-none absolute inset-x-6 top-8 z-10 h-28 rounded-xl border-2 border-amber-300 bg-amber-300/20 shadow-[0_0_32px_rgba(251,191,36,0.45)]" />
              )}
              <Page
                pageNumber={pageNumber}
                width={width}
                loading={<PageSpinner label="Loading page..." />}
                renderAnnotationLayer
                renderTextLayer
                className="overflow-hidden rounded-md bg-white shadow-2xl shadow-black/40"
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
    <div className="flex min-h-80 flex-col items-center justify-center gap-2 rounded-lg border border-amber-800/30 bg-amber-950/10 px-6 text-center text-slate-400">
      <AlertTriangle size={18} className="text-amber-500" />
      <div className="text-sm">Document could not be loaded</div>
      <div className="max-w-md text-xs text-slate-500">Check that the reviewer is assigned to this batch and that the PDF file exists.</div>
    </div>
  );
}

export default PdfDocumentViewer;
