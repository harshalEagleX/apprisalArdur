"use client";

import { useEffect, useRef } from "react";

export default function CursorGridGlow() {
  const timeoutRef = useRef<number | null>(null);
  const frameRef = useRef<number | null>(null);
  const pointRef = useRef({ x: -9999, y: -9999 });

  useEffect(() => {
    const root = document.documentElement;

    const commitPoint = () => {
      root.style.setProperty("--cursor-x", `${pointRef.current.x}px`);
      root.style.setProperty("--cursor-y", `${pointRef.current.y}px`);
      root.classList.add("cursor-grid-active");
      frameRef.current = null;

      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(() => {
        root.classList.remove("cursor-grid-active");
      }, 1000);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      pointRef.current = { x: event.clientX, y: event.clientY };
      if (!frameRef.current) {
        frameRef.current = window.requestAnimationFrame(commitPoint);
      }
    };

    window.addEventListener("pointermove", handlePointerMove, { passive: true });

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      root.classList.remove("cursor-grid-active");
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      if (frameRef.current) window.cancelAnimationFrame(frameRef.current);
    };
  }, []);

  return <div aria-hidden="true" className="cursor-grid-glow" />;
}
