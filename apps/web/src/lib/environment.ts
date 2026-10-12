export function getApiUrl(): string {
  const environment = process.env.APP_ENV ?? "development";
  if (!["development", "staging", "production"].includes(environment)) {
    throw new Error("Invalid APP_ENV");
  }
  const value = process.env.API_URL;
  if (!value && environment !== "development") throw new Error("API_URL is required");
  const url = new URL(value ?? "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("Invalid API_URL");
  }
  return url.origin;
}

export function requireCommercialAccess(): void {
  if (process.env.APP_ENV === "production" || isPublicPilot() || process.env.MOCK_CHECKOUT_ENABLED === "false") throw new Error("Commercial checkout is disabled");
}

export function isPublicPilot(): boolean {
  if (process.env.PUBLIC_PILOT !== "true") return false;
  if (process.env.APP_ENV !== "staging") throw new Error("PUBLIC_PILOT requires staging");
  const value = process.env.PUBLIC_BASE_URL;
  let url: URL;
  try {url = new URL(value ?? "");} catch {throw new Error("Invalid PUBLIC_BASE_URL");}
  if (url.protocol !== "https:" || url.username || url.password || url.origin !== value ||
      url.hostname === "localhost" || !/^[a-z0-9][a-z0-9.-]*[a-z0-9]$/.test(url.hostname) ||
      !url.hostname.includes(".") || url.hostname.includes("..") || /^\d+\.\d+\.\d+\.\d+$/.test(url.hostname)) {
    throw new Error("Invalid PUBLIC_BASE_URL");
  }
  return true;
}
