// ═══════════════════════════════════════════════════════════════════════════
// GhostBuilding — Next.js Proxy (Next 16'da middleware'in yeni adı)
// Korumalı route'lar için JWT token doğrulama ve yönlendirme. Token, istemcinin
// setTokens() ile yazdığı çerezden okunur (lib/api.ts).
// /profile, /verify gibi sayfalar giriş gerektirir.
// ═══════════════════════════════════════════════════════════════════════════

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// ── Korumalı Route Tanımları ──────────────────────────────────────────────

/** Giriş gerektiren route prefix'leri */
const PROTECTED_ROUTES = ["/profile", "/verify", "/settings", "/dashboard"];

/** Auth sayfaları — giriş yapmışsa ana sayfaya yönlendir */
const AUTH_ROUTES = ["/auth/login", "/auth/register"];

/** Token çerez / localStorage key */
const TOKEN_KEY = "ghostbuilding_access_token";

// ── JWT Decode (Edge runtime uyumlu, minimal) ─────────────────────────────

interface JwtPayload {
  sub: string;
  role: string;
  type: string;
  exp: number;
  iat: number;
}

function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    // Base64url → Base64 → decode
    const payload = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/");

    const decoded = atob(payload);
    return JSON.parse(decoded) as JwtPayload;
  } catch {
    return null;
  }
}

function isTokenValid(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload) return false;

  // Süre kontrolü (30 saniye tolerans)
  const now = Math.floor(Date.now() / 1000);
  return payload.exp > now - 30;
}

// ── Proxy ─────────────────────────────────────────────────────────────

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // ── Token kontrolü ──────────────────────────────────────────
  // Proxy localStorage'ı göremez; istemci token'ı ayrıca çereze yazar (lib/api.ts).
  // Eskiden çerez hiç yazılmıyordu: giriş yapmış kullanıcı da profile giremiyordu.

  const token =
    request.cookies.get(TOKEN_KEY)?.value ||
    request.headers.get("Authorization")?.replace("Bearer ", "") ||
    null;

  const hasValidToken = token ? isTokenValid(token) : false;

  // ── Korumalı route'lar — giriş gerekli ──────────────────────
  const isProtectedRoute = PROTECTED_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/")
  );

  if (isProtectedRoute && !hasValidToken) {
    const loginUrl = new URL("/auth/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // ── Auth sayfaları — zaten giriş yapmışsa yönlendir ─────────
  const isAuthRoute = AUTH_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/")
  );

  if (isAuthRoute && hasValidToken) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  // Güvenlik başlıkları (CSP dahil) tek yerde: next.config.mjs → headers().
  const response = NextResponse.next();

  return response;
}

// ── Matcher — Hangi route'larda çalışsın ──────────────────────────────────

export const config = {
  matcher: [
    /*
     * Tüm sayfalar için çalış, ancak şunları hariç tut:
     * - api route'ları
     * - static dosyalar (_next/static, _next/image, favicon.ico)
     */
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
};
