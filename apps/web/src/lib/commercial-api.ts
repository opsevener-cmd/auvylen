import {z} from "zod";
import {getApiUrl, requireCommercialAccess} from "./environment";
import {logFailure} from "./logging";
export {productSchema, orderSchema, paymentSchema, analysisSchema, resultSchema} from "./api-schemas";

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 404 ? "This item is not available." : "The request could not be completed. Check the API and local database.");
  }
}

export function unavailable(error: unknown): null {
  logFailure("commercial_api_unavailable", error, "WARNING");
  return null;
}

export async function apiRequest<T>(path: string, schema: z.ZodType<T>, body?: object, fetcher: typeof fetch = fetch): Promise<T> {
  requireCommercialAccess();
  const response = await fetcher(new URL(`/api/v1${path}`, getApiUrl()), {
    method: body === undefined ? "GET" : "POST", cache: "no-store",
    headers: body === undefined ? undefined : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new ApiError(response.status);
  return schema.parse(await response.json());
}

export function formatMoney(amount: number, currency: string): string {
  return new Intl.NumberFormat("en", {style: "currency", currency, currencyDisplay: "narrowSymbol"}).format(amount / 100);
}
