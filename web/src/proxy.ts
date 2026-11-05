import { type NextRequest, NextResponse } from "next/server";

import { FLASH_COOKIE, FLASH_HEADER, decodeFlash, encodeFlash } from "@/lib/flash";
import { SESSION_COOKIE } from "@/lib/session-cookie";

// The website, sign-up, password resets, email checks, invitations, shared data rooms and the
// legal pages are opened without signing in.
const OPEN = /^\/(welcome|pricing|contact|security|\.well-known|login|signup|forgot|reset|verify|invite|shared|check|legal)(\/|$)/;

/**
 * An optimistic check only: without a session cookie, "/" shows the website (the demo's first
 * screen on the public demo) and anything else
 * goes to sign-in. Whether the session is valid, and what the person may see, is decided by the
 * API on every request.
 *
 * Also hands the result of a form sent before the page's scripts loaded to the page it came
 * from, once (see `settled`).
 */
export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (!request.cookies.has(SESSION_COOKIE)) {
    // The public demo opens on its first screen, the choice of what to see; the website is still
    // at /welcome.
    if (path === "/") {
      return NextResponse.rewrite(new URL(process.env.LEKHARA_DEMO === "1" ? "/login" : "/welcome", request.url));
    }
    if (!OPEN.test(path)) return NextResponse.redirect(new URL("/login", request.url));
  }
  const forwarded = new Headers(request.headers);
  forwarded.delete(FLASH_HEADER);
  const flash = decodeFlash(request.cookies.get(FLASH_COOKIE)?.value);
  if (flash === null || flash.path !== path || request.method !== "GET") {
    return NextResponse.next({ request: { headers: forwarded } });
  }
  forwarded.set(FLASH_HEADER, encodeFlash(flash));
  const response = NextResponse.next({ request: { headers: forwarded } });
  response.cookies.delete(FLASH_COOKIE);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
