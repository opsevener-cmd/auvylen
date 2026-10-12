import type {Account, CreditProduct, RedemptionResult} from "@auvylen/contracts";
import {z} from "zod";
import {analysisSchema} from "./api-schemas";

const credits = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER);
export const accountSchema: z.ZodType<Account> = z.object({
  user: z.object({public_user_id: z.string(), login_identifier: z.string()}),
  wallet: z.object({balance: credits, transactions: z.array(z.object({
    id: z.uuid(), amount: z.number().int(), transaction_type: z.string(),
    balance_after: credits, created_at: z.string(),
  }))}), analyses: z.array(analysisSchema),
});
export const creditProductsSchema: z.ZodType<CreditProduct[]> = z.array(z.object({
  slug: z.string(), name: z.string(), credit_cost: credits, available: z.boolean(),
}));
export const redemptionSchema: z.ZodType<RedemptionResult> = z.object({credits_added: credits, balance: credits});
export const sessionSchema = z.object({
  user: z.object({public_user_id: z.string(), login_identifier: z.string()}), csrf_token: z.string(),
});

export class AccountError extends Error {
  constructor(public status: number, message: string) {super(message);}
}

export async function accountRequest<T>(path: string, schema: z.ZodType<T>, body?: object): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) {
    const response = await fetch("/api/v1/auth/csrf", {cache: "no-store", credentials: "same-origin"});
    if (!response.ok) throw new AccountError(response.status, "Service temporarily unavailable.");
    const csrf = z.object({csrf_token: z.string()}).parse(await response.json());
    headers["X-CSRF-Token"] = csrf.csrf_token;
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
    headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const messages: Record<number, string> = {
      400: "Code is invalid, expired or already used.", 401: "Sign in required or invalid credentials.",
      403: "Request could not be verified. Reload and try again.",
      404: "This service is unavailable.",
      409: path === "/auth/register" ? "Account could not be created with this identifier." : "Insufficient Credits or conflicting request.",
      422: "Check the fields and try again.", 429: "Too many attempts. Please try again later.",
    };
    const preferenceMessages: Record<number, string> = {
      403: "Research access or request verification required.",
      404: "Dataset or image is unavailable, expired or deleted.",
      409: "The selected data/model is unavailable, archived, excluded or pending deletion.",
      413: "Image upload exceeds the size limit.",
      422: "Check consent, images and rating scale. Training needs 8 ratings, 5 independent groups and varied scores in the training split.",
      429: "Upload capacity, request rate or private storage quota reached. Try again later.",
    };
    throw new AccountError(response.status, (path.startsWith("/research/preferences") ? preferenceMessages[response.status] : undefined)
      ?? messages[response.status] ?? "Service temporarily unavailable.");
  }
  return schema.parse(await response.json());
}
