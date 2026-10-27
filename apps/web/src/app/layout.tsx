import type {Metadata} from "next";
import {cookies, headers} from "next/headers";
import {isPublicPilot} from "@/lib/environment";
import {chooseLocale, localeCookie} from "@/lib/i18n/catalog";
import {LanguageProvider} from "@/components/i18n/provider";
import {SiteShell} from "@/components/site-shell";
import localFont from "next/font/local";
import "./globals.css";
// Self-hosted OFL display serif (Latin subset, see fonts/OFL.txt). Chinese falls back to system serifs.
const display = localFont({
  src: [{path: "./fonts/cormorant-garamond-latin-wght.woff2", weight: "300 700", style: "normal"}],
  variable: "--font-display", display: "swap", adjustFontFallback: "Times New Roman",
  fallback: ["Georgia", "Times New Roman", "serif"],
});
// Chinese uses upright accents; load the italic subset only where it is actually used.
const displayItalic = localFont({
  src: [{path: "./fonts/cormorant-garamond-latin-italic-500.woff2", weight: "500", style: "italic"}],
  variable: "--font-display-italic", display: "swap", preload: false,
  adjustFontFallback: "Times New Roman", fallback: ["Georgia", "Times New Roman", "serif"],
});
export const metadata: Metadata = {
  title: {default: "Auvylen · Personal aesthetic research", template: "%s · Auvylen"},
  description: "Auvylen — private personal preference research. 私密的个人审美偏好研究。",
  robots: {index: false, follow: false},
};
export default async function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  const [saved, request] = await Promise.all([cookies(), headers()]);
  const locale = chooseLocale(saved.get(localeCookie)?.value, request.get("accept-language") ?? "");
  return <html lang={locale} className={`${display.variable} ${displayItalic.variable}`}><body><LanguageProvider initialLocale={locale}><SiteShell pilot={isPublicPilot()}>{children}</SiteShell></LanguageProvider></body></html>;
}
export const dynamic = "force-dynamic";
