"use client";
import Link from "next/link";
import {useCallback, useEffect, useRef, useState} from "react";
import {z} from "zod";
import type {PhotoCheckPhoto, PhotoCheckResult, PhotoCheckStatus} from "@auvylen/contracts";
import {AccountError} from "@/lib/account-api";
import {criteria, photoCheckConsentVersion, photoCheckRequest, photoCheckResultSchema, photoCheckStatusSchema, shrinkPhoto} from "@/lib/photo-check-api";
import {useI18n} from "./i18n/provider";

const criterionLabels: Record<(typeof criteria)[number], string> = {
  lighting: "Lighting", sharpness: "Sharpness", framing: "Framing",
  expression: "Expression", eye_contact: "Eye contact", background: "Background",
};
const refusalLabels: Record<string, string> = {
  no_person: "No person is clearly visible in this photo.",
  multiple_people: "More than one person is in this photo. Use a photo of just you.",
  not_a_photo: "This does not look like a photo.",
  appears_under_18: "This photo could not be checked. Only photos of adults are allowed.",
  explicit: "This photo could not be checked.",
};
type Selected = {file: File; url: string};
const box = "rounded-lg border border-black/10 bg-white/70 p-5";

export function PhotoCheck() {
  const {t, locale} = useI18n();
  const [status, setStatus] = useState<PhotoCheckStatus | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [adult, setAdult] = useState(false);
  const [agreed, setAgreed] = useState(false);
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
      const checked = await photoCheckRequest("/analyses", photoCheckResultSchema, {photos, language: locale});
      setResult(checked);
      setStatus({...status, used_today: checked.used_today});
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Service temporarily unavailable.");
      load();
    } finally {setBusy(false);}
  };

  return <section className="max-w-3xl">
    <Heading/>
    {!status.available && <p role="status" className={`mt-6 ${box}`}>{t(status.reason === "paused" ? "Free photo checks are paused until tomorrow. Please come back then." : "Photo check is not available right now.")}</p>}
    {status.available && status.consent_required && <div className={`mt-6 ${box}`}>
      <h2 className="text-xl">{t("Before you start")}</h2>
      <p className="mt-3 leading-7">{t("Your photos are sent to Google's Gemini API (paid tier) to be analysed. Google does not use them to train its models. Google keeps requests for up to 55 days, only for abuse monitoring and legal requirements. Auvylen deletes your photos as soon as your result is ready.")}</p>
      <p className="mt-3 leading-7">{t("Only upload photos of yourself or photos you have permission to use, showing people aged 18 or older.")}</p>
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
    {status.available && !status.consent_required && !result && <div className={`mt-6 ${box}`}>
      <p>{t("Choose 1 to 5 photos (JPEG or PNG)")}</p>
      {/* Styled label instead of the browser's untranslated file button. */}
      <label className="button-secondary mt-3 inline-flex cursor-pointer">{t(selected.length ? "Choose different photos" : "Choose photos")}
        <input className="sr-only" type="file" accept="image/jpeg,image/png" multiple aria-label={t("Choose 1 to 5 photos (JPEG or PNG)")} onChange={event => choose(event.target.files)}/></label>
      {selected.length > 0 && <ul className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-5">{selected.map(item => <li key={item.url}>
        {/* eslint-disable-next-line @next/next/no-img-element -- local preview, never uploaded from here */}
        <img src={item.url} alt="" className="aspect-[4/5] w-full rounded object-cover"/></li>)}</ul>}
      <button className="button-primary mt-5" disabled={!selected.length || busy} onClick={() => void check()}>{busy ? t("Checking your photos…") : t("Check my photos")}</button>
      <p className="mt-3 text-sm text-[#63706a]">{t("{used} of {limit} free checks used today", {used: status.used_today, limit: status.daily_limit})}</p>
    </div>}
    {error && <p role="alert" className="mt-5 text-[#8c513c]">{t(error)}</p>}
    {result && <Results result={result} selected={selected} onAgain={() => {setResult(null); setSelected([]);}}/>}
    <p className="mt-8 text-sm leading-6 text-[#63706a]">{t("Scores describe photo technique only, not how you look. They compare only the photos you upload.")}</p>
  </section>;
}

function Heading() {
  const {t} = useI18n();
  return <><p className="eyebrow">{t("Free photo check")}</p><h1 className="text-3xl font-medium">{t("Which of your photos works best?")}</h1>
    <p className="mt-4 leading-7 text-[#63706a]">{t("Upload up to 5 photos. We rank them on lighting, sharpness, framing, expression, eye contact and background, and give you quick tips.")}</p></>;
}

function Results({result, selected, onAgain}: {result: PhotoCheckResult; selected: Selected[]; onAgain: () => void}) {
  const {t} = useI18n();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {heading.current?.focus();}, [result]);
  const ordered = [...result.photos].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99) || a.index - b.index);
  return <div className="mt-6 space-y-4">
    <h2 ref={heading} tabIndex={-1} className="text-2xl outline-none">{t("Your results")}</h2>
    {ordered.map(photo => <ResultCard key={photo.index} photo={photo} url={selected[photo.index]?.url}/>)}
    <button className="button-secondary" onClick={onAgain}>{t("Check other photos")}</button>
  </div>;
}

function ResultCard({photo, url}: {photo: PhotoCheckPhoto; url?: string}) {
  const {t} = useI18n();
  return <article className={`${box} flex flex-col gap-4 sm:flex-row`}>
    {/* eslint-disable-next-line @next/next/no-img-element -- local preview only */}
    {url && <img src={url} alt="" className="aspect-[4/5] w-32 shrink-0 rounded object-cover"/>}
    <div className="flex-1">
      {photo.usable && photo.scores ? <>
        <p className="text-sm uppercase tracking-[0.14em] text-[#537462]">{photo.rank === 1 ? t("Best photo") : t("Rank {rank}", {rank: photo.rank ?? "–"})}</p>
        <p className="mt-1 text-3xl">{photo.display_score?.toFixed(1)} <span className="text-base text-[#63706a]">{t("/ 10 photo quality")}</span></p>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">{criteria.map(name => <div key={name} className="flex justify-between gap-2"><dt>{t(criterionLabels[name])}</dt><dd>{photo.scores?.[name]}</dd></div>)}</dl>
        {photo.tips.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{photo.tips.map(tip => <li key={tip}>{tip}</li>)}</ul>}
      </> : <p>{t(refusalLabels[photo.refusal_reason ?? ""] ?? "This photo could not be checked.")}</p>}
    </div>
  </article>;
}
