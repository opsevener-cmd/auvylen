import {describe, expect, it, vi} from "vitest";
import {z} from "zod";
import {ApiError, apiRequest, formatMoney, resultSchema} from "./commercial-api";

describe("commercial API boundary", () => {
  it("submits the product identifier without an authoritative price", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ok: true})));
    await apiRequest("/orders", z.object({ok: z.boolean()}), {product_slug: "aevyra-test-analysis"}, fetcher);
    expect(JSON.parse(fetcher.mock.calls[0][1]?.body as string)).toEqual({product_slug: "aevyra-test-analysis"});
    expect(fetcher.mock.calls[0][1]?.method).toBe("POST");
    expect(fetcher.mock.calls[0][1]?.cache).toBe("no-store");
  });
  it("rejects unsuccessful API responses", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", {status: 409}));
    await expect(apiRequest("/orders", z.object({}), {}, fetcher)).rejects.toBeInstanceOf(ApiError);
  });
  it("requires an explicitly synthetic result with provenance", () => {
    const result = {analysis_id: "12345678-1234-4123-8123-123456789abc", raw_score: 0.73,
      display_score: 7.3, engine_slug: "mock", engine_version: "0.1.0", calibration_version: null,
      created_at: "2026-10-06T00:00:00Z", metadata: {synthetic: true, scored_at: "2026-10-06T00:00:00Z"}};
    expect(resultSchema.parse(result).display_score).toBe(7.3);
    expect(resultSchema.safeParse({...result, metadata: {synthetic: false}}).success).toBe(false);
    expect(resultSchema.safeParse({...result, raw_score: NaN}).success).toBe(false);
    expect(resultSchema.safeParse({...result, engine_version: undefined}).success).toBe(false);
  });
  it("formats integer minor units", () => {
    expect(formatMoney(100, "CNY")).toBe("¥1.00");
    expect(formatMoney(690, "CNY")).toBe("¥6.90");
  });
});
