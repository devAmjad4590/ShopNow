import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED = ["/cart", "/orders", "/profile"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED.some((p) => pathname.startsWith(p));

  if (isProtected) {
    const isLoggedIn = request.cookies.get("isLoggedIn")?.value === "true";
    if (!isLoggedIn) {
      return NextResponse.redirect(new URL("/auth", request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/cart/:path*", "/orders/:path*", "/profile/:path*"],
};
