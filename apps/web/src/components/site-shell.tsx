"use client";
import Link from "next/link";
import {usePathname} from "next/navigation";
import {useState} from "react";
import {useI18n} from "./i18n/provider";
export function SiteShell({children, pilot}: {children: React.ReactNode; pilot: boolean}) {
  const {locale, setLocale, t} = useI18n();
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const links = [["/", "Home"], ["/research/aesthetic", "Aesthetic analysis"], ["/research/preferences", "Personal research"], ["/research", "Research workspace"], ["/account", "Account"]];
  return <>
    <a href="#main" className="skip-link">{t("Skip to content")}</a>
    <header className="site-header"><div className="header-inner">
      <Link href="/" className="wordmark" aria-label="Auvylen"><span className="brand-mark" aria-hidden="true">a</span>Auvylen<span className="brand-dot">.</span></Link>
      <button type="button" className="menu-toggle" aria-expanded={open} aria-controls="main-nav" onClick={() => setOpen(!open)}>{t(open ? "Close menu" : "Menu")}</button>
      <nav id="main-nav" aria-label={t("Main navigation")} className={open ? "main-nav is-open" : "main-nav"}>{links.map(([href, label]) => <Link key={href} href={href} onClick={() => setOpen(false)} aria-current={pathname === href ? "page" : undefined}>{t(label)}</Link>)}</nav>
      <div className="language-switch" role="group" aria-label={t("Language")}><button lang="zh-CN" aria-pressed={locale === "zh-CN"} onClick={() => setLocale("zh-CN")}>中文</button><span aria-hidden="true">/</span><button lang="en" aria-pressed={locale === "en"} onClick={() => setLocale("en")}>English</button></div>
    </div></header>
    <div className="site-content">{pilot && <aside className="pilot-note">{t("Private pilot · Synthetic analysis is available for development testing only.")}</aside>}
      <main id="main" tabIndex={-1}>{children}</main>
      <footer className="site-footer"><div><Link href="/" className="wordmark">Auvylen.</Link><p>{t("Your perspective. Your private space.")}</p></div><div><Link href="/status">{t("System status")}</Link><Link href="/history">{t("Analysis history")}</Link><Link href="/#guide">{t("Getting started")}</Link></div><p>{t("Personal preferences, never objective beauty.")}</p></footer>
    </div>
  </>;
}
