import {NextRequest} from "next/server";
import {getApiUrl} from "@/lib/environment";

// Development same-origin proxy. Production Caddy routes /api directly to FastAPI.
// Only the account/credit surface is forwarded; no arbitrary URLs or operator routes.
async function proxy(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  const joined = path.join("/");
  if (!/^v1\/(auth\/(csrf|register|login|logout|me)|account|redeem|credit-products|credit-analyses(?:\/[0-9a-f-]+(?:\/result)?)?)$/.test(joined)) {
    return Response.json({detail: "Not found"}, {status: 404});
  }
  const headers = new Headers();
  for (const name of ["cookie", "content-type", "origin", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const response = await fetch(new URL(`/api/${joined}`, getApiUrl()), {
      method: request.method, headers, cache: "no-store",
      body: request.method === "POST" ? await request.text() : undefined,
      signal: AbortSignal.timeout(15000), redirect: "manual",
    });
    const outgoing = new Headers({"Content-Type": "application/json", "Cache-Control": "no-store"});
    for (const cookie of response.headers.getSetCookie()) outgoing.append("Set-Cookie", cookie);
    return new Response(await response.text(), {status: response.status, headers: outgoing});
  } catch {
    return Response.json({detail: "Service temporarily unavailable"}, {status: 503});
  }
}

export const GET = proxy;
export const POST = proxy;
