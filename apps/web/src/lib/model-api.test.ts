import {describe, expect, it} from "vitest";
import {extractorSchema, metric, predictionSchema} from "./model-api";
import {allowedApiPath} from "./api-proxy-policy";

describe("pretrained feature selection contracts", () => {
  it("exposes availability and provenance without granting weight routes", () => {
    expect(extractorSchema.parse({id: "mobilenetv3-small-imagenet-onnx-v1", available: false,
      reason: "Checkpoint unavailable", manifest: {weight_license: "Apache-2.0"}}).available).toBe(false);
    expect(allowedApiPath("v1/research/preferences/extractors")).toBe(true);
    expect(allowedApiPath("v1/research/preferences/extractors/mobilenet/weights")).toBe(false);
    expect(allowedApiPath("v1/research/preferences/models/download")).toBe(false);
  });
  it("keeps missing historical metrics explicit and refuses synthetic predictions", () => {
    expect(metric(undefined)).toBe("Unavailable");
    expect(metric(Number.NaN)).toBe("Unavailable");
    expect(predictionSchema.safeParse({synthetic: true}).success).toBe(false);
  });
});
