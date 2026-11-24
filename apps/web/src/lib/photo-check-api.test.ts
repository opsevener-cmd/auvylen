import {describe, expect, it} from "vitest";
import {allowedApiPath, requestBodyLimit} from "./api-proxy-policy";
import {photoCheckError, photoCheckErrors, photoCheckResultSchema, photoCheckStatusSchema} from "./photo-check-api";
import zh from "./i18n/zh-CN.json";

const photo = {index: 0, rank: 1, usable: true, refusal_reason: null, raw_score: 7.5, display_score: 7.5, tips: ["Face the window"],
  scores: {lighting: 7, sharpness: 8, framing: 7, expression: 8, eye_contact: 7, background: 8}};
const result = {id: "6b0b2f1e-4b5c-4d3e-9f10-2a3b4c5d6e7f", engine: "gemini-photo-quality", model: "gemini-3.5-flash-lite",
  prompt_version: "photo-quality-v1", created_at: "2026-11-24T09:00:00Z", used_today: 1, daily_limit: 30, photos: [photo]};

describe("free photo check client", () => {
  it("accepts only well-formed results", () => {
    expect(photoCheckResultSchema.parse(result).photos[0].rank).toBe(1);
    expect(() => photoCheckResultSchema.parse({...result, photos: [{...photo, scores: {...photo.scores, lighting: 11}}]})).toThrow();
    expect(() => photoCheckResultSchema.parse({...result, photos: Array(6).fill(photo)})).toThrow();
    expect(photoCheckStatusSchema.parse({available: false, reason: "paused", consent_version: "gemini-paid-v1",
      consent_required: false, used_today: 0, daily_limit: 30, max_photos: 5}).reason).toBe("paused");
  });
  it("maps fixed server codes to plain messages and never shows raw bodies", () => {
    expect(photoCheckError(503, JSON.stringify({detail: "photo_check_paused"})).message).toBe(photoCheckErrors.photo_check_paused);
    expect(photoCheckError(500, JSON.stringify({detail: "Traceback: secret"})).message).toBe("Service temporarily unavailable.");
    expect(photoCheckError(401, "").message).toBe("Sign in to check your photos.");
  });
  it("has a Chinese translation for every message", () => {
    for (const message of Object.values(photoCheckErrors)) expect(Object.hasOwn(zh, message), message).toBe(true);
    expect(Object.hasOwn(zh, "Sign in to check your photos.")).toBe(true);
  });
  it("lets the same-origin proxy reach only the photo check routes, with the upload limit", () => {
    for (const path of ["v1/photo-check/status", "v1/photo-check/consent", "v1/photo-check/analyses"]) expect(allowedApiPath(path)).toBe(true);
    expect(allowedApiPath("v1/photo-check/analyses/123")).toBe(false);
    expect(requestBodyLimit("v1/photo-check/analyses")).toBe(6 * 1024 * 1024);
    expect(requestBodyLimit("v1/photo-check/consent")).toBe(1024 * 1024);
  });
});
