"use client";
import Link from "next/link";
import {EditorialPortrait} from "./editorial-portrait";
import {useI18n} from "./i18n/provider";
const steps = [
  ["Sign in to your space", "Create an account or sign in. Research access must be enabled by the operator; Owner access is included.", "/register"],
  ["Create a private project", "Choose a name for your research question. Projects keep related datasets together.", "/research/preferences"],
  ["Create your first dataset", "Record the source, license and retention period. Choose one rating scale you can use consistently.", "/research/preferences"],
  ["Upload authorized adult photographs", "Use JPEG or PNG files you have permission to study. Confirm that every subject is an adult aged 18 or older.", "/research/preferences"],
  ["Identify the same person", "Use the same group identifier for every photograph of one person, so training and validation stay separate.", "/research/preferences"],
  ["Rate what you prefer", "Use your own consistent scale. Save each rating, skip uncertain images and revisit any score.", "/research/preferences"],
  ["Compare two photographs", "Optionally choose which photograph you prefer. Pairwise choices are saved separately and do not currently train the rating model.", "/research/preferences"],
  ["Train a personal model", "Start with at least 8 rated images across 5 independent groups. Each training run creates a version you can review.", "/research/preferences"],
  ["Explore a new prediction", "Upload a new photograph, select a ready model and request a personal rating. Treat the result as an estimate of your labels.", "/research/preferences"],
];
const features = [
  ["01", "A space for your perspective", "Private projects and datasets keep your research organized and separate from other accounts."],
  ["02", "Look, rate, compare", "Study photographs at a comfortable size, record numerical ratings and compare pairs side by side."],
  ["03", "Learn from your choices", "Train a versioned model using lightweight color and texture features or MobileNetV3-Small representations."],
  ["04", "Explore with care", "Predict personal ratings for new images, review validation results and keep the limitations in view."],
];
export function HomePage({syntheticAvailable}: {syntheticAvailable: boolean}) {
  const {t} = useI18n();
  return <div className="home-page">
    <section className="hero hero--editorial"><div className="hero-copy"><p className="eyebrow">{t("A private study of personal aesthetics")}</p><h1>{t("Understand Beauty.")}<br/><em>{t("Discover Your Aesthetic.")}</em></h1><p className="hero-intro">{t("Auvylen turns your thoughtful observations into a personal preference model. A quiet, private place to look closer, learn from your choices and explore your own perspective.")}</p><div className="hero-actions"><Link href="/research/preferences" className="button-primary">{t("Explore personal research")} <Arrow/></Link><a className="button-secondary" href="#guide">{t("How it works")} <Arrow down/></a></div><div className="hero-trust"><span>{t("Private by design")}</span><span>{t("Your labels, your perspective")}</span><span>{t("No research Credit charge")}</span></div></div>
      <EditorialPortrait variant="hero"/>
    </section>
    <section className="purpose-strip"><p className="eyebrow">{t("Two experiences. Clearly explained.")}</p><div><span className="chapter-numeral" aria-hidden="true">I</span><h2>{t("Personal research learns from real images.")}</h2><p>{t("Your model learns relationships between image features and your own ratings. It estimates personal preferences, not objective beauty or a person's worth.")}</p></div><div><span className="chapter-numeral" aria-hidden="true">II</span><h2>{t("Synthetic analysis is a development demo.")}</h2><p>{t("The separate /analyze experience produces synthetic test output. It does not inspect a photograph or provide a facial attractiveness assessment.")}</p>{syntheticAvailable ? <Link href="/analyze">{t("View development demo")} <Arrow/></Link> : <p>{t("Synthetic analysis is unavailable in production.")}</p>}</div></section>
    <section className="home-section" id="features"><div className="section-heading"><p className="eyebrow">{t("Designed for thoughtful exploration")}</p><h2>{t("From observation to understanding.")}</h2></div><div className="feature-grid">{features.map(([number, title, description]) => <article className="feature-card" key={number}><span className="feature-number">{number}</span><h3>{t(title)}</h3><p>{t(description)}</p></article>)}</div></section>
    <section className="home-section guide-section" id="guide"><div className="section-heading"><p className="eyebrow">{t("Your first research journey")}</p><h2>{t("Start small. Learn as you go.")}</h2><p>{t("You do not need a machine-learning background. Follow these nine steps; your saved datasets and annotations let you return whenever you like.")}</p><EditorialPortrait variant="onboarding"/></div><ol className="guide-list">{steps.map(([title, explanation, href], i) => <li key={title}><span className="step-number">{String(i + 1).padStart(2, "0")}</span><div><h3>{t(title)}</h3><p>{t(explanation)}</p></div><Link href={href} aria-label={t("Open step: {step}", {step: t(title)})}><Arrow/></Link></li>)}</ol></section>
    <section className="privacy-banner"><div className="privacy-copy"><p className="eyebrow">{t("Care is part of the process")}</p><h2>{t("Your research belongs to you.")}</h2><p>{t("Private photographs require sign-in and ownership checks. Choose a retention period of 1–90 days. Archiving pauses changes; deleting blocks access immediately and schedules stored files for removal. Backup retention is managed separately.")}</p></div><Link href="/research/preferences" className="button-primary">{t("Begin your research")} <Arrow/></Link></section>
  </div>;
}

function Arrow({down = false}: {down?: boolean}) {
  return <svg aria-hidden="true" focusable="false" viewBox="0 0 16 16" width="14" height="14" className="inline-block align-middle" fill="none" stroke="currentColor" strokeWidth="1.25"><path d={down ? "M8 2v12m-5-5 5 5 5-5" : "M3 13 13 3M3 3h10v10"}/></svg>;
}
