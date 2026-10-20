import type {Metadata} from "next";
import {cookies, headers} from "next/headers";
import {isPublicPilot} from "@/lib/environment";
import {chooseLocale, localeCookie} from "@/lib/i18n/catalog";
import {LanguageProvider} from "@/components/i18n/provider";
import {SiteShell} from "@/components/site-shell";
import "./globals.css";
export const metadata: Metadata = {
  title: {default: "Auvylen · Personal aesthetic research", template: "%s · Auvylen"},
  description: "Auvylen — private personal preference research. 私密的个人审美偏好研究。",
  robots: {index: false, follow: false},
};
export default async function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  const [saved, request] = await Promise.all([cookies(), headers()]);
  const locale = chooseLocale(saved.get(localeCookie)?.value, request.get("accept-language") ?? "");
  return <html lang={locale}><body><LanguageProvider initialLocale={locale}><SiteShell pilot={isPublicPilot()}>{children}</SiteShell></LanguageProvider></body></html>;
}
export const dynamic = "force-dynamic";
