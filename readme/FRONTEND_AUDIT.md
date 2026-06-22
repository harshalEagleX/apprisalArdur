# Frontend Audit — SHAL (Next.js 16 / React 19)

Scope: full `frontend/` review (~15.2k LOC across 18 pages, 50+ components, 9 lib modules,
5 hooks) on branch `uat`, 2026-06-22. Verified against current source, not memory.

## Verdict
**Solid, mature frontend.** Clean architecture (logic extracted to tested `lib/` modules),
strong security posture (HttpOnly-cookie auth, no token in JS, no XSS sinks), and excellent
loading/empty/error-state coverage. No P1 blockers. The gaps are deployment-config (middleware
URL, security headers), test depth (no render tests), and minor a11y/UX polish.

## Findings by severity

| # | Sev | Area | Finding | Fix |
|---|-----|------|---------|-----|
| 1 | **P2** | Deploy/Auth | `middleware.ts` calls `${JAVA}/api/me` **server-side**, but `JAVA` = `NEXT_PUBLIC_JAVA_URL` (browser-facing). On a split host / Docker, `localhost:8080` is wrong from inside the frontend server → every auth check fails → redirect loop. Works on a single local host only. | Add a server-only `JAVA_INTERNAL_URL` (e.g. `http://java-backend:8080`) and use it in middleware; keep `NEXT_PUBLIC_JAVA_URL` for browser calls. |
| 2 | **P2** | Security | `next.config.ts` is empty — **no security headers** (CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, HSTS). Clickjacking + MIME-sniff exposure on the HTML the Next server returns. | Add an async `headers()` returning at least `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and a CSP. |
| 3 | **P2** | Testing | No component/DOM tests. vitest runs in `node` env with no `jsdom`/`@testing-library/react`, so `include` only covers `lib/**` + `hooks/**` pure logic. The 899-LOC verify page, `RuleCard`, dialogs render untested. | Add `jsdom` + `@testing-library/react`; render-test the reviewer verify flow + StatusBadge (incl. BLOCKED). |
| 4 | P3 | Deps | **Dead dependencies**: `axios` (imported nowhere — `fetch` is used everywhere) and `@react-pdf-viewer/core` (only `react-pdf` is used in `PdfDocumentViewer`). | Remove both from `package.json` → smaller install. |
| 5 | P3 | Deps | `lucide-react: "^1.11.0"` — unusual major (upstream lucide-react is `0.x`). It resolves & builds, but verify it's the intended package/range. | Confirm the installed version is what's intended; pin if so. |
| 6 | P3 | UX | After login, `app/login/page.tsx` always redirects to `/`. It ignores the `?next=` that `middleware.ts` sets and the `?expired=1` flag from `useSessionExpiry`. User isn't returned to the page they wanted; no "session expired" message. | Read `searchParams.get("next")` (validate it's a local path) and redirect there; surface `expired=1` as a notice. |
| 7 | P3 | A11y | Form `<label>`s aren't associated with inputs (no `htmlFor`/`id`) — e.g. login. 6 `onClick` handlers on `div`/`span` without `role`/keyboard support. | Add `htmlFor`+`id` pairs; convert clickable divs to `<button>` or add `role`+`onKeyDown`. |
| 8 | P3 | Build robustness | PDF worker path `new URL("react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url)` depends on nested `node_modules` layout — fragile under hoisting/pnpm. | Resolve `pdfjs-dist` as a direct dep and point the worker at the top-level path. |
| 9 | P3 | UX/Resilience | `apiFetch` treats any network `TypeError` as auth failure and redirects to `/login`. A transient network blip mid-session bounces the user to login (losing context). | Distinguish a true 401 from a network error; show a retry/toast for the latter. |
| 10 | P3 | Perf | `getAllUsers` paginates sequentially (`await` in a loop). Fine at the 50-user target; would be slow at scale. | Acceptable now; parallelize/`Promise.all` if user count grows. |
| 11 | Info | UAT | `DeviceGate` blocks viewports `<768px` (phones) by design. UAT testers must use tablet/desktop. | Document in the UAT scenarios / access pack. |

## What's already done well (keep)
- **Auth & secrets**: JWT lives in the **HttpOnly cookie**; JS never stores the token (only a
  session-expiry *timestamp* in `sessionStorage`). `login()` establishes both the jwt cookie and
  a Spring session (for WS handshake); `logout()` clears both. Verified `SESSION_TTL_MS` (24h)
  **matches** `JwtUtils.java:45` exactly.
- **CSRF**: cookie is `SameSite=strict` (`application.yml`), the primary CSRF defense for a
  cookie-auth SPA.
- **XSS**: zero `dangerouslySetInnerHTML`, `eval`, `innerHTML`, `document.write`; React escaping
  is relied on throughout. API error messages are passed through `sanitizeErrorMessage`.
- **Data layer** (`lib/api.ts`): one `apiFetch` with `AbortController` timeouts (30s data / 90s
  OCR), structured timeline logging, and explicit 401/403/429 handling.
- **Resilience**: `app/error.tsx` boundary + `not-found.tsx`; `useWebSocket` reconnects with
  backoff and tolerates malformed frames (REST polling fallback); offline detection on the verify
  page; review-session locking via `useReviewSession`.
- **State coverage**: `EmptyState` (8 files), `Skeleton` (9), `Spinner` (9); 16/18 pages have
  `try/catch`. The "unverified empty/error states" concern is largely satisfied in code (visual
  QA still recommended).
- **Architecture/DRY**: heavy page logic extracted to tested modules (`reviewVerify.ts`,
  `ruleStatus.ts`, `ruleLanguage.ts`, `ruleEvidence.ts`, `displayName.ts`, `duration.ts`); base
  URL centralized in `lib/config.ts`; PDF viewer lazy-loaded via `dynamic(ssr:false)`.
- **Type discipline**: only **1** `any`, only **6** `console.*` across the codebase; eslint clean.
- **Legacy cleanup**: the old unauthenticated `qc-review` Python-direct demo is now just a safe
  redirect to `/reviewer/queue`.

## Tests added this session
`frontend/middleware.test.ts` — 7 cases pinning the auth/role gate (the #1 regression risk from
`REGRESSION_AUDIT.md`): public-path bypass, unauth→`/login?next=…`, backend-unreachable→`/login`,
ADMIN allowed on admin paths, REVIEWER blocked from `/admin` + `/analytics`→`/reviewer/queue`,
REVIEWER allowed on reviewer paths. **Suite: 42/42 green, lint clean.**

## Recommended order
1. **P2 #1 + #2** before any non-localhost deploy (middleware internal URL + security headers).
2. **P2 #3** test depth (jsdom + testing-library; render the verify flow).
3. **P3 #4–#9** polish (dead deps, login `next`, a11y, pdf worker path).
