import {afterEach, describe, expect, it, vi} from "vitest";
import {accountRequest, accountSchema, redemptionSchema} from "./account-api";

afterEach(() => vi.unstubAllGlobals());

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
