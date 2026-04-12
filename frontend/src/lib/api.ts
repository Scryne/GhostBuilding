// ═══════════════════════════════════════════════════════════════════════════
// GhostBuilding — Typed API Client
// Axios tabanlı, JWT interceptor'lu, tüm backend endpoint'leri typed.
// ═══════════════════════════════════════════════════════════════════════════

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from "axios";
import type {
  PaginatedResponse,
  AnomalyListItem,
  AnomalyDetail,
  ScanRequest,
  ScanResponse,
  ScanStatusResponse,
  TileCompareResponse,
  StatsResponse,
  RegisterRequest,
  RegisterResponse,
  LoginRequest,
  TokenResponse,
  RefreshRequest,
  LogoutRequest,
  MessageResponse,
  UserProfile,
  ProfileUpdateRequest,
  VerifyRequest,
  VerifyResponse,
  VerificationSummary,
  ApiError,
} from "./types";

// ── Base URL ──────────────────────────────────────────────────────────────

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ── Token Yönetimi ────────────────────────────────────────────────────────

const TOKEN_KEY = "ghostbuilding_access_token";
const REFRESH_KEY = "ghostbuilding_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh?: string | null): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, access);
  if (refresh) {
    localStorage.setItem(REFRESH_KEY, refresh);
  }
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// ── Axios Instance ────────────────────────────────────────────────────────

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor — JWT token ekle
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — 401'de otomatik refresh dene
let isRefreshing = false;
let failedQueue: {
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
}[] = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // 401 ve henüz retry yapılmadıysa
    if (error.response?.status === 401 && !originalRequest._retry) {
      const refreshToken = getRefreshToken();

      // Refresh token yoksa direkt reject
      if (!refreshToken) {
        clearTokens();
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Zaten refresh yapılıyor — kuyruğa ekle
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return api(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const { data } = await axios.post<TokenResponse>(
          `${API_BASE_URL}/auth/refresh`,
          { refresh_token: refreshToken }
        );

        setTokens(data.access_token, data.refresh_token);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        }

        processQueue(null, data.access_token);
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearTokens();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ── API Helper ────────────────────────────────────────────────────────────

export function getApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data) {
      if (typeof data === "string") return data;
      if (typeof data.message === "string") return data.message;
      if (typeof data.detail === "string") return data.detail;
      if (typeof data.detail === "object" && data.detail?.message) {
        return data.detail.message;
      }
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Bilinmeyen bir hata oluştu.";
}

// ═══════════════════════════════════════════════════════════════════════════
// AUTH ENDPOINTS
// ═══════════════════════════════════════════════════════════════════════════

export const authApi = {
  /** POST /auth/register — Yeni kullanıcı kaydı */
  register: (body: RegisterRequest) =>
    api.post<RegisterResponse>("/auth/register", body).then((r) => r.data),

  /** POST /auth/login — Giriş yap, token al */
  login: (body: LoginRequest) =>
    api.post<TokenResponse>("/auth/login", body).then((r) => r.data),

  /** POST /auth/refresh — Token yenile */
  refresh: (body: RefreshRequest) =>
    api.post<TokenResponse>("/auth/refresh", body).then((r) => r.data),

  /** POST /auth/logout — Oturumu kapat */
  logout: (body?: LogoutRequest) =>
    api.post<MessageResponse>("/auth/logout", body || {}).then((r) => r.data),

  /** GET /auth/me — Profil bilgisi */
  getProfile: () =>
    api.get<UserProfile>("/auth/me").then((r) => r.data),

  /** PATCH /auth/me — Profil güncelle */
  updateProfile: (body: ProfileUpdateRequest) =>
    api.patch<UserProfile>("/auth/me", body).then((r) => r.data),
};

// ═══════════════════════════════════════════════════════════════════════════
// ANOMALY ENDPOINTS
// ═══════════════════════════════════════════════════════════════════════════

export interface AnomalyListParams {
  lat?: number;
  lng?: number;
  radius_km?: number;
  category?: string;
  min_confidence?: number;
  status?: string;
  page?: number;
  limit?: number;
}

export const anomalyApi = {
  /** GET /anomalies — Anomali listesi (mekansal + filtre) */
  list: (params?: AnomalyListParams) =>
    api
      .get<PaginatedResponse<AnomalyListItem>>("/anomalies/", { params })
      .then((r) => r.data),

  /** GET /anomalies/:id — Anomali detayı */
  getById: (id: string) =>
    api.get<AnomalyDetail>(`/anomalies/${id}`).then((r) => r.data),

  /** GET /anomalies/stats — İstatistikler */
  getStats: () =>
    api.get<StatsResponse>("/anomalies/stats").then((r) => r.data),

  /** POST /anomalies/scan — Tarama başlat */
  startScan: (body: ScanRequest) =>
    api.post<ScanResponse>("/anomalies/scan", body).then((r) => r.data),

  /** GET /anomalies/scan/:taskId/status — Tarama durumu */
  getScanStatus: (taskId: string) =>
    api
      .get<ScanStatusResponse>(`/anomalies/scan/${taskId}/status`)
      .then((r) => r.data),

  /** GET /anomalies/tiles/compare — Tile karşılaştırma */
  compareTiles: (params: {
    lat: number;
    lng: number;
    zoom?: number;
    providers?: string[];
  }) =>
    api
      .get<TileCompareResponse>("/anomalies/tiles/compare", { params })
      .then((r) => r.data),
};

// ═══════════════════════════════════════════════════════════════════════════
// VERIFICATION ENDPOINTS
// ═══════════════════════════════════════════════════════════════════════════

export const verificationApi = {
  /** POST /anomalies/:id/verify — Oy ver */
  verify: (anomalyId: string, body: VerifyRequest) =>
    api
      .post<VerifyResponse>(`/anomalies/${anomalyId}/verify`, body)
      .then((r) => r.data),

  /** GET /anomalies/:id/verifications — Doğrulama özeti */
  getSummary: (anomalyId: string, page?: number, limit?: number) =>
    api
      .get<VerificationSummary>(`/anomalies/${anomalyId}/verifications`, {
        params: { page, limit },
      })
      .then((r) => r.data),
};

// ── SWR Fetcher ───────────────────────────────────────────────────────────

export const swrFetcher = <T>(url: string): Promise<T> =>
  api.get<T>(url).then((r) => r.data);

export default api;
