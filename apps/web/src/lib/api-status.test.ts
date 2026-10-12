import {describe, expect, it, vi} from "vitest";
import {getApiStatus} from "./api-status";

const response = (body: unknown, status = 200) => vi.fn<typeof fetch>().mockResolvedValue(
  new Response(JSON.stringify(body), {status}),
);

describe("API status", () => {
  it("recognizes a ready API", async () => {
    const fetcher = response({status: "ready", dependencies: {database: "ok", redis: "ok"}});
    expect((await getApiStatus("http://localhost:8000", fetcher)).reachable).toBe(true);
    expect(fetcher.mock.calls[0][1]?.cache).toBe("no-store");
  });
  it("distinguishes an available API from failing dependencies", async () => {
    const fetcher = response({status: "not_ready", dependencies: {database: "unavailable", redis: "ok"}}, 503);
    const state = await getApiStatus("http://localhost:8000", fetcher);
    expect(state.reachable).toBe(true);
    expect(state.readiness?.status).toBe("not_ready");
  });
  it("handles network failure", async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline"));
    expect((await getApiStatus("http://localhost:8000", fetcher)).reachable).toBe(false);
  });
  it.each([
    [{status: "ready"}, 200],
    [{status: "ready", dependencies: {database: "unavailable", redis: "ok"}}, 200],
    [{status: "ready", dependencies: {database: "ok", redis: "ok"}}, 500],
  ])("rejects malformed or inconsistent responses", async (body, code) => {
    expect((await getApiStatus("http://localhost:8000", response(body, code))).reachable).toBe(false);
  });
});
