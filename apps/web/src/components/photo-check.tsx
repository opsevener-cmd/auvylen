"use client";
import Link from "next/link";
import {useCallback, useEffect, useRef, useState} from "react";
import {z} from "zod";
import type {PhotoCheckPhoto, PhotoCheckResult, PhotoCheckRoastLevel, PhotoCheckStatus} from "@auvylen/contracts";
import {AccountError} from "@/lib/account-api";
import {archetypeLabels, bandLabels, criteria, photoCheckConsentVersion, photoCheckRequest, photoCheckResultSchema, photoCheckStatusSchema, shrinkPhoto} from "@/lib/photo-check-api";
import {useI18n} from "./i18n/provider";

const criterionLabels: Record<(typeof criteria)[number], string> = {
  lighting: "Lighting", sharpness: "Sharpness", framing: "Framing",
  expression: "Expression", eye_contact: "Eye contact", background: "Background",
};
// Neutral on purpose: the reason for "cannot_analyse" is never spelled out.
const refusalLabels: Record<string, string> = {
  no_person: "We couldn't find a person in this photo.",
  not_a_photo: "This doesn't look like a photo.",
  cannot_analyse: "We can't analyse this photo.",
};
type Selected = {file: File; url: string};
const box = "rounded-lg border border-black/10 bg-white/70 p-5";

function friendlyDate(value: string, locale: string): string {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(locale, {timeZone: "UTC", weekday: "long", month: "long", day: "numeric"});
}

export function PhotoCheck() {
  const {t, locale} = useI18n();
  const [status, setStatus] = useState<PhotoCheckStatus | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [adult, setAdult] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [selfConfirmed, setSelfConfirmed] = useState(false);
  const [roast, setRoast] = useState<PhotoCheckRoastLevel>("off");
  const [selected, setSelected] = useState<Selected[]>([]);
  const [result, setResult] = useState<PhotoCheckResult | null>(null);

  const [version, setVersion] = useState(0);
  const load = useCallback(() => setVersion(value => value + 1), []);
  useEffect(() => {
    let active = true;
    photoCheckRequest("/status", photoCheckStatusSchema).then(value => {
      if (active) {setStatus(value); setSignedOut(false);}
    }).catch(failure => {
      if (!active) return;
      if (failure instanceof AccountError && failure.status === 401) setSignedOut(true);
      else setError(failure instanceof Error ? failure.message : "Service temporarily unavailable.");
    });
    return () => {active = false;};
  }, [version]);
  // Free local previews when the selection changes or the page closes.
  useEffect(() => () => selected.forEach(item => URL.revokeObjectURL(item.url)), [selected]);

  if (signedOut) return <section className="max-w-xl">
    <Heading/><p className="mt-6">{t("Sign in to check your photos.")}</p>
    <p className="mt-5 flex gap-5"><Link className="button-primary" href="/login">{t("Sign in")}</Link><Link className="underline" href="/register">{t("Create account")}</Link></p>
  </section>;
  if (!status) return <section className="max-w-xl"><Heading/>{error ? <p role="alert" className="mt-6">{t(error)}</p> : <p className="mt-6">{t("Loading…")}</p>}</section>;

  const choose = (files: FileList | null) => {
    setError(""); setResult(null);
    const list = Array.from(files ?? []).filter(file => ["image/jpeg", "image/png"].includes(file.type));
    if (list.length > status.max_photos) setError("You can check up to 5 photos at a time.");
    setSelected(list.slice(0, status.max_photos).map(file => ({file, url: URL.createObjectURL(file)})));
  };
  const check = async () => {
    setBusy(true); setError("");
    try {
      const photos = await Promise.all(selected.map(item => shrinkPhoto(item.file).catch(() => {
        throw new Error("One of these photos could not be opened. Use JPEG or PNG photos.");
      })));
      const checked = await photoCheckRequest("/analyses", photoCheckResultSchema,
        {photos, language: locale, self_and_adult_confirmed: true, roast: status.roast_available ? roast : "off"});
      setResult(checked);
      setSelfConfirmed(false); // Confirmed again for every upload.
      load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Service temporarily unavailable.");
      load();
    } finally {setBusy(false);}
  };
  const free = status.free_checks_now > 0;
  const affordable = free || status.credit_cost === 0 || status.credit_balance >= status.credit_cost;

  return <section className="max-w-3xl">
    <Heading/>
    {!status.available && <p role="status" className={`mt-6 ${box}`}>{t(status.reason === "paused" ? "Photo checks are paused until tomorrow. Please come back then." : "Photo check is not available right now.")}</p>}
    {status.available && status.consent_required && <div className={`mt-6 ${box}`}>
      <h2 className="text-xl">{t("Before you start")}</h2>
      <p className="mt-3 leading-7">{t("Your photos are sent to Google's Gemini API (paid tier) to check the photo itself and give feedback on your appearance. Google doesn't use them to train its models and keeps requests for up to 55 days, only to prevent abuse and meet legal requirements. Auvylen deletes your photos right after your result is ready.")}</p>
      <p className="mt-3 leading-7">{t("Only upload photos of yourself. You must be 18 or older.")}</p>
      <label className="mt-4 flex items-start gap-3"><input className="mt-1.5" type="checkbox" checked={adult} onChange={event => setAdult(event.target.checked)}/>{t("I am 18 or older.")}</label>
      <label className="mt-2 flex items-start gap-3"><input className="mt-1.5" type="checkbox" checked={agreed} onChange={event => setAgreed(event.target.checked)}/>{t("I agree that my photos are sent to Google's Gemini API for this check.")}</label>
      <button className="button-primary mt-5" disabled={!adult || !agreed || busy} onClick={async () => {
        setBusy(true); setError("");
        try {
          await photoCheckRequest("/consent", z.object({accepted: z.boolean()}), {consent_version: photoCheckConsentVersion, adult_confirmed: true, processing_accepted: true});
          load();
        } catch (failure) {setError(failure instanceof Error ? failure.message : "Service temporarily unavailable.");}
        finally {setBusy(false);}
      }}>{t("Accept and continue")}</button>
    </div>}
    {status.available && !status.consent_required && <Quota status={status}/>}
    {status.available && !status.consent_required && !result && <div className={`mt-4 ${box}`}>
      <p>{t("Choose 1 to 5 photos of yourself (JPEG or PNG)")}</p>
      {/* Styled label instead of the browser's untranslated file button. */}
      <label className="button-secondary mt-3 inline-flex cursor-pointer">{t(selected.length ? "Choose different photos" : "Choose photos")}
        <input className="sr-only" type="file" accept="image/jpeg,image/png" multiple aria-label={t("Choose 1 to 5 photos of yourself (JPEG or PNG)")} onChange={event => choose(event.target.files)}/></label>
      {selected.length > 0 && <ul className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-5">{selected.map(item => <li key={item.url}>
        {/* eslint-disable-next-line @next/next/no-img-element -- local preview, never uploaded from here */}
        <img src={item.url} alt="" className="aspect-[4/5] w-full rounded object-cover"/></li>)}</ul>}
      <label className="mt-5 flex items-start gap-3"><input className="mt-1.5" type="checkbox" checked={selfConfirmed} onChange={event => setSelfConfirmed(event.target.checked)}/>{t("This is me and I'm 18+.")}</label>
      {status.roast_available && <fieldset className="mt-4">
        <label className="flex items-start gap-3"><input className="mt-1.5" type="checkbox" checked={roast !== "off"} onChange={event => setRoast(event.target.checked ? "gentle" : "off")}/>{t("Roast me 🔥")}</label>
        {roast !== "off" && <div className="mt-2 flex gap-5 pl-7" role="radiogroup" aria-label={t("Roast level")}>
          {(["gentle", "spicy"] as const).map(level => <label key={level} className="flex items-center gap-2"><input type="radio" name="roast" checked={roast === level} onChange={() => setRoast(level)}/>{t(level === "gentle" ? "Gentle" : "Spicy")}</label>)}
        </div>}
        <p className="mt-1 pl-7 text-sm text-[#63706a]">{t("Jokes about the photo, never about your looks.")}</p>
      </fieldset>}
      <button className="button-primary mt-5" disabled={!selected.length || !selfConfirmed || !affordable || busy} onClick={() => void check()}>
        {busy ? t("Checking your photos…") : !free && status.credit_cost > 0 ? t(status.credit_cost === 1 ? "Check my photos ({cost} Credit)" : "Check my photos ({cost} Credits)", {cost: status.credit_cost}) : t("Check my photos")}
      </button>
    </div>}
    {error && <p role="alert" className="mt-5 text-[#8c513c]">{t(error)}</p>}
    {result && <Results result={result} selected={selected} onAgain={() => {setResult(null); setSelected([]);}}/>}
    <p className="mt-8 text-sm leading-6 text-[#63706a]">{t("Feedback is about your photos and what suits you, and it compares only the photos you upload.")}</p>
  </section>;
}

function Quota({status}: {status: PhotoCheckStatus}) {
  const {t, locale} = useI18n();
  let text: string;
  if (status.credit_cost === 0) text = t("Unlimited checks on your account.");
  else if (status.free_checks_now > 0) text = t(status.free_checks_now === 1 ? "You have {count} free check left." : "You have {count} free checks left.", {count: status.free_checks_now});
  else {
    const next = status.next_free_on ? t("Your next free check: {date}.", {date: friendlyDate(status.next_free_on, locale)}) + " " : "";
    text = next + t(status.credit_cost === 1 ? "Until then, each check costs {cost} Credit. You have {balance}." : "Until then, each check costs {cost} Credits. You have {balance}.", {cost: status.credit_cost, balance: status.credit_balance});
  }
  const short = status.free_checks_now === 0 && status.credit_cost > status.credit_balance;
  return <p className="mt-6 text-sm" role="status">{text} {short && <Link className="underline" href="/account#credits">{t("Add Credits")}</Link>}</p>;
}

function Heading() {
  const {t} = useI18n();
  return <><p className="eyebrow">{t("Photo check")}</p><h1 className="text-3xl font-medium">{t("Which of your photos works best?")}</h1>
    <p className="mt-4 leading-7 text-[#63706a]">{t("Upload up to 5 photos of yourself. We'll rank them, give you quick tips on the photo itself, and tell you what suits you.")}</p></>;
}

function Results({result, selected, onAgain}: {result: PhotoCheckResult; selected: Selected[]; onAgain: () => void}) {
  const {t} = useI18n();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {heading.current?.focus();}, [result]);
  const ordered = [...result.photos].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99) || a.index - b.index);
  const paid = result.credits_charged > 0
    ? t(result.credits_charged === 1 ? "{count} Credit used." : "{count} Credits used.", {count: result.credits_charged})
    : result.funding === "owner" ? "" : t("This one was free.");
  return <div className="mt-6 space-y-4">
    <h2 ref={heading} tabIndex={-1} className="text-2xl outline-none">{t("Your results")}</h2>
    {result.advanced && <p className="inline-block rounded-full border border-[#537462]/40 px-3 py-0.5 text-xs uppercase tracking-[0.14em] text-[#537462]">{t("Advanced analysis")}</p>}
    {paid && <p className="text-sm text-[#63706a]">{paid}</p>}
    {ordered.map(photo => <ResultCard key={photo.index} photo={photo} url={selected[photo.index]?.url} onAgain={onAgain}/>)}
    <button className="button-secondary" onClick={onAgain}>{t("Check other photos")}</button>
  </div>;
}

function List({title, items}: {title: string; items: string[]}) {
  const {t} = useI18n();
  if (!items.length) return null;
  return <div className="mt-3"><h4 className="text-sm font-medium">{t(title)}</h4><ul className="mt-1 list-disc space-y-1 pl-5 text-sm">{items.map(item => <li key={item}>{item}</li>)}</ul></div>;
}

function ResultCard({photo, url, onAgain}: {photo: PhotoCheckPhoto; url?: string; onAgain: () => void}) {
  const {t} = useI18n();
  const [showImpression, setShowImpression] = useState(false);
  return <article className={`${box} flex flex-col gap-4 sm:flex-row`}>
    {/* eslint-disable-next-line @next/next/no-img-element -- local preview only */}
    {url && <img src={url} alt="" className="aspect-[4/5] w-32 shrink-0 rounded object-cover"/>}
    <div className="flex-1">
      {photo.usable && photo.scores ? <>
        <p className="text-sm uppercase tracking-[0.14em] text-[#537462]">{photo.rank === 1 ? t("Best photo") : t("Rank {rank}", {rank: photo.rank ?? "–"})}</p>
        <p className="mt-1 text-3xl">{photo.display_score?.toFixed(1)} <span className="text-base text-[#63706a]">{t("/ 10 photo quality")}</span></p>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">{criteria.map(name => <div key={name} className="flex justify-between gap-2"><dt>{t(criterionLabels[name])}</dt><dd>{photo.scores?.[name]}</dd></div>)}</dl>
        <List title="Photo tips" items={photo.tips}/>
        {/* Stage 2 (appearance, AI impression, roast) only for photos good enough to judge. */}
        {!photo.quality_passed && <div className="mt-5 border-t border-black/10 pt-4">
          <p>{t("Photo quality {score}/10. Retake it with the tips above, then check your look.", {score: photo.display_score?.toFixed(1) ?? "–"})}</p>
          <button className="button-secondary mt-3" onClick={onAgain}>{t("Try another photo")}</button>
        </div>}
        {photo.quality_passed && <p className="mt-4 text-sm text-[#537462]">{t("Quality OK ✓")}</p>}
        {photo.quality_passed && photo.appearance && <section className="mt-5 border-t border-black/10 pt-4" aria-label={t("What suits you")}>
          <h3 className="text-lg">{t("What suits you")}</h3>
          <List title="What's working" items={photo.appearance.strengths}/>
          <List title="What flatters you in photos" items={photo.appearance.flattering}/>
          <List title="Tips" items={photo.appearance.tips}/>
          <div className="mt-4">
            {showImpression
              ? <p className="text-2xl" aria-live="polite">{t(bandLabels[photo.appearance.band])}</p>
              : <button className="button-secondary" onClick={() => setShowImpression(true)}>{t("Show my AI impression")}</button>}
            <p className="mt-1 text-xs text-[#63706a]">{t("AI impression for fun, not an objective rating")}</p>
          </div>
        </section>}
        {photo.quality_passed && photo.roast && (photo.roast.lines.length > 0 || photo.roast.vibe) && <section className="mt-5 border-t border-black/10 pt-4" aria-label={t("Roast 🔥")}>
          <h3 className="text-lg">{t("Roast 🔥")}</h3>
          {photo.roast.lines.map(line => <p key={line} className="mt-2">{line}</p>)}
          {photo.roast.vibe && <p className="mt-2 text-sm">{t("Vibe: {vibe}", {vibe: t(archetypeLabels[photo.roast.vibe])})}</p>}
        </section>}
      </> : <p>{t(refusalLabels[photo.refusal_reason ?? ""] ?? "We can't analyse this photo.")}</p>}
    </div>
  </article>;
}
