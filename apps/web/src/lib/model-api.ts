import {z} from "zod";
import type {FeatureExtractor, PersonalModel} from "@auvylen/contracts";
export const modelSchema: z.ZodType<PersonalModel> = z.object({
  id: z.uuid(), dataset_id: z.uuid().nullable(), project_id: z.uuid(), version: z.number().int().positive(),
  state: z.enum(["TRAINING", "READY", "FAILED", "ARCHIVED", "DELETED"]), training_job_id: z.uuid(),
  extractor: z.string(), implementation: z.string(), configuration: z.record(z.string(), z.unknown()),
  metrics: z.record(z.string(), z.unknown()).nullable(), limitations: z.array(z.string()),
  created_at: z.string(), completed_at: z.string().nullable(), expires_at: z.string(),
});
export const predictionSchema = z.object({
  model_id: z.uuid(), model_version: z.number().int(), input_image_id: z.uuid(),
  raw_score: z.number().finite(), display_score: z.number().finite(), score_min: z.number(), score_max: z.number(),
  processing_duration_ms: z.number().nonnegative(), seen_in_training_snapshot: z.boolean(),
  synthetic: z.literal(false), prediction_type: z.literal("subjective_rating"), timestamp: z.string(),
});
export function metric(value: unknown): string {return typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : "Unavailable";}

export const extractorSchema: z.ZodType<FeatureExtractor> = z.object({
  id: z.string(), available: z.boolean(), reason: z.string(), manifest: z.record(z.string(), z.unknown()),
});
