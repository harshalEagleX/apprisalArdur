/**
 * Regression coverage for the auth/role gate in middleware.ts.
 *
 * This is the #1 regression risk (REGRESSION_AUDIT.md): the middleware gates EVERY
 * non-public route, so a mistake here either locks out valid users or exposes admin
 * pages. These tests pin the contract: public bypass, unauth → /login, role-based
 * admin gating, and graceful redirect when the backend is unreachable.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock next/server so we can run the middleware in a plain node env and capture
// which branch it took without the Next runtime.
vi.mock("next/server", () => ({
  NextResponse: {
    next: vi.fn(() => ({ kind: "next" })),
    redirect: vi.fn((url: URL) => ({ kind: "redirect", location: url.toString() })),
  },
}));
vi.mock("@/lib/config", () => ({ JAVA: "http://java.test" }));

import { middleware } from "./middleware";

type Resp = { kind: "next" } | { kind: "redirect"; location: string };

function req(pathname: string, cookie = "") {
  return {
    nextUrl: { pathname },
    url: `http://app.test${pathname}`,
    headers: { get: (k: string) => (k.toLowerCase() === "cookie" ? cookie : null) },
  } as unknown as Parameters<typeof middleware>[0];
}

/** Make global.fetch resolve as if /api/me returned the given role (or 401 when null). */
function mockMe(role: string | null) {
  globalThis.fetch = vi.fn(async () =>
    role
      ? ({ ok: true, json: async () => ({ role }) } as Response)
      : ({ ok: false, json: async () => ({}) } as Response),
  ) as unknown as typeof fetch;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("middleware auth/role gate", () => {
  it("lets the public /login path through without calling the backend", async () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
    const res = (await middleware(req("/login"))) as Resp;
    expect(res.kind).toBe("next");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("redirects unauthenticated users to /login with the original path as ?next", async () => {
    mockMe(null);
    const res = (await middleware(req("/admin/users"))) as Resp;
    expect(res.kind).toBe("redirect");
    expect(res).toMatchObject({ location: expect.stringContaining("/login") });
    expect((res as { location: string }).location).toContain("next=%2Fadmin%2Fusers");
  });

  it("redirects to /login when the backend is unreachable (fetch throws)", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const res = (await middleware(req("/reviewer/queue"))) as Resp;
    expect(res.kind).toBe("redirect");
    expect((res as { location: string }).location).toContain("/login");
  });

  it("allows an ADMIN onto an admin path", async () => {
    mockMe("ADMIN");
    const res = (await middleware(req("/admin/batches"))) as Resp;
    expect(res.kind).toBe("next");
  });

  it("blocks a REVIEWER from an admin path, redirecting to the reviewer queue", async () => {
    mockMe("REVIEWER");
    const res = (await middleware(req("/admin/batches"))) as Resp;
    expect(res.kind).toBe("redirect");
    expect((res as { location: string }).location).toContain("/reviewer/queue");
  });

  it("blocks a REVIEWER from the analytics (admin) area", async () => {
    mockMe("REVIEWER");
    const res = (await middleware(req("/analytics"))) as Resp;
    expect(res.kind).toBe("redirect");
    expect((res as { location: string }).location).toContain("/reviewer/queue");
  });

  it("allows a REVIEWER onto a reviewer path", async () => {
    mockMe("REVIEWER");
    const res = (await middleware(req("/reviewer/queue"))) as Resp;
    expect(res.kind).toBe("next");
  });
});
