"use client";
import Link from "next/link";
import {EditorialPortrait} from "./editorial-portrait";
import {useEffect, useRef, useState} from "react";
import {z} from "zod";
import type {AestheticAnalysis, AestheticResult, AestheticStatus} from "@auvylen/contracts";
import {accountRequest, csrfToken} from "@/lib/account-api";
import {aestheticAnalysisSchema, aestheticPath, aestheticStatusSchema, percent, submitAnalysis, unavailableReason} from "@/lib/aesthetic-api";
import {pollWhileVisible} from "@/lib/polling";
import {validateUpload, type UploadProgress} from "@/lib/upload";
import {useI18n} from "./i18n/provider";

const button = "rounded border border-black/20 px-3 py-2 disabled:opacity-40";
const pending = (status?: string) => status === "QUEUED" || status === "RUNNING";
const ratingLabels = ["1 · Lowest", "2", "3 · Middle", "4", "5 · Highest"];

/** Five-bar distribution: one series, direct value labels, accessible table alongside. */
function Distribution({result}: {result: AestheticResult}) {
  const {t} = useI18n();
  const top = Math.max(...result.rating_distribution, 0.0001);
  return <figure className="mt-5">
    <figcaption className="font-semibold">{t("Predicted rating distribution (annotator scale 1–5)")}</figcaption>
    <div className="distribution" role="img" aria-label={t("Predicted share of annotators choosing each rating")}>
      {result.rating_distribution.map((value, index) => <div key={index} className="distribution-row" title={`${t(ratingLabels[index])}: ${percent(value)}`}>
        <span className="distribution-label">{t(ratingLabels[index])}</span>
        <span className="distribution-track"><span className="distribution-bar" style={{width: `${Math.max(0.5, value / top * 100)}%`}} /></span>
        <span className="distribution-value">{percent(value)}</span>
      </div>)}
    </div>
    <details className="mt-3"><summary>{t("Show as table")}</summary>
      <table className="w-full text-left"><thead><tr><th>{t("Rating")}</th><th>{t("Predicted share")}</th></tr></thead>
        <tbody>{result.rating_distribution.map((value, index) => <tr key={index}><td>{index + 1}</td><td>{percent(value)}</td></tr>)}</tbody></table>
    </details>
  </figure>;
}

function ResultCard({analysis}: {analysis: AestheticAnalysis}) {
  const {t, locale} = useI18n();
  const result = analysis.result;
  if (!result) return null;
  return <div className="result-card mt-6" aria-live="polite">
    {result.synthetic && <p role="alert">{t("Synthetic test model: this number comes from a model trained on generated data. It is not a real aesthetic prediction.")}</p>}
    <p className="eyebrow mt-4">{t("Estimated annotator rating")}</p>
    <p className="score-hero">{result.score_10.toFixed(1)}<span> / 10</span></p>
    {result.interval_low !== null && result.interval_high !== null
      ? <p>{t("Calibrated {level}% range for the model's error: {low}–{high}", {level: Math.round(result.interval_level * 100), low: result.interval_low.toFixed(1), high: result.interval_high.toFixed(1)})}</p>
      : <p>{t("No calibrated error range is available for this model.")}</p>}
    <p>{t("Expected rating {value} on the 1–5 annotator scale · predicted annotator spread ±{spread} on the 1–10 scale", {value: result.expected_rating_5.toFixed(2), spread: result.rating_spread_10.toFixed(1)})}</p>
    <Distribution result={result} />
    <p className="mt-4 text-sm">{t("Spread describes how much annotators would be expected to disagree about this photograph. The calibrated range describes how far the model's own estimate has typically been from real annotator averages on people it never saw.")}</p>
    <dl className="model-facts mt-4 text-sm">
      <dt>{t("Model version")}</dt><dd>{result.version}</dd>
      <dt>{t("Calibration version")}</dt><dd>{result.calibration_version}</dd>
      <dt>{t("Visual features")}</dt><dd>{result.extractor}</dd>
      <dt>{t("Analyzed")}</dt><dd>{new Date(result.timestamp).toLocaleString(locale)} · {result.processing_duration_ms.toFixed(0)} {t("ms")}</dd>
      <dt>{t("Adult, single subject")}</dt><dd>{t("Confirmed by your attestation; no age estimation or automated face detection is performed.")}</dd>
    </dl>
  </div>;
}

export function AestheticAnalysisPage() {
  const {t, locale} = useI18n();
  const [status, setStatus] = useState<AestheticStatus | null>(null);
  const [history, setHistory] = useState<AestheticAnalysis[]>([]);
  const [current, setCurrent] = useState<AestheticAnalysis | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const key = useRef<string>("");
  const currentId = current?.id;
  const currentStatus = current?.status;
  useEffect(() => {
    let active = true;
    accountRequest(`${aestheticPath}/status`, aestheticStatusSchema).then(async loaded => {
      if (!active) return;
      setStatus(loaded);
      if (!loaded.authorized) return;
      const saved = await accountRequest(`${aestheticPath}/analyses`, z.array(aestheticAnalysisSchema));
      if (active) {setHistory(saved); setCurrent(saved.find(item => pending(item.status)) ?? saved[0] ?? null);}
    }).catch(e => {if (active) setError(e instanceof Error ? e.message : "Aesthetic analysis unavailable.");});
    return () => {active = false;};
  }, []);
  useEffect(() => () => {if (preview) URL.revokeObjectURL(preview);}, [preview]);
  useEffect(() => {
    if (!currentId || !pending(currentStatus)) return;
    let active = true;
    const stop = pollWhileVisible(async () => {
      const updated = await accountRequest(`${aestheticPath}/analyses/${currentId}`, aestheticAnalysisSchema);
      if (!active) return false;
      setCurrent(updated); setHistory(items => [updated, ...items.filter(item => item.id !== updated.id)]);
      return pending(updated.status);
    }, () => {if (active) setError("Cannot check the analysis. Reload to resume.");});
    return () => {active = false; stop();};
  }, [currentId, currentStatus]);
  const ready = !!status?.authorized && !!status.available;
  const model = status?.model;
  return <section className="aesthetic-workspace">
    <header className="aesthetic-landing"><div className="aesthetic-landing-copy">
    <p className="eyebrow">{t("Auvylen Analyze · research preview")}</p>
    <h1 className="text-3xl font-medium">{t("Aesthetic analysis")}</h1>
    <p className="mt-5">{t("Auvylen's own model estimates how a group of human annotators would rate a photograph on a five-point scale, then reports the expected rating on a 1–10 scale with the full predicted distribution. It reflects those annotators' statistical preferences, not objective beauty.")}</p>
    <p className="mt-3">{t("This is separate from your personal preference models, which learn only from your own ratings.")} <Link href="/research/preferences" className="underline">{t("Personal research")}</Link></p>
    </div><EditorialPortrait variant="analysis"/></header>
    <div className="aesthetic-content">
    {error && <p role="alert" className="mt-5">{t(error)} <Link href="/login" className="underline">{t("Sign in")}</Link></p>}
    {status && !status.authorized && <p role="status" className="mt-5">{t("Research is disabled or operator authorization is required.")}</p>}
    {status && status.authorized && !status.available && <div role="status" className="mt-5">
      <p className="font-semibold">{t("Aesthetic scoring is not available yet")}</p>
      <p>{t(unavailableReason(status.reason))}</p>
      <p className="mt-2">{t("No score is shown until an authorized human-rated dataset has trained a model that passes validation. Auvylen never substitutes simulated results.")}</p>
    </div>}
    {model && <details className="mt-6 rounded border p-4" open={model.synthetic}>
      <summary>{t("Model card · version {version}", {version: model.model_version})}</summary>
      {model.synthetic && <p role="alert" className="mt-3">{t("This installed model was trained on generated test data and is enabled only in development or test environments.")}</p>}
      <dl className="model-facts mt-3 text-sm">
        <dt>{t("Training data")}</dt><dd>{model.dataset_name} · {model.dataset_license}</dd>
        <dt>{t("Annotators")}</dt><dd>{model.annotator_population}</dd>
        <dt>{t("Held-out test set")}</dt><dd>{t("{images} photographs of {subjects} people never used for training, model selection or calibration", {images: model.test_images, subjects: model.test_subjects})}</dd>
      </dl>
      <table className="mt-3 w-full text-left text-sm"><caption>{t("Held-out test comparison")}</caption>
        <thead><tr><th>{t("Measure")}</th><th>{t("This model")}</th><th>{t("Simple baseline")}</th></tr></thead>
        <tbody>
          <tr><td>{t("Mean absolute error (1–5 scale)")}</td><td>{model.test_mae.toFixed(3)}</td><td>{model.mean_baseline_mae.toFixed(3)}</td></tr>
          <tr><td>{t("Distribution loss")}</td><td>{model.test_distribution_loss.toFixed(4)}</td><td>{model.mean_distribution_baseline_loss.toFixed(4)}</td></tr>
          <tr><td>{t("Spearman rank correlation")}</td><td>{model.test_spearman === null ? t("Unavailable") : model.test_spearman.toFixed(3)}</td><td>—</td></tr>
          <tr><td>{t("Calibrated range coverage")}</td><td>{model.interval_test_coverage === null ? t("Unavailable") : percent(model.interval_test_coverage)}</td><td>{t("Target")} {percent(model.interval_level)}</td></tr>
        </tbody></table>
      <p className="mt-2 text-sm">{t("Baselines predict the average training rating or rating distribution for every photograph.")} {model.calibration_version} · {model.extractor}</p>
    </details>}
    {ready && <form className="upload-zone mt-6" onSubmit={async event => {
      event.preventDefault();
      if (busy || !file) {if (!file) setError("Choose a photograph."); return;}
      setBusy(true); setError("");
      key.current ||= crypto.randomUUID();
      try {
        const token = await csrfToken();
        const queued = await submitAnalysis(file, {idempotency_key: key.current, adult_subject_attested: true, single_subject_attested: true, authorized_consent: true}, token, setProgress);
        key.current = "";
        setCurrent(queued); setHistory(items => [queued, ...items.filter(item => item.id !== queued.id)]);
      } catch (e) {setError(e instanceof Error ? e.message : "Analysis request failed."); setProgress(null);}
      finally {setBusy(false);}
    }}>
      <h2 className="text-xl">{t("Analyze a photograph")}</h2>
      <p className="mt-2 text-sm">{t("One JPEG or PNG up to 4 MiB, at least 224 pixels on the shorter side, showing one adult. The private copy is deleted as soon as the analysis finishes.")}</p>
      <label className="mt-4 block">{t("Photograph of one adult")}<input className="mt-2 block" type="file" accept="image/jpeg,image/png" required disabled={busy} onChange={event => {
        const chosen = event.target.files?.[0] ?? null;
        setError(""); setProgress(null); key.current = "";
        try {if (chosen) validateUpload(chosen); setFile(chosen); setPreview(chosen ? URL.createObjectURL(chosen) : "");}
        catch (e) {setFile(null); setPreview(""); setError(e instanceof Error ? e.message : "Choose a JPEG or PNG image.");}
      }} /></label>
      {/* Local object URL only; the photograph is never sent to a third party. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {preview && <img src={preview} alt={t("Selected photograph preview")} className="analysis-preview mt-3" />}
      <fieldset className="mt-4 space-y-2" disabled={busy}><legend className="font-semibold">{t("Confirmations")}</legend>
        <label className="block"><input type="checkbox" required />{t("The photograph shows exactly one person, and that person is an adult (18+).")}</label>
        <label className="block"><input type="checkbox" required />{t("I have the person's permission and the rights to upload this photograph for research analysis.")}</label>
        <label className="block"><input type="checkbox" required />{t("I understand the score reflects annotators' statistical preferences, not objective beauty or worth.")}</label>
      </fieldset>
      <button className="button-primary mt-4" disabled={busy || pending(current?.status)}>{t("Analyze photograph")}</button>
      {progress && <p className="mt-3" aria-live="polite">{progress.stage === "uploading" ? t("Uploading {percent}", {percent: progress.percent === undefined ? "…" : `${progress.percent}%`}) : progress.stage === "processing" ? t("Checking and queueing the photograph…") : progress.stage === "saved" ? t("Queued for analysis.") : ""}</p>}
    </form>}
    {current && <div className="mt-6 rounded border p-4">
      <progress max={100} value={current.progress} aria-label={t("Server-reported job progress")} />
      <p>{t("Analysis:")} {t(current.status)} · {t(current.phase)} · {current.progress}%</p>
      {current.failure_reason && <p>{t(current.failure_reason)}</p>}
      <ResultCard analysis={current} />
    </div>}
    {history.length > 0 && <><h2 className="mt-10 text-xl">{t("Your analyses")}</h2>
      <ul className="mt-3 space-y-2">{history.map(item => <li key={item.id} className="flex flex-wrap items-center gap-3">
        <button className="underline" onClick={() => setCurrent(item)}>{new Date(item.created_at).toLocaleString(locale)} · {t(item.status)}{item.result ? ` · ${item.result.score_10.toFixed(1)} / 10` : ""}</button>
        <button className={button} disabled={busy} onClick={async () => {
          if (!window.confirm(t("Delete this analysis and its result?"))) return;
          setBusy(true); setError("");
          try {
            await accountRequest(`${aestheticPath}/analyses/${item.id}/delete`, z.object({deleted: z.boolean()}), {});
            setHistory(items => items.filter(other => other.id !== item.id));
            setCurrent(selected => selected?.id === item.id ? null : selected);
          } catch (e) {setError(e instanceof Error ? e.message : "Deletion failed.");}
          finally {setBusy(false);}
        }}>{t("Delete analysis")}</button>
      </li>)}</ul></>}
    {status && <><h2 className="mt-10 text-xl">{t("Limitations")}</h2>
      <ul className="mt-3 list-disc pl-5 space-y-1">{status.limitations.map(text => <li key={text}>{t(text)}</li>)}</ul></>}
  </div></section>;
}
