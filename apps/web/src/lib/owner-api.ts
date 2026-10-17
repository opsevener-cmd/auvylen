import {z} from "zod";
import type {AdminPage, AdminResult, AdminValue, OwnerOverview} from "@auvylen/contracts";

const value: z.ZodType<AdminValue> = z.json();
const row = z.record(z.string(), value);
export const adminPageSchema: z.ZodType<AdminPage> = z.object({items: z.array(row), total: z.number().int().nonnegative(), page: z.number().int().positive(), page_size: z.number().int().positive()});
export const adminResultSchema: z.ZodType<AdminResult> = z.object({data: row});
export const ownerOverviewSchema: z.ZodType<OwnerOverview> = z.object({
  counts: z.record(z.string(), z.number()), jobs: z.record(z.string(), z.number()),
  credits: z.record(z.string(), z.number()), health: row, providers: z.array(row), extractors: z.array(row), usage: z.array(row),
  quotas: z.record(z.string(), z.number()), environment: z.string(), research_enabled: z.boolean(), free_product_access: z.literal(true),
});

// Presentation copy lives outside authorization/business logic; ready for locale catalogs.
export const ownerText = {
  title: "Owner workspace", subtitle: "Administration, service visibility and financial integrity.",
  badge: "SUPER ADMINISTRATOR", entitlement: "Permanent product access · No usage Credits charged",
  tabs: ["Overview", "Users & Credits", "Redemption", "Research operations", "Audit trail"],
  denied: "Owner access required. Sign in with your provisioned Owner account.",
  fresh: "Sensitive changes require a sign-in within the last 10 minutes. Confirm your password here to renew it.",
  reason: "Audit reason (no passwords, tokens or personal image details)",
  secretNotice: "These codes are shown only once. Download them to protected storage now. They cannot be retrieved later. If delivery is uncertain, disable this batch and create a new one.",
  mutationErrors: {
    403: "Owner access, CSRF verification or a fresh sign-in is required. Confirm your password and retry.",
    409: "This request was already used or conflicts. Review the current records before creating a new request. Codes cannot be exported twice.",
  },
};
