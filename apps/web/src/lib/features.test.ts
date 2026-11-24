import {afterEach, describe, expect, it, vi} from "vitest";
import {features, previewFeaturesEnabled} from "./features";

afterEach(() => vi.unstubAllEnvs());
const none = {aesthetic: false, nativePreview: false, syntheticAnalysis: false, mockCheckout: false};

describe("unfinished feature visibility", () => {
  it("hides every unfinished feature in production by default", () => {
    vi.stubEnv("APP_ENV", "production");
    vi.stubEnv("PREVIEW_FEATURES_ENABLED", undefined);
    expect(features()).toEqual(none);
    vi.stubEnv("PREVIEW_FEATURES_ENABLED", "");
    expect(features()).toEqual(none);
  });
  it("never enables synthetic analysis or mock checkout in production", () => {
    vi.stubEnv("APP_ENV", "production");
    vi.stubEnv("PREVIEW_FEATURES_ENABLED", "true");
    vi.stubEnv("MOCK_CHECKOUT_ENABLED", "true");
    expect(features()).toEqual({aesthetic: true, nativePreview: true, syntheticAnalysis: false, mockCheckout: false});
  });
  it("keeps development and staging behaviour unless explicitly disabled", () => {
    vi.stubEnv("APP_ENV", "staging");
    expect(features()).toEqual({aesthetic: true, nativePreview: true, syntheticAnalysis: true, mockCheckout: true});
    vi.stubEnv("MOCK_CHECKOUT_ENABLED", "false");
    expect(features().mockCheckout).toBe(false);
    expect(features().syntheticAnalysis).toBe(true);
    vi.stubEnv("PREVIEW_FEATURES_ENABLED", "false");
    expect(features()).toEqual(none);
  });
  it("rejects ambiguous flag values", () => {
    vi.stubEnv("PREVIEW_FEATURES_ENABLED", "yes");
    expect(() => previewFeaturesEnabled()).toThrow("PREVIEW_FEATURES_ENABLED");
  });
});
