// Server-only visibility of unfinished or unavailable product areas. Hidden areas keep their
// code but are removed from navigation and answer 404, so production users never reach an
// "unavailable" page. API-side gates (research policy, AESTHETIC_SCORING_ENABLED, production
// mock-commerce routes) are unchanged and still apply when a page is shown.
import {isPublicPilot} from "./environment";

export type Features = {
  /** Phase 6 /research/aesthetic page. */
  aesthetic: boolean;
  /** Native Auvylen research preview (/research/native-preview). */
  nativePreview: boolean;
  /** Synthetic /analyze, /result and analysis history. Never in production. */
  syntheticAnalysis: boolean;
  /** Mock checkout and simulated payment pages. Never in production or the public pilot. */
  mockCheckout: boolean;
};

/**
 * PREVIEW_FEATURES_ENABLED: "true" or "false"; unset or empty follows APP_ENV
 * (off in production, on in development and staging).
 */
export function previewFeaturesEnabled(): boolean {
  const value = process.env.PREVIEW_FEATURES_ENABLED ?? "";
  if (value === "true") return true;
  if (value === "false") return false;
  if (value !== "") throw new Error("PREVIEW_FEATURES_ENABLED must be true or false");
  return (process.env.APP_ENV ?? "development") !== "production";
}

export function features(): Features {
  const preview = previewFeaturesEnabled();
  const production = process.env.APP_ENV === "production";
  const synthetic = preview && !production;
  return {
    aesthetic: preview,
    nativePreview: preview,
    syntheticAnalysis: synthetic,
    mockCheckout: synthetic && !isPublicPilot() && process.env.MOCK_CHECKOUT_ENABLED !== "false",
  };
}
