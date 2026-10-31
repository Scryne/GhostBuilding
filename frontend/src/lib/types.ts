// ═══════════════════════════════════════════════════════════════════════════
// GhostBuilding — Frontend TypeScript Type Definitions
// Backend Pydantic şemalarının 1:1 TypeScript karşılıkları.
// ═══════════════════════════════════════════════════════════════════════════

// ── Enums ─────────────────────────────────────────────────────────────────

export enum AnomalyCategory {
  GHOST_BUILDING = "GHOST_BUILDING",
  HIDDEN_STRUCTURE = "HIDDEN_STRUCTURE",
  CENSORED_AREA = "CENSORED_AREA",
  IMAGE_DISCREPANCY = "IMAGE_DISCREPANCY",
}

export enum AnomalyStatus {
  PENDING = "PENDING",
  VERIFIED = "VERIFIED",
  REJECTED = "REJECTED",
  UNDER_REVIEW = "UNDER_REVIEW",
}

/** Görüntü kaynakları. API küçük harfle döner ("esri"); karşılaştırma büyük/küçük harf duyarsız. */
export enum ImageProvider {
  ESRI = "esri",
  MAPTILER = "maptiler",
  IGN = "ign",
  OSM = "osm",
  WAYBACK = "esri_wayback",
}

export enum VerificationVote {
  CONFIRM = "CONFIRM",
  DENY = "DENY",
  UNCERTAIN = "UNCERTAIN",
}

export enum UserRole {
  USER = "USER",
  MODERATOR = "MODERATOR",
  ADMIN = "ADMIN",
}

export enum ScanJobStatus {
  PENDING = "PENDING",
  RUNNING = "RUNNING",
  COMPLETED = "COMPLETED",
  FAILED = "FAILED",
}

// ── Pagination ────────────────────────────────────────────────────────────

export interface PaginationMeta {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta;
}

// ── Anomaly ───────────────────────────────────────────────────────────────

export interface AnomalyListItem {
  id: string;
  lat: number;
  lng: number;
  category: AnomalyCategory;
  confidence_score: number;
  title: string | null;
  status: AnomalyStatus;
  detected_at: string | null;
  thumbnail_url: string | null;
  location_label: string | null;
}

/** Motorun her sinyal için verdiği taban-göreli puan (50 = sıradan konumların p99'u). */
export interface ScoreBreakdown {
  pixel_diff_score: number;
  blur_censorship_score: number;
  geospatial_mismatch_score: number;
  historical_change_score: number;
  provider_disagreement_score: number;
  weighted_total: number;
  raw_max_diff?: number;
  raw_censorship?: number;
  raw_max_diff_p90?: number | null;
  raw_censorship_p90?: number | null;
  inactive_signals?: string[];
}

export interface AnomalyMeta {
  score_breakdown?: ScoreBreakdown;
  reasons?: string[];
  most_blurred_provider?: string;
  sharpest_provider?: string;
  max_diff_pair?: [string, string] | null;
  reference_site?: string;
  reference_kind?: "tesis" | "kontrol";
  reference_scan?: boolean;
  [key: string]: unknown;
}

export interface AnomalyImage {
  id: string;
  provider: string;
  image_url: string;
  captured_at: string | null;
  zoom_level: number | null;
  tile_x: number | null;
  tile_y: number | null;
  tile_z: number | null;
  diff_score: number | null;
  is_blurred: boolean;
}

export interface VerificationStats {
  total_votes: number;
  confirm_count: number;
  deny_count: number;
  uncertain_count: number;
  confirmation_rate: number;
}

export interface TimeSeriesEntry {
  date: string;
  confidence_score: number | null;
  provider_count: number | null;
  event: string | null;
}

/** Esri Wayback zaman serisi: kanıt, puan değil (sıradan şehirler de sık değişir). */
export interface AnomalyHistory {
  status: "ready" | "empty" | "pending" | "failed";
  source: string | null;
  zoom: number | null;
  generated_at: string | null;
  snapshots: { date: string; year: number; image_url: string }[];
  changes: {
    date: string;
    date_before: string;
    change_type: string;
    label: string;
    diff_score: number;
    ssim: number;
  }[];
}

export interface AnomalyDetail {
  id: string;
  lat: number;
  lng: number;
  category: AnomalyCategory;
  confidence_score: number;
  title: string | null;
  description: string | null;
  status: AnomalyStatus;
  detected_at: string | null;
  verified_at: string | null;
  source_providers: string[] | null;
  detection_methods: string[] | null;
  meta_data: AnomalyMeta | null;
  location_label: string | null;
  created_at: string | null;
  updated_at: string | null;
  images: AnomalyImage[];
  verification_stats: VerificationStats;
  time_series: TimeSeriesEntry[];
}

// ── Scan ──────────────────────────────────────────────────────────────────

export interface ScanRequest {
  lat: number;
  lng: number;
  zoom?: number;
  radius_km?: number;
}

export interface ScanResponse {
  task_id: string;
  estimated_seconds: number;
  status_url: string;
}

export interface ScanStatusResponse {
  task_id: string;
  status: "pending" | "running" | "complete" | "failed";
  progress_percent: number | null;
  current_step: string | null;
  anomaly_count: number | null;
  anomaly_urls: string[] | null;
}

// ── Tile Compare ──────────────────────────────────────────────────────────

export interface TileCompareResponse {
  lat: number;
  lng: number;
  zoom: number;
  tile_coords: { x: number; y: number; z: number };
  provider_images: Record<string, string>;
  diff_scores: Record<string, number>;
  anomaly_indicators: {
    has_significant_diff: boolean;
    max_diff_pair: string | null;
    max_diff_score: number;
    providers_missing: string[];
  };
}

// ── Stats ─────────────────────────────────────────────────────────────────

export interface CategoryCount {
  category: AnomalyCategory;
  count: number;
}

export interface StatusCount {
  status: AnomalyStatus;
  count: number;
}

export interface TopAnomaly {
  id: string;
  lat: number;
  lng: number;
  category: AnomalyCategory;
  confidence_score: number;
  title: string | null;
  status: AnomalyStatus;
}

export interface RegionDistribution {
  region: string;
  count: number;
}

export interface StatsResponse {
  total_count: number;
  by_category: CategoryCount[];
  by_status: StatusCount[];
  last_30_days_count: number;
  top_10: TopAnomaly[];
  region_distribution: RegionDistribution[];
}

// ── Auth ──────────────────────────────────────────────────────────────────

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
}

export interface RegisterResponse {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  message: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string | null;
  token_type: string;
  expires_in: number;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface LogoutRequest {
  refresh_token?: string;
}

export interface MessageResponse {
  message: string;
}

export interface UserProfile {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  trust_score: number;
  verified_count: number;
  submitted_count: number;
  is_active: boolean;
  is_verified: boolean;
  created_at: string | null;
}

/** GET /auth/me/verifications öğesi */
export interface MyVerification {
  anomaly_id: string;
  vote: VerificationVote;
  comment: string | null;
  created_at: string | null;
  category: AnomalyCategory;
  anomaly_status: AnomalyStatus;
  confidence_score: number;
  lat: number;
  lng: number;
  location_label: string | null;
}

export interface ProfileUpdateRequest {
  username?: string;
  current_password?: string;
  new_password?: string;
}

// ── Verification ──────────────────────────────────────────────────────────

export interface VerifyRequest {
  vote: VerificationVote;
  comment?: string;
}

export interface VerifyResponse {
  verification_id: string;
  vote: VerificationVote;
  is_update: boolean;
  anomaly_status: AnomalyStatus;
  new_confidence_score: number;
  message: string;
}

export interface VerificationItem {
  id: string;
  user_id: string;
  username: string;
  vote: VerificationVote;
  comment: string | null;
  is_trusted_verifier: boolean;
  vote_weight: number;
  created_at: string | null;
}

export interface VerificationSummary {
  anomaly_id: string;
  total_votes: number;
  confirm_count: number;
  deny_count: number;
  uncertain_count: number;
  weighted_confirm_count: number;
  weighted_deny_count: number;
  confirm_ratio: number;
  community_score: number;
  base_confidence: number;
  final_confidence: number;
  anomaly_status: AnomalyStatus;
  verifications: VerificationItem[];
}

// ── Map ───────────────────────────────────────────────────────────────────

export interface MapViewport {
  latitude: number;
  longitude: number;
  zoom: number;
}

export interface MapBounds {
  north: number;
  south: number;
  east: number;
  west: number;
}

// ── Generic API Error ─────────────────────────────────────────────────────

export interface ApiError {
  error: string;
  message: string;
  detail?: string;
  retry_after_seconds?: number;
}
