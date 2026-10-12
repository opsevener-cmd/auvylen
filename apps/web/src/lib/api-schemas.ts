import type {Analysis, AnalysisResult, Order, Payment, Product} from "@auvylen/contracts";
import {z} from "zod";

const money = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
export const productSchema: z.ZodType<Product> = z.object({
  id: z.uuid(), slug: z.string(), name: z.string(), description: z.string(),
  product_type: z.string(), price_amount: money, currency: z.string(), active: z.boolean(),
});
export const orderSchema: z.ZodType<Order> = z.object({
  public_order_id: z.string(), product: productSchema, provider: z.string(),
  amount: money, currency: z.string(),
  status: z.enum(["CREATED", "PENDING_PAYMENT", "PAID", "FULFILLING", "COMPLETED", "FAILED", "CANCELLED", "REFUNDED"]),
  created_at: z.string(), paid_at: z.string().nullable(), completed_at: z.string().nullable(), analysis_id: z.uuid().nullable(),
});
export const paymentSchema: z.ZodType<Payment> = z.object({
  payment_id: z.uuid(), provider: z.string(), status: z.enum(["PENDING", "SUCCEEDED", "FAILED", "REFUNDED"]),
  amount: money, currency: z.string(),
});
export const analysisSchema: z.ZodType<Analysis> = z.object({
  id: z.uuid(), scoring_engine_slug: z.string(), status: z.enum(["CREATED", "PROCESSING", "COMPLETED", "FAILED"]),
  created_at: z.string(), started_at: z.string().nullable(), completed_at: z.string().nullable(), failure_reason: z.string().nullable(),
});
export const resultSchema: z.ZodType<AnalysisResult> = z.object({
  analysis_id: z.uuid(), raw_score: z.number().finite(), display_score: z.number().finite(),
  engine_slug: z.string(), engine_version: z.string(), calibration_version: z.string().nullable(),
  metadata: z.object({synthetic: z.literal(true), scored_at: z.string()}).catchall(z.unknown()), created_at: z.string(),
});

