"use client";
import { useEffect, useRef } from "react";

/**
 * Attaches a stable keydown listener that never re-registers.
 * The handler is kept in a ref so callers can pass a brand-new closure
 * every render without the event listener being removed and re-added.
 *
 * IMPORTANT — do NOT wrap the handler in `useCallback(..., [])` at the call
 * site. This hook already solves the "listener churn" problem; a frozen
 * handler identity instead defeats the ref refresh and permanently traps the
 * closure on first-render state (null session tokens, empty lists), so every
 * guard inside it fails and the shortcuts go silently dead. Pass the handler
 * inline, or memoise it only with a complete dependency list.
 *
 * @param shortcuts  Keydown handler. Re-read from the ref on every event, so
 *                   it always sees the values of the most recent render.
 * @param enabled    When false the listener is a no-op (still attached,
 *                   just skips immediately). Defaults to true.
 */
export function useKeyboardShortcuts(
  shortcuts: (e: KeyboardEvent) => void,
  enabled = true,
): void {
  // Store the latest handler in a ref so the event listener closure never goes stale
  const handlerRef = useRef<(e: KeyboardEvent) => void>(shortcuts);
  const enabledRef = useRef(enabled);

  useEffect(() => {
    handlerRef.current = shortcuts;
    enabledRef.current = enabled;
  }, [enabled, shortcuts]);

  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (!enabledRef.current) return;
      handlerRef.current(e);
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
    // Empty deps: the listener is attached once and reads from refs on every call.
  }, []);
}

export default useKeyboardShortcuts;
