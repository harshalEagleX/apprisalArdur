/**
 * Shared runtime configuration.
 *
 * `JAVA` is the base URL of the Java backend.
 *
 * Resolution order:
 *  1. NEXT_PUBLIC_JAVA_URL — explicit override (production / custom backend host).
 *  2. In the browser — the SAME host the app was loaded from, on port 8080. This
 *     makes it work on http://localhost:3000 AND http://<LAN-IP>:3000 with no
 *     per-machine config: open the app at an IP and the API calls follow to that
 *     same IP:8080.
 *  3. Server-side (middleware / SSR) — localhost:8080 (the backend is local to
 *     the Next server process).
 */
function resolveJava(): string {
  const override = process.env.NEXT_PUBLIC_JAVA_URL;
  if (override && override.trim()) return override.trim();

  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8080`;
  }

  return "http://localhost:8080";
}

export const JAVA = resolveJava();
