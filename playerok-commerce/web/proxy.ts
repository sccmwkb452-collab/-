import { NextResponse, type NextRequest } from "next/server";

// Fast gate: pages of the panel need a session cookie. The real check is done by
// the API on every request (an expired or revoked cookie gets 401 and the client
// returns to /login).
export function proxy(request: NextRequest) {
  if (!request.cookies.has("pac_session")) {
    const url = new URL("/login", request.url);
    const next = request.nextUrl.pathname + request.nextUrl.search;
    if (next !== "/") url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|login|_next/static|_next/image|favicon.ico|icon.svg|robots.txt).*)"],
};
