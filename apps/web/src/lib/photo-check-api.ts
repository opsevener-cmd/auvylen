import type {PhotoCheckResult, PhotoCheckStatus} from "@auvylen/contracts";
import {z} from "zod";
import {AccountError, csrfToken} from "./account-api";

export const photoCheckConsentVersion = "gemini-paid-v1";
export const criteria = ["lighting", "sharpness", "framing", "expression", "eye_contact", "background"] as const;
const refusal = z.enum(["no_person", "multiple_people", "not_a_photo", "appears_under_18", "explicit"]);
const count = z.number().int().min(0);
const score = z.number().int().min(1).max(10);

export const photoCheckStatusSchema: z.ZodType<PhotoCheckStatus> = z.object({
  available: z.boolean(), reason: z.enum(["ready", "disabled", "not_configured", "paid_tier_unconfirmed", "paused"]),
  consent_version: z.string(), consent_required: z.boolean(), used_today: count, daily_limit: count, max_photos: count,
});
export const photoCheckResultSchema: z.ZodType<PhotoCheckResult> = z.object({
  id: z.uuid(), engine: z.string(), model: z.string(), prompt_version: z.string(), created_at: z.string(),
  used_today: count, daily_limit: count,
  photos: z.array(z.object({
    index: count, rank: count.nullable(), usable: z.boolean(), refusal_reason: refusal.nullable(),
    scores: z.object({lighting: score, sharpness: score, framing: score, expression: score, eye_contact: score, background: score}).nullable(),
    raw_score: z.number().min(1).max(10).nullable(), display_score: z.number().min(1).max(10).nullable(),
    tips: z.array(z.string().max(200)).max(2),
  })).min(1).max(5),
});

/** Plain-language messages for the server's fixed error codes (English keys, translated in the UI). */
export const photoCheckErrors: Record<string, string> = {
  photo_check_unavailable: "Photo check is not available right now.",
  photo_check_paused: "Free photo checks are paused until tomorrow. Please come back then.",
  photo_check_daily_limit: "You have used today's free photo checks. Try again tomorrow.",
  photo_check_consent_required: "Please read and accept the photo check terms first.",
  photo_check_invalid_photos: "Use 1 to 5 JPEG or PNG photos.",
  photo_check_too_large: "These photos are too large. Try fewer or smaller photos.",
  photo_check_busy: "Photo check is busy. Wait a few seconds and try again.",
  photo_check_provider_failed: "The photo check did not finish. Nothing was charged to you. Please try again.",
  photo_check_blocked: "These photos could not be checked. Use clear photos of one adult.",
};

export function photoCheckError(status: number, body: string): AccountError {
  let detail: unknown;
  try {detail = (JSON.parse(body) as {detail?: unknown}).detail;} catch { /* Not JSON */ }
  if (typeof detail === "string" && Object.hasOwn(photoCheckErrors, detail)) return new AccountError(status, photoCheckErrors[detail]);
  const fallback: Record<number, string> = {
    401: "Sign in to check your photos.", 403: "Request could not be verified. Reload and try again.",
    413: "These photos are too large. Try fewer or smaller photos.", 429: "Too many attempts. Please try again later.",
  };
  return new AccountError(status, fallback[status] ?? "Service temporarily unavailable.");
}

export async function photoCheckRequest<T>(path: string, schema: z.ZodType<T>, body?: object): Promise<T> {
  try {
    const headers: Record<string, string> = {};
    if (body !== undefined) {headers["X-CSRF-Token"] = await csrfToken(); headers["Content-Type"] = "application/json";}
    const response = await fetch(`/api/v1/photo-check${path}`, {
      method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
      headers, body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw photoCheckError(response.status, await response.text().catch(() => ""));
    return schema.parse(await response.json());
  } catch (error) {
    if (error instanceof AccountError) throw error;
    throw new AccountError(0, "The response could not be verified. Check your connection and retry safely.");
  }
}

/** Downscale in the browser so uploads stay small; the server re-checks every photo. */
export async function shrinkPhoto(file: File, longEdge = 1024): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, longEdge / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas unavailable");
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
  return dataUrl.slice(dataUrl.indexOf(",") + 1);
}
