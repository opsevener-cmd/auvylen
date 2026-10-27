import {z} from "zod";
import type {AestheticAnalysis, AestheticModelCard, AestheticResult, AestheticStatus, AestheticUploadMetadata} from "@auvylen/contracts";
import {sendImage, type UploadProgress} from "./upload";

export const aestheticPath = "/research/aesthetic";
const finite = z.number().finite();
const nullableFinite = finite.nullable();
export const modelCardSchema: z.ZodType<AestheticModelCard> = z.object({
  model_version: z.string(), calibration_version: z.string(), implementation: z.string(), extractor: z.string(),
  dataset_name: z.string(), dataset_license: z.string(), annotator_population: z.string(), synthetic: z.boolean(),
  test_images: z.number().int(), test_subjects: z.number().int(), test_mae: finite, mean_baseline_mae: finite,
  test_spearman: nullableFinite, test_distribution_loss: finite, mean_distribution_baseline_loss: finite,
  interval_level: finite, interval_half_width: nullableFinite, interval_test_coverage: nullableFinite,
});
export const aestheticStatusSchema: z.ZodType<AestheticStatus> = z.object({
  enabled: z.boolean(), authorized: z.boolean(), available: z.boolean(), reason: z.string(),
  model: modelCardSchema.nullable(), limitations: z.array(z.string()),
});
export const aestheticResultSchema: z.ZodType<AestheticResult> = z.object({
  raw_score: finite, display_score: finite, engine: z.string(), version: z.string(), calibration_version: z.string(),
  timestamp: z.string(), synthetic: z.boolean(), score_10: finite.min(1).max(10), expected_rating_5: finite.min(1).max(5),
  rating_distribution: z.array(finite.min(0).max(1)).length(5), rating_spread_10: finite, interval_level: finite,
  interval_low: nullableFinite, interval_high: nullableFinite, extractor: z.string(), processing_duration_ms: finite.nonnegative(),
  adult_basis: z.literal("user_attestation"), single_subject_basis: z.literal("user_attestation"),
  automated_face_detection: z.literal("not_implemented"),
});
export const aestheticAnalysisSchema: z.ZodType<AestheticAnalysis> = z.object({
  id: z.uuid(), status: z.enum(["QUEUED", "RUNNING", "COMPLETED", "FAILED"]), progress: z.number().int().min(0).max(100),
  phase: z.string(), failure_reason: z.string().nullable(), model_version: z.string(), image_retained: z.boolean(),
  result: aestheticResultSchema.nullable(), created_at: z.string(), completed_at: z.string().nullable(),
});
/** Fixed server vocabulary → user-facing explanation key. Unknown reasons stay unavailable. */
export const unavailableReasons: Record<string, string> = {
  disabled: "Aesthetic scoring is switched off until an authorized dataset and a validated model are installed.",
  checkpoint_not_configured: "No validated aesthetic model has been configured by the operator.",
  checkpoint_missing: "The configured aesthetic model is not installed.",
  checkpoint_integrity_failure: "The installed aesthetic model failed its integrity check and has been disabled.",
  validation_gate_failed: "The installed aesthetic model has not passed validation and is disabled.",
  extractor_unavailable: "The reviewed visual feature extractor required by the model is not installed.",
};
export function unavailableReason(reason: string): string {
  return unavailableReasons[reason] ?? "Aesthetic scoring is unavailable.";
}
export function submitAnalysis(file: File, metadata: AestheticUploadMetadata, token: string, progress: (value: UploadProgress) => void, signal?: AbortSignal): Promise<AestheticAnalysis> {
  return sendImage(`${aestheticPath}/analyses`, file, metadata, aestheticAnalysisSchema, token, progress, signal);
}
export function percent(value: number): string {return `${(value * 100).toFixed(1)}%`;}
