import {NextRequest} from "next/server";
import {allowedApiPath} from "@/lib/api-proxy-policy";
import {getApiUrl} from "@/lib/environment";
import {proxyOrigin} from "@/lib/proxy-origin";

// Development same-origin proxy. Production Caddy routes /api directly to FastAPI.
// Explicit account and research routes only; no arbitrary URLs or operator routes.
async function proxy(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  const joined = path.join("/");
  if (!allowedApiPath(joined)) {
    return Response.json({detail: "Not found"}, {status: 404});
  }
  const origin = proxyOrigin(request.headers, request.method, process.env);
  if (!origin.allowed) {
    return Response.json({detail: "Request origin rejected"}, {
      status: 403, headers: {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    });
  }
  const headers = new Headers();
  for (const name of ["cookie", "content-type", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (origin.origin !== null) headers.set("origin", origin.origin);
  try {
    let body: Uint8Array | undefined;
    if (request.method === "POST") {
      const limit = joined.startsWith("v1/research/preferences/") ? 6 * 1024 * 1024 : 1024 * 1024;
      const chunks: Uint8Array[] = [];
      let size = 0;
      const reader = request.body?.getReader();
      if (reader) {
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > limit) {
            await reader.cancel();
            return Response.json({detail: "Request too large"}, {status: 413});
          }
          chunks.push(value);
        }
      }
      body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {body.set(chunk, offset); offset += chunk.byteLength;}
    }
    const response = await fetch(new URL(`/api/${joined}${request.nextUrl.search}`, getApiUrl()), {
      method: request.method, headers, cache: "no-store",
      body: body ? Buffer.from(body) : undefined,
      signal: AbortSignal.timeout(15000), redirect: "manual",
    });
    const outgoing = new Headers({"Content-Type": response.headers.get("content-type") ?? "application/json", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"});
    for (const cookie of response.headers.getSetCookie()) outgoing.append("Set-Cookie", cookie);
    return new Response(response.body, {status: response.status, headers: outgoing});
  } catch {
    return Response.json({detail: "Service temporarily unavailable"}, {status: 503});
  }
}

export const GET = proxy;
export const POST = proxy;
