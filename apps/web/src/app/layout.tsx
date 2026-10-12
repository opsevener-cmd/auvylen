import type {Metadata} from "next";
import Link from "next/link";
import {isPublicPilot} from "@/lib/environment";
import "./globals.css";

export const metadata: Metadata = {
  title: {default: "Auvylen", template: "%s · Auvylen"},
  description: "Auvylen — development commercial flow with synthetic results.",
  robots: {index: false, follow: false},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  const pilot = isPublicPilot();
  return <html lang="en"><body className="min-h-screen antialiased">
    <a href="#main" className="sr-only focus:not-sr-only focus:p-4">Skip to content</a>
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 sm:px-10">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-black/10 py-7 sm:py-9">
        <Link href="/" className="text-xl font-semibold tracking-tight">Auvylen<span className="text-[#537462]">.</span></Link>
        <nav aria-label="Main navigation" className="flex flex-wrap gap-4 text-sm text-[#52605a]">
          <Link href="/" className="hover:text-black">Home</Link>
          <Link href="/status" className="hover:text-black">System status</Link>
          <Link href="/account" className="hover:text-black">Account</Link>
          <Link href="/research" className="hover:text-black">Research</Link>
        </nav>
      </header>
      {pilot && <aside className="mt-6 rounded-md border border-black/10 p-4 text-sm" aria-label="Pilot notice"><strong>Auvylen Pilot</strong><p>Synthetic analysis is currently enabled for testing.</p></aside>}
      <main id="main" className="flex-1 py-16 sm:py-24">{children}</main>
      <footer className="flex flex-wrap justify-between gap-3 border-t border-black/10 py-6 text-xs text-[#68736d]">
        <span>Auvylen · Pilot foundation</span><span>Synthetic analysis only</span>
      </footer>
    </div>
  </body></html>;
}
export const dynamic = "force-dynamic";
