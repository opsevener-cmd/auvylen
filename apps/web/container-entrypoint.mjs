// Fail before accepting traffic; never print configuration values.
const environment = process.env.APP_ENV;
if (!["development", "staging", "production"].includes(environment)) {
  throw new Error("APP_ENV must explicitly select development, staging or production");
}
try {
  const url = new URL(process.env.API_URL);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error();
} catch {
  throw new Error("A valid server-side API_URL is required");
}
if (process.env.PUBLIC_PILOT === "true") {
  try {
    const value = process.env.PUBLIC_BASE_URL;
    const url = new URL(value);
    if (environment !== "staging" || url.protocol !== "https:" || url.origin !== value ||
        url.username || url.password || url.hostname === "localhost" ||
        !/^[a-z0-9][a-z0-9.-]*[a-z0-9]$/.test(url.hostname) ||
        !url.hostname.includes(".") || url.hostname.includes("..") || /^\d+\.\d+\.\d+\.\d+$/.test(url.hostname)) throw new Error();
  } catch {throw new Error("Pilot requires staging and a canonical public HTTPS origin");}
}
await import("./apps/web/server.js");
