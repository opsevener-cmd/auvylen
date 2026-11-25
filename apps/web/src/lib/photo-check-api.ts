import type {PhotoCheckResult, PhotoCheckStatus} from "@auvylen/contracts";
import {z} from "zod";
import {AccountError, csrfToken} from "./account-api";

export const photoCheckConsentVersion = "gemini-paid-v2";
export const criteria = ["lighting", "sharpness", "framing", "expression", "eye_contact", "background"] as const;
export const archetypes = ["hk_film_lead_90s", "indie_band_frontman", "old_money_weekend", "city_pop_album_cover",
  "film_camera_diary", "campus_drama_lead", "street_style_snap", "art_house_poster", "sunday_brunch_regular",
  "startup_keynote", "travel_vlogger", "late_night_jazz_bar"] as const;
/** English keys, translated in the UI. A style, never a person. */
export const archetypeLabels: Record<(typeof archetypes)[number], string> = {
  hk_film_lead_90s: "90s Hong Kong film lead", indie_band_frontman: "Indie band frontman",
  old_money_weekend: "Old-money weekend", city_pop_album_cover: "City-pop album cover",
  film_camera_diary: "Film-camera diary", campus_drama_lead: "Campus drama lead",
  street_style_snap: "Street-style snap", art_house_poster: "Art-house film poster",
  sunday_brunch_regular: "Sunday brunch regular", startup_keynote: "Startup keynote energy",
  travel_vlogger: "Travel vlogger", late_night_jazz_bar: "Late-night jazz bar",
};
/** The AI impression bands (owner copy). Chinese avoids "颜值打分". */
export const bandLabels: Record<1 | 2 | 3 | 4, string> = {1: "What🫣🤣", 2: "Average🧐", 3: "Attractive🥹", 4: "Striking😘🤩"};
const refusal = z.enum(["no_person", "not_a_photo", "cannot_analyse"]);
const count = z.number().int().min(0);
const score = z.number().int().min(1).max(10);
const lines = (max: number) => z.array(z.string().min(1).max(200)).max(max);

export const photoCheckStatusSchema: z.ZodType<PhotoCheckStatus> = z.object({
  available: z.boolean(), reason: z.enum(["ready", "disabled", "not_configured", "paid_tier_unconfirmed", "paused"]),
  consent_version: z.string(), consent_required: z.boolean(), free_checks_now: count, free_signup_remaining: count,
  next_free_on: z.iso.date().nullable(), credit_cost: count, credit_balance: count, roast_available: z.boolean(), max_photos: count,
});
export const photoCheckResultSchema: z.ZodType<PhotoCheckResult> = z.object({
  id: z.uuid(), engine: z.string(), model: z.string(), prompt_version: z.string(), created_at: z.string(),
  funding: z.enum(["free_signup", "free_weekly", "credits", "owner"]), credits_charged: count,
  free_checks_now: count, next_free_on: z.iso.date().nullable(),
  photos: z.array(z.object({
    index: count, rank: count.nullable(), usable: z.boolean(), refusal_reason: refusal.nullable(),
    scores: z.object({lighting: score, sharpness: score, framing: score, expression: score, eye_contact: score, background: score}).nullable(),
    raw_score: z.number().min(1).max(10).nullable(), display_score: z.number().min(1).max(10).nullable(),
    tips: lines(2), quality_passed: z.boolean(),
    appearance: z.object({strengths: lines(3), flattering: lines(3), tips: lines(3),
      band: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)])}).nullable(),
    roast: z.object({lines: lines(2), vibe: z.enum(archetypes).nullable()}).nullable(),
  })).min(1).max(5),
});

/** Plain-language messages for the server's fixed error codes (English keys, translated in the UI). */
export const photoCheckErrors: Record<string, string> = {
  photo_check_unavailable: "Photo check is not available right now.",
  photo_check_paused: "Photo checks are paused until tomorrow. Please come back then.",
  photo_check_consent_required: "Please read and accept the photo check terms first.",
  photo_check_confirmation_required: "Please confirm that this is you and you're 18 or older.",
  photo_check_insufficient_credits: "You've used your free checks. Add Credits on your Account page to keep going.",
  photo_check_invalid_photos: "Use 1 to 5 JPEG or PNG photos.",
  photo_check_too_large: "These photos are too large. Try fewer or smaller photos.",
  photo_check_busy: "Photo check is busy. Wait a few seconds and try again.",
  photo_check_provider_failed: "The photo check didn't finish. You weren't charged. Please try again.",
  photo_check_blocked: "We can't analyse these photos. Use clear photos of just you.",
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
