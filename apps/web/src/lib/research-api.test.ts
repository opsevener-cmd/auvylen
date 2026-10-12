import {describe, expect, it} from "vitest";
import {researchJobSchema, researchScoreSchema} from "./research-api";

describe("research wire boundary", () => {
  it("validates a queued job without inventing a result", () => {
    const job = researchJobSchema.parse({id: "10000000-0000-4000-8000-000000000001", provider: "mock", kind: "SCORE",
      status: "QUEUED", result: null, failure_reason: null, created_at: "2026-10-10", completed_at: null});
    expect(job.result).toBeNull();
  });
  it("requires the synthetic marker before showing a mock score", () => {
    expect(researchScoreSchema.safeParse({raw_score: 0.7, display_score: 7, engine: "mock", version: "0.1.0",
      timestamp: "2026-10-10", synthetic: false}).success).toBe(false);
  });
});
