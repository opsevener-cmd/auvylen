// Production configuration must make unfinished pages unreachable (404) and keep them out
// of navigation, rather than rendering an "unavailable" page.
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import type {ReactNode} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {LanguageProvider} from "@/components/i18n/provider";
import {SiteShell} from "@/components/site-shell";
import {HomePage} from "@/components/home-page";
import {features} from "@/lib/features";

vi.mock("next/navigation", async original => ({
  ...await original<typeof import("next/navigation")>(), usePathname: () => "/", useRouter: () => ({push() {}, refresh() {}}),
}));

const hidden: [string, () => Promise<{default: (props: never) => unknown}>][] = [
  ["/research/aesthetic", () => import("./research/aesthetic/page")],
  ["/research/native-preview", () => import("./research/native-preview/page")],
  ["/analyze", () => import("./analyze/page")],
  ["/history", () => import("./history/page")],
  ["/checkout/[orderId]", () => import("./checkout/[orderId]/page")],
  ["/result/[analysisId]", () => import("./result/[analysisId]/page")],
];
const props = {params: Promise.resolve({orderId: "av_00", analysisId: "00"}), searchParams: Promise.resolve({})} as never;
const hiddenHrefs = ["/research/aesthetic", "/research/native-preview", "/analyze", "/history", "/checkout", "/result", "/redeem"];

function shell(): string {
  const enabled = features();
  return html(<SiteShell pilot={false} features={enabled}><HomePage syntheticAvailable={enabled.syntheticAnalysis}/></SiteShell>);
}
function html(node: ReactNode): string {
  return renderToStaticMarkup(<LanguageProvider initialLocale="en">{node}</LanguageProvider>);
}

beforeEach(() => {
  vi.stubEnv("APP_ENV", "production");
  vi.stubEnv("API_URL", "http://api.invalid:8000");
  vi.stubEnv("PREVIEW_FEATURES_ENABLED", "");
});
afterEach(() => vi.unstubAllEnvs());

describe("production hides unfinished features", () => {
  it.each(hidden)("%s answers 404", async (_route, load) => {
    const page = (await load()).default;
    let thrown: unknown;
    try {await page(props);} catch (error) {thrown = error;}
    expect((thrown as {digest?: string} | undefined)?.digest).toBe("NEXT_HTTP_ERROR_FALLBACK;404");
  });
  it("/redeem redirects to the Account page's Credits section", async () => {
    const page = (await import("./redeem/page")).default;
    let thrown: unknown;
    try {page();} catch (error) {thrown = error;}
    expect(String((thrown as {digest?: string}).digest)).toContain(";/account#credits;");
  });
  it("navigation, footer and home page link only to available areas", () => {
    const markup = shell();
    const hrefs = [...markup.matchAll(/href="([^"]*)"/g)].map(match => match[1]);
    for (const href of hrefs) expect(hiddenHrefs.some(prefix => href.startsWith(prefix)), href).toBe(false);
    expect(hrefs).toEqual(expect.arrayContaining(["/research/preferences", "/research/studies", "/research", "/account"]));
    expect(markup).not.toContain("unavailable in production");
  });
  it("development still shows the preview features", () => {
    vi.stubEnv("APP_ENV", "development");
    const markup = shell();
    for (const href of ["/research/aesthetic", "/history", "/analyze"]) expect(markup).toContain(`href="${href}"`);
  });
});
