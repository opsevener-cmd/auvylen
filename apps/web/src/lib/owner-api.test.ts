import {describe, expect, it} from "vitest";
import {allowedApiPath} from "./api-proxy-policy";
import {accountSchema, sessionSchema} from "./account-api";
import {adminPageSchema, ownerOverviewSchema} from "./owner-api";

describe("Owner boundary contracts", () => {
  it("only forwards explicit admin routes, never arbitrary artifacts or URLs", () => {
    for (const path of ["v1/owner/users", "v1/owner/overview", "v1/owner/audit", "v1/owner/jobs", `v1/owner/users/usr_${"a".repeat(32)}/credits`, `v1/owner/batches/batch_${"b".repeat(32)}/disable`]) expect(allowedApiPath(path)).toBe(true);
    for (const path of ["v1/owner", "v1/owner/initialize", "v1/owner/promote", "v1/owner/../../private", "v1/owner/users/usr_a/password", "v1/owner/checkpoints", "https://attacker.example"]) expect(allowedApiPath(path)).toBe(false);
  });
  it("rejects missing and fabricated roles instead of granting privileges", () => {
    const user = {public_user_id: "usr_test", login_identifier: "owner_god"};
    expect(sessionSchema.safeParse({user, csrf_token: "test"}).success).toBe(false);
    expect(sessionSchema.safeParse({user: {...user, role: "admin"}, csrf_token: "test"}).success).toBe(false);
    expect(accountSchema.parse({user: {...user, role: "owner"}, wallet: {balance: 0, transactions: []}, analyses: []}).wallet.balance).toBe(0);
  });
  it("requires complete measured overview and bounded page metadata", () => {
    expect(ownerOverviewSchema.safeParse({free_product_access: true}).success).toBe(false);
    expect(adminPageSchema.safeParse({items: [], total: -1, page: 1, page_size: 20}).success).toBe(false);
    expect(adminPageSchema.parse({items: [], total: 0, page: 1, page_size: 20}).items).toEqual([]);
  });
});
