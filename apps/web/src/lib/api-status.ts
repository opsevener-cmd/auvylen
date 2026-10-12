import type {ReadinessResponse} from "@auvylen/contracts";
import {z} from "zod";

const dependency = z.enum(["ok", "unavailable"]);
const readinessSchema: z.ZodType<ReadinessResponse> = z.object({
  status: z.enum(["ready", "not_ready"]),
  dependencies: z.object({database: dependency, redis: dependency}),
});

export type ApiStatus =
  | { reachable: true; readiness: ReadinessResponse }
  | { reachable: false; readiness: null };

export async function getApiStatus(
  apiUrl: string,
  fetcher: typeof fetch = fetch,
): Promise<ApiStatus> {
  try {
    const response = await fetcher(new URL("/ready", apiUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(7000),
    });
    if (response.status !== 200 && response.status !== 503) {
      return {reachable: false, readiness: null};
    }
    const readiness = readinessSchema.parse(await response.json());
    const healthy = readiness.dependencies.database === "ok" && readiness.dependencies.redis === "ok";
    if ((readiness.status === "ready") !== healthy || (response.status === 200) !== healthy) {
      return {reachable: false, readiness: null};
    }
    return {reachable: true, readiness};
  } catch {
    // Connection, timeout and invalid-response failures are visible in the status UI.
    return {reachable: false, readiness: null};
  }
}
