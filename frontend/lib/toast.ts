type ToastType = "success" | "error" | "info" | "warning";

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number; // ms — 0 = persist until dismissed
}

type Listener = (toasts: ToastItem[]) => void;

let items: ToastItem[] = [];
const listeners: Set<Listener> = new Set();

function notify() {
  listeners.forEach(fn => fn([...items]));
}

function add(type: ToastType, title: string, message?: string, duration = 5000) {
  const id = Math.random().toString(36).slice(2);
  items = [...items, { id, type, title, message, duration }];
  notify();
  if (duration > 0) {
    setTimeout(() => dismiss(id), duration);
  }
  return id;
}

export function dismiss(id: string) {
  items = items.filter(t => t.id !== id);
  notify();
}

export function subscribe(fn: Listener) {
  listeners.add(fn);
  fn([...items]);
  return () => listeners.delete(fn);
}

export const toast = {
  success: (title: string, message?: string) => add("success", title, message),
  error:   (title: string, message?: string) => add("error",   title, message, 8000),
  info:    (title: string, message?: string) => add("info",    title, message),
  warning: (title: string, message?: string) => add("warning", title, message, 6000),
};
