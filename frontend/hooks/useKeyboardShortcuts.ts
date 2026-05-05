"use client";
import { useEffect, useRef } from "react";

/**
 * Attaches a stable keydown listener that never re-registers.
 * The handler map is kept in a ref so callers can update shortcuts
 * every render without the event listener being removed and re-added.
 *
 * @param shortcuts  A map of key identifiers to handlers.
 *                   Keys are matched after the whole-shortcut object is
 *                   read from the ref on every keydown event.
 * @param enabled    When false the listener is a no-op (still attached,
 *                   just skips immediately). Defaults to true.
 */
export function useKeyboardShortcuts(
  shortcuts: (e: KeyboardEvent) => void,
  enabled = true,
): void {
  // Store the latest handler in a ref so the event listener closure never goes stale
  const handlerRef = useRef<(e: KeyboardEvent) => void>(shortcuts);
  handlerRef.current = shortcuts;

  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

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
