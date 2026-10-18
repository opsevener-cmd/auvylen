type ProxyEnvironment = Readonly<Record<string, string | undefined>>;

type OriginDecision = {allowed: true; origin: string | null} | {allowed: false};

/** Restore only the documented Codespaces port-3000 rewrite, never arbitrary Origins.
 * Host/Fetch Metadata/Referer are consistency checks, not authentication. FastAPI
 * still validates the exact Origin, session-bound CSRF token and account session.
 */
export function proxyOrigin(headers: Headers, method: string, env: ProxyEnvironment): OriginDecision {
  const incoming = headers.get("origin");
  if (env.CODESPACES !== "true" || method !== "POST") return {allowed: true, origin: incoming};

  const name = env.CODESPACE_NAME ?? "";
  // The name plus "-3000" must be a single valid DNS label (at most 63 bytes).
  if (env.APP_ENV !== "staging" || !/^[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?$/.test(name) ||
      (env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN ?? "app.github.dev") !== "app.github.dev") {
    return {allowed: false};
  }
  const host = `${name}-3000.app.github.dev`;
  const canonical = `https://${host}`;
  // Cross-check the server configuration used by FastAPI. Never derive trust
  // from a caller's Host, X-Forwarded-Host, URL, or client-supplied override.
  let configured: unknown;
  try {configured = JSON.parse(env.CORS_ORIGINS ?? "");} catch {return {allowed: false};}
  if (!Array.isArray(configured) || configured.length !== 1 || configured[0] !== canonical ||
      headers.get("host") !== host ||
      (headers.has("x-forwarded-host") && headers.get("x-forwarded-host") !== host)) {
    return {allowed: false};
  }
  const site = headers.get("sec-fetch-site");
  if (site !== null && site !== "same-origin") return {allowed: false};
  if (incoming === canonical) return {allowed: true, origin: incoming};
  // Do not broaden this to other localhost names, schemes, ports, or missing Origin.
  if (incoming !== "http://localhost:3000" || site !== "same-origin") return {allowed: false};
  try {
    const referer = new URL(headers.get("referer") ?? "");
    if (referer.origin !== canonical || referer.username || referer.password) return {allowed: false};
  } catch {return {allowed: false};}
  return {allowed: true, origin: canonical};
}
