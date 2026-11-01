import {afterEach, describe, expect, it, vi} from "vitest";
import {accountRequest, accountSchema, freshOwnerSignIn, redemptionSchema, requestError} from "./account-api";

afterEach(() => vi.unstubAllGlobals());

describe("safe research authorization feedback", () => {
  const path = "/research/preferences/datasets/test/images";
  it.each([
    ["Research access required", "Research permission is not enabled"],
    ["CSRF validation failed", "Request verification expired"],
    ["Request origin rejected", "Request origin rejected"],
  ])("distinguishes %s without leaking response fields", (detail, expected) => {
    expect(requestError(path, 403, JSON.stringify({detail, token: "secret"})).message).toContain(expected);
  });
  it("keeps unknown errors generic and private", () => {
    expect(requestError(path, 403, JSON.stringify({detail: "private secret"})).message).toBe("Research access or request verification required.");
    expect(requestError(path, 403, "not json").message).not.toContain("not json");
  });
});

describe("native research preview feedback", () => {
  const path = "/research/native-preview/jobs";
  it("separates fresh sign-in, Owner-only and verification failures", () => {
    expect(requestError(path, 403, JSON.stringify({detail: "Fresh Owner sign-in required for this operation"})).message).toBe(freshOwnerSignIn);
    expect(requestError(path, 403, JSON.stringify({detail: "Owner authorization required"})).message).toContain("Only the Owner");
    expect(requestError(path, 403, JSON.stringify({detail: "private secret"})).message).toBe("Request could not be verified. Reload and try again.");
  });
  it("explains disabled, expired and rate-limited states without a fallback score", () => {
    expect(requestError(path, 503).message).toContain("No score was generated");
    expect(requestError(path + "/x", 404).message).toContain("expired or was deleted");
    expect(requestError(path, 429).message).toContain("same photograph");
    expect(requestError(path, 500).status).toBe(500);
  });
});

describe("account contracts and mutations", () => {
  it("validates integer balances and transaction history", () => {
    const account = {user: {public_user_id: "usr_example", login_identifier: "pilot", role: "user"},
      wallet: {balance: 9, transactions: []}, analyses: []};
    expect(accountSchema.parse(account).wallet.balance).toBe(9);
    expect(() => accountSchema.parse({...account, wallet: {...account.wallet, balance: -1}})).toThrow();
    expect(() => redemptionSchema.parse({credits_added: 0.5, balance: 1})).toThrow();
  });
  it("uses same-origin credentials and a CSRF token for redemption", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({csrf_token: "csrf"})))
      .mockResolvedValueOnce(new Response(JSON.stringify({credits_added: 10, balance: 10})));
    vi.stubGlobal("fetch", fetcher);
    const result = await accountRequest("/redeem", redemptionSchema, {code: "fixture"});
    expect(result.balance).toBe(10);
    expect(fetcher.mock.calls[1][1]).toMatchObject({credentials: "same-origin", method: "POST",
      headers: {"X-CSRF-Token": "csrf", "Content-Type": "application/json"}});
  });
  it("returns a safe error instead of echoing private input", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private-input", {status: 401})));
    await expect(accountRequest("/account", accountSchema)).rejects.toThrow("Sign in required");
  });
});

it("reports localized-safe connection and malformed-response errors without echoing data", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("private network detail")));
  await expect(accountRequest("/account", accountSchema)).rejects.toThrow("The response could not be verified.");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({private: "sensitive fixture"}))));
  await expect(accountRequest("/account", accountSchema)).rejects.toThrow("The response could not be verified.");
});
