import type {ResearchJob, ResearchStatus} from "@auvylen/contracts";
import {z} from "zod";

export const researchJobSchema: z.ZodType<ResearchJob> = z.object({
  id: z.uuid(), provider: z.string(), kind: z.string(),
  status: z.enum(["QUEUED", "RUNNING", "COMPLETED", "FAILED"]),
  result: z.record(z.string(), z.unknown()).nullable(), failure_reason: z.string().nullable(),
  created_at: z.string(), completed_at: z.string().nullable(),
});
export const researchStatusSchema: z.ZodType<ResearchStatus> = z.object({
  enabled: z.boolean(), authorized: z.boolean(), synthetic_available: z.boolean(),
  providers: z.array(z.object({slug: z.string(), display_name: z.string(), available: z.boolean(), reason: z.string()})),
});
export const researchScoreSchema = z.object({
  raw_score: z.number().finite(), display_score: z.number().finite(), engine: z.string(),
  version: z.string(), timestamp: z.string(), synthetic: z.literal(true),
});
