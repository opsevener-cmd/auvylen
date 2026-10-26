import {describe, expect, it} from "vitest";
import {requestError} from "./account-api";
import {allowedApiPath} from "./api-proxy-policy";
import {aestheticAnalysisSchema, aestheticResultSchema, aestheticStatusSchema, unavailableReason} from "./aesthetic-api";

const result = {
  raw_score: 3.4, display_score: 6.4, engine: "auvylen-aesthetic", version: "v1", calibration_version: "v1+split-conformal-90",
  timestamp: "2026-10-26T00:00:00+00:00", synthetic: false, score_10: 6.4, expected_rating_5: 3.4,
  rating_distribution: [0.05, 0.15, 0.3, 0.35, 0.15], rating_spread_10: 2.4, interval_level: 0.9, interval_low: 5.1,
  interval_high: 7.7, extractor: "mobilenetv3-small-imagenet-onnx-v1", processing_duration_ms: 42,
  adult_basis: "user_attestation", single_subject_basis: "user_attestation", automated_face_detection: "not_implemented",
};
describe("aesthetic wire contracts", () => {
  it("accepts a complete versioned result", () => {
    expect(aestheticResultSchema.parse(result)).toEqual(result);
    expect(aestheticAnalysisSchema.parse({id: "00000000-0000-4000-8000-000000000001", status: "COMPLETED", progress: 100, phase: "Completed", failure_reason: null, model_version: "v1", image_retained: false, result, created_at: "2026-10-26", completed_at: "2026-10-26"}).result?.score_10).toBe(6.4);
  });
  it("rejects malformed scores and distributions instead of displaying them", () => {
    for (const bad of [{score_10: 11}, {expected_rating_5: 0.5}, {rating_distribution: [0.2, 0.2, 0.2, 0.2, 0.1, 0.1]}, {rating_distribution: [1.2, 0, 0, 0, 0]}, {calibration_version: undefined}, {automated_face_detection: "passed"}]) {
      expect(aestheticResultSchema.safeParse({...result, ...bad}).success).toBe(false);
    }
  });
  it("explains fixed unavailability reasons and treats unknown ones as unavailable", () => {
    expect(aestheticStatusSchema.parse({enabled: false, authorized: true, available: false, reason: "disabled", model: null, limitations: []}).available).toBe(false);
    expect(unavailableReason("validation_gate_failed")).toContain("has not passed validation");
    expect(unavailableReason("anything-else")).toBe("Aesthetic scoring is unavailable.");
    expect(requestError("/research/aesthetic/analyses", 503).message).toContain("no validated model");
    expect(requestError("/research/aesthetic/analyses", 415).message).toBe("Choose a JPEG or PNG image.");
  });
});

it("proxies only the exact aesthetic analysis routes", () => {
  const id = "00000000-0000-4000-8000-000000000001";
  for (const path of ["v1/research/aesthetic/status", "v1/research/aesthetic/analyses", `v1/research/aesthetic/analyses/${id}`, `v1/research/aesthetic/analyses/${id}/delete`]) expect(allowedApiPath(path), path).toBe(true);
  for (const path of ["v1/research/aesthetic", "v1/research/aesthetic/checkpoint", `v1/research/aesthetic/analyses/${id}/content`, "v1/research/aesthetic/analyses/../../owner/users", "v1/research/aesthetic/models"]) expect(allowedApiPath(path), path).toBe(false);
});
