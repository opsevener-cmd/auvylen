"use client";
import {useI18n} from "./i18n/provider";

type Variant = "hero" | "onboarding" | "analysis";
type MobileSource = {media: string; srcSet: string; avifSrcSet?: string; sizes: string; width: number; height: number};
type Portrait = {alt: string; caption: string; src: string; srcSet: string; avifSrcSet?: string; sizes: string; width: number; height: number; mobile?: MobileSource};
const adultCaption = "Generated adult portraits · Decorative, not research data";
// Public, generated artwork only. Never pass an upload or dataset URL into this component.
const portraits: Record<Variant, Portrait> = {
  hero: {
    alt: "Four fictional adults in a sunlit stone gallery, generated for Auvylen",
    caption: adultCaption,
    src: "/images/editorial/hero-1440.webp",
    srcSet: "/images/editorial/hero-960.webp 960w, /images/editorial/hero-1440.webp 1440w",
    sizes: "(max-width: 1100px) 100vw, (max-width: 1360px) 52vw, calc(27.084vw + 337px)",
    width: 1440, height: 960,
    mobile: {media: "(max-width: 1100px)", srcSet: "/images/editorial/hero-mobile-480.webp 480w, /images/editorial/hero-mobile-768.webp 768w, /images/editorial/hero-mobile-1056.webp 1056w", sizes: "100vw", width: 768, height: 669},
  },
  onboarding: {
    alt: "Generated architectural prints, a brass loupe and a pencil on stone",
    caption: "Generated still life · Decorative, not research data",
    src: "/images/editorial/study-still-life-960.webp",
    srcSet: "/images/editorial/study-still-life-480.webp 480w, /images/editorial/study-still-life-960.webp 960w",
    avifSrcSet: "/images/editorial/study-still-life-480.avif 480w, /images/editorial/study-still-life-960.avif 960w",
    sizes: "(max-width: 860px) 100vw, (max-width: 1360px) 38vw, 480px",
    width: 960, height: 720,
  },
  analysis: {
    alt: "Two fictional adults on a plaster bench in directional studio light",
    caption: adultCaption,
    src: "/images/editorial/analysis-pair-960.webp",
    srcSet: "/images/editorial/analysis-pair-480.webp 480w, /images/editorial/analysis-pair-960.webp 960w",
    avifSrcSet: "/images/editorial/analysis-pair-480.avif 480w, /images/editorial/analysis-pair-960.avif 960w",
    sizes: "(max-width: 860px) 100vw, (max-width: 1360px) 44vw, 590px",
    width: 960, height: 1200,
    mobile: {media: "(max-width: 860px)", srcSet: "/images/editorial/analysis-pair-mobile-480.webp 480w, /images/editorial/analysis-pair-mobile-960.webp 960w", avifSrcSet: "/images/editorial/analysis-pair-mobile-480.avif 480w, /images/editorial/analysis-pair-mobile-960.avif 960w", sizes: "100vw", width: 960, height: 720},
  },
};
export function EditorialPortrait({variant}: {variant: Variant}) {
  const {t} = useI18n();
  const portrait = portraits[variant];
  const mobile = portrait.mobile;
  return <figure className={`editorial-portrait editorial-portrait--${variant}`}>
    <picture>
      {mobile?.avifSrcSet && <source type="image/avif" media={mobile.media} srcSet={mobile.avifSrcSet} sizes={mobile.sizes} width={mobile.width} height={mobile.height}/>}
      {mobile && <source type="image/webp" media={mobile.media} srcSet={mobile.srcSet} sizes={mobile.sizes} width={mobile.width} height={mobile.height}/>}
      {portrait.avifSrcSet && <source type="image/avif" srcSet={portrait.avifSrcSet} sizes={portrait.sizes}/>}
      {/* Art-directed, pre-encoded local variants avoid runtime image encoding. */}
      <img src={portrait.src} srcSet={portrait.srcSet} sizes={portrait.sizes} width={portrait.width} height={portrait.height} alt={t(portrait.alt)} loading={variant === "onboarding" ? "lazy" : "eager"} fetchPriority={variant === "hero" ? "high" : "auto"} decoding="async" />
    </picture>
    <figcaption>{t(portrait.caption)}</figcaption>
  </figure>;
}
