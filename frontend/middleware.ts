import { NextRequest, NextResponse } from "next/server";
import { JAVA } from "@/lib/config";

const PUBLIC_PATHS = ["/login"];
const ADMIN_PATHS  = ["/admin", "/analytics"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.some(p => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const cookie = request.headers.get("cookie") ?? "";

  let role: string | null = null;
  try {
    const res = await fetch(`${JAVA}/api/me`, {
      headers: { cookie },
      cache: "no-store",
    });
    if (res.ok) {
      const data = await res.json() as { role?: string };
      role = data.role ?? null;
    }
  } catch {
    // backend unreachable — redirect to login
  }

  if (!role) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  const isAdminPath = ADMIN_PATHS.some(p => pathname.startsWith(p));
  if (isAdminPath && role !== "ADMIN") {
    return NextResponse.redirect(new URL("/reviewer/queue", request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Exclude ALL Next.js internals (not just static/image): the dev HMR
  // websocket lives at /_next/webpack-hmr (+ Turbopack HMR). The old matcher
  // only skipped _next/static|_next/image, so the HMR upgrade hit this auth
  // middleware and got redirected to /login — which kills the ws connection
  // ("WebSocket connection to ws://…/_next/webpack-hmr failed"). Skipping all
  // of _next leaves auth gating on real routes intact while letting HMR through.
  matcher: ["/((?!_next|favicon.ico).*)"],
};
