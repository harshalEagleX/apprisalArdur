import { NextRequest, NextResponse } from "next/server";

const JAVA = process.env.NEXT_PUBLIC_JAVA_URL ?? "http://localhost:8080";

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
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
