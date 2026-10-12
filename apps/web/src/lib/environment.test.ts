import {afterEach, describe, expect, it, vi} from "vitest";
import {getApiUrl, isPublicPilot, requireCommercialAccess} from "./environment";

afterEach(() => vi.unstubAllEnvs());
describe("deployment environment", () => {
  it("blocks commercial calls in the public pilot", () => {
    vi.stubEnv("APP_ENV", "staging");
    vi.stubEnv("PUBLIC_PILOT", "true");
    vi.stubEnv("PUBLIC_BASE_URL", "https://pilot.example.test");
    expect(isPublicPilot()).toBe(true);
    expect(() => requireCommercialAccess()).toThrow("disabled");
  });
  it.each(["http://example.com", "https://localhost", "https://127.0.0.1", "https://example.com/", "https://example.com/path", "https://user:secret@example.com"])("rejects invalid pilot origin %s", value => {
    vi.stubEnv("APP_ENV", "staging");
    vi.stubEnv("PUBLIC_PILOT", "true");
    vi.stubEnv("PUBLIC_BASE_URL", value);
    expect(() => isPublicPilot()).toThrow("Invalid PUBLIC_BASE_URL");
  });
  it("requires an explicit deployment API URL", () => {
    vi.stubEnv("APP_ENV", "production");
    vi.stubEnv("API_URL", undefined);
    expect(() => getApiUrl()).toThrow("API_URL is required");
  });
  it("blocks production commercial calls", () => {
    vi.stubEnv("APP_ENV", "production");
    expect(() => requireCommercialAccess()).toThrow("disabled");
  });
  it("allows staging to use internal service URLs", () => {
    vi.stubEnv("APP_ENV", "staging");
    vi.stubEnv("API_URL", "http://api:8000");
    expect(getApiUrl()).toBe("http://api:8000");
    expect(() => requireCommercialAccess()).not.toThrow();
  });
  it("rejects credentials in the frontend API URL", () => {
    vi.stubEnv("API_URL", "http://user:password@api:8000");
    expect(() => getApiUrl()).toThrow("Invalid API_URL");
  });
});
