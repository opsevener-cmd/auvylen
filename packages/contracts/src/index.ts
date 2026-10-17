/** Wire contract for GET /ready; validated at the frontend network boundary. */
export type DependencyStatus = "ok" | "unavailable";
export interface ReadinessResponse {
  status: "ready" | "not_ready";
  dependencies: { database: DependencyStatus; redis: DependencyStatus };
}

export type OrderStatus = "CREATED" | "PENDING_PAYMENT" | "PAID" | "FULFILLING" | "COMPLETED" | "FAILED" | "CANCELLED" | "REFUNDED";
export interface Product {
  id: string; slug: string; name: string; description: string; product_type: string;
  price_amount: number; currency: string; active: boolean;
}
export interface Order {
  public_order_id: string; product: Product; provider: string; amount: number;
  currency: string; status: OrderStatus; created_at: string; paid_at: string | null;
  completed_at: string | null; analysis_id: string | null;
}
export interface Payment {
  payment_id: string; provider: string; status: "PENDING" | "SUCCEEDED" | "FAILED" | "REFUNDED";
  amount: number; currency: string;
}
export interface Analysis {
  id: string; scoring_engine_slug: string; status: "CREATED" | "PROCESSING" | "COMPLETED" | "FAILED";
  created_at: string; started_at: string | null; completed_at: string | null; failure_reason: string | null;
}
export interface AnalysisResult {
  analysis_id: string; raw_score: number; display_score: number; engine_slug: string;
  engine_version: string; calibration_version: string | null; created_at: string;
  metadata: {synthetic: true; scored_at: string; [key: string]: unknown};
}
export interface AccountUser {public_user_id: string; login_identifier: string; role: "user" | "owner"}
export interface CreditEntry {id: string; amount: number; transaction_type: string; balance_after: number; created_at: string}
export interface Account {user: AccountUser; wallet: {balance: number; transactions: CreditEntry[]}; analyses: Analysis[]}
export interface CreditProduct {slug: string; name: string; credit_cost: number; available: boolean}
export interface RedemptionResult {credits_added: number; balance: number}
export interface ResearchJob {
  progress: number; phase: string; payload: Record<string, unknown> | null;
  id: string;
  provider: string;
  kind: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  result: Record<string, unknown> | null;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ResearchStatus {
  enabled: boolean;
  authorized: boolean;
  synthetic_available: boolean;
  providers: {slug: string; display_name: string; available: boolean; reason: string}[];
}

export interface PreferenceProject {id: string; name: string; created_at: string}
export interface PreferenceDataset extends PreferenceProject {
  project_id: string; source: string; source_url: string; license: string;
  rating_min: number; rating_max: number; archived: boolean; expires_at: string;
  image_count: number; rated_count: number; compared_count: number;
}
export interface PreferenceImage {
  id: string; dataset_id: string; width: number; height: number;
  subject_group: string | null; excluded: boolean; created_at: string;
  score: number | null; rating_recorded: boolean;
}
export interface PreferencePair {
  id: string; left_id: string; right_id: string;
  choice: "left" | "right" | "equal" | "skip"; updated_at: string;
}
export interface PreferenceDetail {
  dataset: PreferenceDataset; images: PreferenceImage[]; pairs: PreferencePair[];
}

export interface PersonalModel {
  id: string; dataset_id: string | null; project_id: string; version: number;
  state: "TRAINING" | "READY" | "FAILED" | "ARCHIVED" | "DELETED";
  training_job_id: string; extractor: string; implementation: string;
  configuration: Record<string, unknown>; metrics: Record<string, unknown> | null;
  limitations: string[]; created_at: string; completed_at: string | null; expires_at: string;
}

export interface EngineMetadata {
  slug: string; display_name: string; version: string; licensing_status: string;
  provenance: string; commercial_allowed: boolean; research_allowed: boolean;
  production_enabled: boolean; synthetic: boolean;
}

export interface FeatureExtractor {
  id: string; available: boolean; reason: string; manifest: Record<string, unknown>;
}

export type AdminValue = string | number | boolean | null | AdminValue[] | {[key: string]: AdminValue};
export interface AdminPage {items: Record<string, AdminValue>[]; total: number; page: number; page_size: number}
export interface AdminResult {data: Record<string, AdminValue>}
export interface OwnerOverview {
  counts: Record<string, number>; jobs: Record<string, number>; credits: Record<string, number>;
  health: Record<string, AdminValue>; providers: Record<string, AdminValue>[];
  extractors: Record<string, AdminValue>[]; usage: Record<string, AdminValue>[]; quotas: Record<string, number>;
  environment: string; research_enabled: boolean; free_product_access: true;
}
