// ═══════════════════════════════════════════════════════════════════════════
// GhostBuilding — Auth Hook
// JWT auth state, localStorage token yönetimi, login/register/logout.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { jwtDecode } from "jwt-decode";
import {
  authApi,
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
  getApiError,
} from "@/lib/api";
import type {
  UserProfile,
  LoginRequest,
  RegisterRequest,
  UserRole,
} from "@/lib/types";

// ── JWT Payload Tipi ──────────────────────────────────────────────────────

interface JwtPayload {
  sub: string;
  role: string;
  type: string;
  exp: number;
  iat: number;
}

// ── Auth State ────────────────────────────────────────────────────────────

interface AuthState {
  /** Kullanıcı giriş yapmış mı */
  isAuthenticated: boolean;
  /** Profil yükleniyor mu */
  isLoading: boolean;
  /** Kullanıcı profili */
  user: UserProfile | null;
  /** Kullanıcı rolü (JWT'den) */
  role: UserRole | null;
  /** Hata mesajı */
  error: string | null;
}

// ── Hook Return Tipi ──────────────────────────────────────────────────────

interface UseAuthReturn extends AuthState {
  /** Email/şifre ile giriş yap */
  login: (credentials: LoginRequest) => Promise<void>;
  /** Yeni kullanıcı kaydı */
  register: (data: RegisterRequest) => Promise<string>;
  /** Oturumu kapat */
  logout: () => Promise<void>;
  /** Profil bilgisini yenile */
  refreshProfile: () => Promise<void>;
  /** Token geçerli mi kontrol et */
  isTokenValid: () => boolean;
}

// ── Token Helpers ─────────────────────────────────────────────────────────

function decodeToken(token: string): JwtPayload | null {
  try {
    return jwtDecode<JwtPayload>(token);
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const payload = decodeToken(token);
  if (!payload) return true;
  // 30 saniye tolerans
  return payload.exp * 1000 < Date.now() - 30_000;
}

// ═══════════════════════════════════════════════════════════════════════════
// useAuth Hook
// ═══════════════════════════════════════════════════════════════════════════

export function useAuth(): UseAuthReturn {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    role: null,
    error: null,
  });

  // ── Initialization — localStorage'dan token okuma ────────────────────

  useEffect(() => {
    const initAuth = async () => {
      const token = getAccessToken();

      if (!token || isTokenExpired(token)) {
        // Token yok veya süresi dolmuş — temizle
        clearTokens();
        setState({
          isAuthenticated: false,
          isLoading: false,
          user: null,
          role: null,
          error: null,
        });
        return;
      }

      // Token geçerli — profili çek
      const payload = decodeToken(token);
      try {
        const profile = await authApi.getProfile();
        setState({
          isAuthenticated: true,
          isLoading: false,
          user: profile,
          role: (payload?.role as UserRole) || null,
          error: null,
        });
      } catch {
        // Token geçersiz olmuş olabilir
        clearTokens();
        setState({
          isAuthenticated: false,
          isLoading: false,
          user: null,
          role: null,
          error: null,
        });
      }
    };

    initAuth();
  }, []);

  // ── Login ───────────────────────────────────────────────────────────

  const login = useCallback(async (credentials: LoginRequest) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const tokenResponse = await authApi.login(credentials);
      setTokens(tokenResponse.access_token, tokenResponse.refresh_token);

      const payload = decodeToken(tokenResponse.access_token);
      const profile = await authApi.getProfile();

      setState({
        isAuthenticated: true,
        isLoading: false,
        user: profile,
        role: (payload?.role as UserRole) || null,
        error: null,
      });
    } catch (err) {
      const message = getApiError(err);
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
      throw new Error(message);
    }
  }, []);

  // ── Register ────────────────────────────────────────────────────────

  const register = useCallback(
    async (data: RegisterRequest): Promise<string> => {
      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        const response = await authApi.register(data);
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: null,
        }));
        return response.message;
      } catch (err) {
        const message = getApiError(err);
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: message,
        }));
        throw new Error(message);
      }
    },
    []
  );

  // ── Logout ──────────────────────────────────────────────────────────

  const logout = useCallback(async () => {
    try {
      const refreshToken = getRefreshToken();
      await authApi.logout(
        refreshToken ? { refresh_token: refreshToken } : undefined
      );
    } catch {
      // Logout başarısız olsa bile local token'ları temizle
    } finally {
      clearTokens();
      setState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        role: null,
        error: null,
      });
    }
  }, []);

  // ── Refresh Profile ─────────────────────────────────────────────────

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await authApi.getProfile();
      setState((prev) => ({
        ...prev,
        user: profile,
      }));
    } catch {
      // Profil yenileyemiyorsa sessizce geç
    }
  }, []);

  // ── Token Validity Check ────────────────────────────────────────────

  const isTokenValid = useCallback((): boolean => {
    const token = getAccessToken();
    if (!token) return false;
    return !isTokenExpired(token);
  }, []);

  return useMemo(
    () => ({
      ...state,
      login,
      register,
      logout,
      refreshProfile,
      isTokenValid,
    }),
    [state, login, register, logout, refreshProfile, isTokenValid]
  );
}
