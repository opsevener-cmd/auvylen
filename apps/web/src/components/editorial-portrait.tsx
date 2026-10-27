"use client";
import {useI18n} from "./i18n/provider";

// Public, generated artwork only. Never pass an upload or dataset URL into this component.
const portraits = {
  hero: {
    alt: "Four fictional adults in a sunlit stone gallery, generated for Auvylen",
    src: "/images/editorial/hero-1440.webp",
    srcSet: "/images/editorial/hero-960.webp 960w, /images/editorial/hero-1440.webp 1440w",
    sizes: "(max-width: 1280px) calc(100vw - 80px), 1200px",
    width: 1440,
    height: 960,
  },
  onboarding: {
    alt: "Three fictional adults sharing a quiet moment around a studio table",
    src: "/images/editorial/onboarding-960.webp",
    srcSet: "/images/editorial/onboarding-480.webp 480w, /images/editorial/onboarding-960.webp 960w",
    sizes: "(max-width: 720px) calc(100vw - 40px), 460px",
    width: 960,
    height: 640,
  },
  analysis: {
    alt: "Two fictional adults in a softly lit studio, generated as decorative artwork",
    src: "/images/editorial/analysis-960.webp",
    srcSet: "/images/editorial/analysis-480.webp 480w, /images/editorial/analysis-960.webp 960w",
    sizes: "(max-width: 720px) calc(100vw - 40px), (max-width: 1100px) calc(100vw - 52px), (max-width: 1280px) 45vw, 575px",
    width: 960,
    height: 640,
  },
};
export function EditorialPortrait({variant}: {variant: keyof typeof portraits}) {
  const {t} = useI18n();
  const portrait = portraits[variant];
  return <figure className={`editorial-portrait editorial-portrait--${variant}`}>
    <picture>
      {variant === "hero" && <source media="(max-width: 1100px)" srcSet="/images/editorial/hero-mobile-480.webp 480w, /images/editorial/hero-mobile-768.webp 768w, /images/editorial/hero-mobile-1056.webp 1056w" sizes="calc(100vw - 40px)" width={768} height={669} />}
      {/* Static art-directed variants avoid runtime image encoding on the small CPU host. */}
      <img {...portrait} alt={t(portrait.alt)} loading={variant === "onboarding" ? "lazy" : "eager"} fetchPriority={variant === "hero" ? "high" : "auto"} decoding="async" />
    </picture>
    <figcaption>{t("Generated adult portraits · Decorative, not research data")}</figcaption>
  </figure>;
}
