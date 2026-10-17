import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/session-cookie";

/**
 * An optimistic check only: without a session cookie, go to sign-in. Whether the
 * session is valid, and what the person may see, is decided by the API on every request.
 */
export function proxy(request: NextRequest) {
  if (!request.cookies.has(SESSION_COOKIE)) {
    const url = new URL("/login", request.url);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Sign-up, password resets, email checks, invitations and shared data rooms are opened
  // without signing in.
  matcher: [
    "/((?!login|signup|forgot|reset|verify|invite|shared|_next/static|_next/image|favicon.ico).*)",
  ],
};
