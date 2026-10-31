import {describe, expect, it} from "vitest";
import {activeModelVersions, extractorSchema, metric, modelSchema, predictionSchema} from "./model-api";
import {allowedApiPath} from "./api-proxy-policy";

describe("pretrained feature selection contracts", () => {
  it("exposes availability and provenance without granting weight routes", () => {
    expect(extractorSchema.parse({id: "mobilenetv3-small-imagenet-onnx-v1", available: false,
      reason: "Checkpoint unavailable", manifest: {weight_license: "Apache-2.0"}}).available).toBe(false);
    expect(allowedApiPath("v1/research/preferences/extractors")).toBe(true);
    expect(allowedApiPath("v1/research/preferences/extractors/mobilenet/weights")).toBe(false);
    expect(allowedApiPath("v1/research/preferences/models/download")).toBe(false);
  });
  it("hides soft-deleted model versions from the normal list", () => {
    const datasetId = "00000000-0000-4000-8000-000000000001";
    const deletedId = "00000000-0000-4000-8000-000000000002";
    const otherId = "00000000-0000-4000-8000-000000000003";
    const ready = modelSchema.parse({
      id: datasetId, dataset_id: datasetId, project_id: datasetId, training_job_id: datasetId,
      version: 1, state: "READY", extractor: "rgb-grid-texture-v1", implementation: "test",
      configuration: {}, metrics: null, limitations: [], created_at: "2026-10-31",
      completed_at: "2026-10-31", expires_at: "2027-01-01",
    });
    const deleted = {...ready, id: deletedId, state: "DELETED" as const};
    const other = {...ready, id: otherId, dataset_id: otherId};
    expect(activeModelVersions([ready, deleted, other], datasetId).map(m => m.id)).toEqual([datasetId]);
  });
  it("keeps missing historical metrics explicit and refuses synthetic predictions", () => {
    expect(metric(undefined)).toBe("Unavailable");
    expect(metric(Number.NaN)).toBe("Unavailable");
    expect(predictionSchema.safeParse({synthetic: true}).success).toBe(false);
  });
});
