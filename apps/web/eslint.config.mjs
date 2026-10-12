import {defineConfig, globalIgnores} from "eslint/config";
import {fixupConfigRules} from "@eslint/compat";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  // Preserve plugin rules while adapting their legacy APIs to current ESLint.
  ...fixupConfigRules([...nextVitals, ...nextTypescript]),
  globalIgnores([".next/**", "next-env.d.ts"]),
]);
