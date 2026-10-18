import {describe, expect, it} from "vitest";
import {proxyOrigin} from "./proxy-origin";

const name = "opulent-umbrella-6v5456gw9jx5hrg69";
const host = `${name}-3000.app.github.dev`;
const canonical = `https://${host}`;
const env = {APP_ENV: "staging", CODESPACES: "true", CODESPACE_NAME: name,
  GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: "app.github.dev", CORS_ORIGINS: JSON.stringify([canonical])};
// Exact real ingress captured in the private Codespace (Referer represented by a page URL).
const forwarded = {host: "localhost:3000", origin: "http://localhost:3000", "x-forwarded-host": host, "x-forwarded-proto": "https",
  "sec-fetch-site": "same-origin", referer: `${canonical}/account`};

describe("private Codespaces Origin boundary", () => {
  it("restores the exact rewrite and preserves an unmodified canonical Origin", () => {
    expect(proxyOrigin(new Headers(forwarded), "POST", env)).toEqual({allowed: true, origin: canonical});
    expect(proxyOrigin(new Headers({...forwarded, host, origin: canonical}), "POST", env))
      .toEqual({allowed: true, origin: canonical});
    // An unmodified canonical pair does not need forwarding evidence.
    expect(proxyOrigin(new Headers({host, origin: canonical}), "POST", env))
      .toEqual({allowed: true, origin: canonical});
  });
  it.each(["origin", "host", "x-forwarded-host", "x-forwarded-proto", "referer", "sec-fetch-site"])("rejects missing %s for a rewrite", (key) => {
    const headers = new Headers(forwarded);
    headers.delete(key);
    expect(proxyOrigin(headers, "POST", env)).toEqual({allowed: false});
  });
  it.each([
    "", "null", canonical, "https://attacker.example", "https://another-space-3000.app.github.dev",
    "http://localhost:3001", "https://localhost:3000", "http://127.0.0.1:3000",
    "http://[::1]:3000", "http://localhost:3000/", "http://localhost:3000.evil.test",
    `${canonical}/`, `${canonical}:443`, `${canonical}.evil.test`, `http://${host}`,
    `${canonical}, http://localhost:3000`, `https://user@${host}`,
  ])("rejects unauthorized or noncanonical Origin %s", (origin) => {
    expect(proxyOrigin(new Headers({...forwarded, origin}), "POST", env)).toEqual({allowed: false});
  });
  it.each([
    {host}, {host: "localhost:3001"}, {host: "127.0.0.1:3000"}, {host: "[::1]:3000"},
    {host: `${host}.evil.test`}, {host: "another-space-3000.app.github.dev"},
    {host: `localhost:3000, ${host}`},
    {"x-forwarded-host": "attacker.example"}, {"x-forwarded-host": `${host}, attacker.example`},
    {"sec-fetch-site": "cross-site"}, {"sec-fetch-site": "same-site"}, {"sec-fetch-site": "none"},
    {"x-forwarded-proto": "http"}, {"x-forwarded-proto": "https, http"}, {"x-forwarded-proto": "HTTPS"},
    {"x-forwarded-host": ""}, {"x-forwarded-host": `${host}:443`}, {"x-forwarded-host": canonical},
    {referer: "https://attacker.example/account"}, {referer: "http://localhost:3000/account"},
    {referer: `https://user:password@${host}/account`}, {referer: `${canonical}.evil.test/account`},
    {referer: `${canonical}/account, https://attacker.example/`}, {referer: `${canonical}/#fragment`},
    {referer: `${canonical}\\account`}, {referer: ""},
  ])("rejects forged or contradictory routing/browser evidence %j", (override) => {
    expect(proxyOrigin(new Headers({...forwarded, ...override}), "POST", env)).toEqual({allowed: false});
  });
  it.each([
    {"x-forwarded-host": "attacker.example"}, {"x-forwarded-host": `${host}, ${host}`},
    {"x-forwarded-proto": "http"}, {"x-forwarded-proto": "https, https"},
    {"sec-fetch-site": "cross-site"}, {"sec-fetch-site": "same-origin, same-origin"},
    {referer: "https://attacker.example/"}, {referer: `${canonical}/,${canonical}/`},
    {origin: `${canonical}, ${canonical}`},
  ])("rejects contradictory or ambiguous evidence even with a canonical pair %j", (override) => {
    expect(proxyOrigin(new Headers({...forwarded, host, origin: canonical, ...override}), "POST", env))
      .toEqual({allowed: false});
  });
  it.each(["origin", "host", "x-forwarded-host", "x-forwarded-proto", "sec-fetch-site", "referer"])("rejects duplicate %s on rewritten requests", (key) => {
    const headers = new Headers(forwarded);
    headers.append(key, headers.get(key)!);
    expect(proxyOrigin(headers, "POST", env)).toEqual({allowed: false});
  });
  it.each([
    {APP_ENV: "production"}, {APP_ENV: "development"}, {CODESPACE_NAME: ""},
    {CODESPACE_NAME: "../attacker"}, {CODESPACE_NAME: "-invalid"}, {CODESPACE_NAME: "invalid-"},
    {CODESPACE_NAME: "a".repeat(59)}, {GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: "evil.test"},
    {CORS_ORIGINS: ""}, {CORS_ORIGINS: canonical}, {CORS_ORIGINS: JSON.stringify(canonical)},
    {CORS_ORIGINS: JSON.stringify([canonical, "http://localhost:3000"])},
    {CORS_ORIGINS: JSON.stringify(["https://another-space-3000.app.github.dev"])},
  ])("fails closed for invalid runtime configuration %j", (override) => {
    expect(proxyOrigin(new Headers(forwarded), "POST", {...env, ...override})).toEqual({allowed: false});
  });
  it("does not activate outside Codespaces or invent Origin on read-only requests", () => {
    for (const environment of [{}, {...env, CODESPACES: "false"}]) {
      expect(proxyOrigin(new Headers(forwarded), "POST", environment))
        .toEqual({allowed: true, origin: forwarded.origin});
      expect(proxyOrigin(new Headers(), "POST", environment)).toEqual({allowed: true, origin: null});
    }
    expect(proxyOrigin(new Headers(), "GET", env)).toEqual({allowed: true, origin: null});
  });
});
