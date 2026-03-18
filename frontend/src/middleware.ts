/**
 * Next.js edge middleware — runs before every request.
 *
 * Route rules:
 *  /login, /register  → redirect to / if already logged in
 *  /admin/*           → require login + admin role
 *  everything else    → require login (except /login, /register, /api/*)
 *
 * The middleware reads a lightweight "auth-session" cookie that the backend
 * sets alongside the httpOnly refresh token.  This cookie contains:
 *   { loggedIn: true, role: "user"|"admin" }
 * It is NOT the JWT — just a routing hint.  Real auth is enforced by the backend.
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];
const API_PREFIX = "/api";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Never intercept API proxy routes or Next internals
  if (pathname.startsWith(API_PREFIX) || pathname.startsWith("/_next")) {
    return NextResponse.next();
  }

  const sessionCookie = request.cookies.get("auth-session")?.value;
  let session: { loggedIn?: boolean; role?: string } = {};
  try {
    if (sessionCookie) session = JSON.parse(decodeURIComponent(sessionCookie));
  } catch { /* malformed cookie → treat as logged out */ }

  const isLoggedIn = session.loggedIn === true;
  const isAdmin = session.role === "admin";

  // Already logged in → redirect away from auth pages
  if (isLoggedIn && PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.redirect(new URL("/query", request.url));
  }

  // Not logged in → redirect to login
  if (!isLoggedIn && !PUBLIC_PATHS.includes(pathname)) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Admin check
  if (pathname.startsWith("/admin") && isLoggedIn && !isAdmin) {
    return NextResponse.redirect(new URL("/query?error=forbidden", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths EXCEPT:
     * - _next/static, _next/image, favicon, public files
     * - /api/* (handled by Next.js proxy)
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
