import {describe, expect, it} from "vitest";
import {allowedApiPath, requestBodyLimit} from "./api-proxy-policy";
import {archetypeLabels, archetypes, bandLabels, photoCheckError, photoCheckErrors, photoCheckResultSchema, photoCheckStatusSchema} from "./photo-check-api";
import zh from "./i18n/zh-CN.json";

const photo = {index: 0, rank: 1, usable: true, refusal_reason: null, raw_score: 7.5, display_score: 7.5, tips: ["Face the window"], quality_passed: true,
  scores: {lighting: 7, sharpness: 8, framing: 7, expression: 8, eye_contact: 7, background: 8},
  appearance: {strengths: ["Warm smile"], flattering: ["Soft side light"], tips: ["Try navy"], band: 3},
  roast: {lines: ["That ceiling light is auditioning for a crime drama."], vibe: "hk_film_lead_90s"}};
const result = {id: "6b0b2f1e-4b5c-4d3e-9f10-2a3b4c5d6e7f", engine: "gemini-photo-check", model: "gemini-3.5-flash-lite", advanced: false,
  prompt_version: "photo-appearance-v1", created_at: "2026-11-25T09:00:00Z", funding: "free_signup", credits_charged: 0,
  free_checks_now: 3, next_free_on: null, photos: [photo]};
const status = {available: false, reason: "paused", consent_version: "gemini-paid-v2", consent_required: false,
  free_checks_now: 0, free_signup_remaining: 0, next_free_on: "2026-11-30", credit_cost: 1, credit_balance: 0,
  roast_available: true, max_photos: 5};

describe("photo check client", () => {
  it("accepts only well-formed results", () => {
    expect(photoCheckResultSchema.parse(result).photos[0].appearance?.band).toBe(3);
    const broken = (changes: object) => ({...result, photos: [{...photo, ...changes}]});
    expect(() => photoCheckResultSchema.parse(broken({scores: {...photo.scores, lighting: 11}}))).toThrow();
    expect(() => photoCheckResultSchema.parse(broken({appearance: {...photo.appearance, band: 5}}))).toThrow();
    expect(() => photoCheckResultSchema.parse(broken({appearance: {...photo.appearance, band: 2.5}}))).toThrow();
    // A vibe is always a known style, never free text such as a person's name.
    expect(() => photoCheckResultSchema.parse(broken({roast: {lines: [], vibe: "Tony Leung"}}))).toThrow();
    expect(() => photoCheckResultSchema.parse({...result, photos: Array(6).fill(photo)})).toThrow();
    expect(photoCheckStatusSchema.parse(status).next_free_on).toBe("2026-11-30");
  });
  it("requires the quality gate flag on every photo", () => {
    const {quality_passed: _omitted, ...withoutGate} = photo;
    void _omitted;
    expect(() => photoCheckResultSchema.parse({...result, photos: [withoutGate]})).toThrow();
    const below = {...photo, raw_score: 5.8, display_score: 5.8, quality_passed: false, appearance: null, roast: null};
    expect(photoCheckResultSchema.parse({...result, photos: [below]}).photos[0].quality_passed).toBe(false);
  });
  it("says whether the advanced model was used", () => {
    expect(photoCheckResultSchema.parse({...result, model: "gemini-4-hydrogen", advanced: true}).advanced).toBe(true);
    const {advanced: _omitted, ...withoutFlag} = result;
    void _omitted;
    expect(() => photoCheckResultSchema.parse(withoutFlag)).toThrow();
  });
  it("maps fixed server codes to plain messages and never shows raw bodies", () => {
    expect(photoCheckError(503, JSON.stringify({detail: "photo_check_paused"})).message).toBe(photoCheckErrors.photo_check_paused);
    expect(photoCheckError(409, JSON.stringify({detail: "photo_check_insufficient_credits"})).message).toBe(photoCheckErrors.photo_check_insufficient_credits);
    expect(photoCheckError(500, JSON.stringify({detail: "Traceback: secret"})).message).toBe("Service temporarily unavailable.");
    expect(photoCheckError(401, "").message).toBe("Sign in to check your photos.");
  });
  it("has Chinese copy for every message, band and vibe, without 颜值打分", () => {
    const keys = [...Object.values(photoCheckErrors), ...Object.values(bandLabels), ...Object.values(archetypeLabels), "Sign in to check your photos."];
    for (const key of keys) expect(Object.hasOwn(zh, key), key).toBe(true);
    expect(Object.keys(archetypeLabels).sort()).toEqual([...archetypes].sort());
    for (const value of Object.values(zh as Record<string, string>)) expect(value).not.toContain("颜值打分");
  });
  it("lets the same-origin proxy reach only the photo check routes, with the upload limit", () => {
    for (const path of ["v1/photo-check/status", "v1/photo-check/consent", "v1/photo-check/analyses"]) expect(allowedApiPath(path)).toBe(true);
    expect(allowedApiPath("v1/photo-check/analyses/123")).toBe(false);
    expect(requestBodyLimit("v1/photo-check/analyses")).toBe(6 * 1024 * 1024);
    expect(requestBodyLimit("v1/photo-check/consent")).toBe(1024 * 1024);
  });
});
