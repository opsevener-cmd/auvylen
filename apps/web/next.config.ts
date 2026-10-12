import type { NextConfig } from "next";
import path from "node:path";

const config: NextConfig = {
  // Containers use traced output; host development/test startup keeps next start.
  output: process.env.AEVYRA_STANDALONE === "1" ? "standalone" : undefined,
  outputFileTracingRoot: path.join(__dirname, "../.."),
  // Engineering instructions are maintained in the repository's root AGENTS.md.
  agentRules: false,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  async headers() {
    return [{source: "/:path*", headers: [
      {key: "X-Content-Type-Options", value: "nosniff"},
      {key: "Referrer-Policy", value: "strict-origin-when-cross-origin"},
      {key: "X-Frame-Options", value: "DENY"},
    ]}];
  },
};
export default config;
