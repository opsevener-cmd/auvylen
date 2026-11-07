"use client";
import Link from "next/link";
import {useCallback, useEffect, useRef, useState} from "react";
import {z} from "zod";
import {useI18n} from "./i18n/provider";
import {AccountError, accountRequest, csrfToken, freshOwnerSignIn} from "@/lib/account-api";
import {researchJobSchema} from "@/lib/research-api";
import {pollWhileVisible} from "@/lib/polling";
import {sendImage, validateUpload, type UploadProgress} from "@/lib/upload";
import type {ResearchJob} from "@auvylen/contracts";

const path = "/research/native-preview";
const statusSchema = z.object({
  available: z.boolean(), consumer_enabled: z.literal(false), native_scale: z.tuple([z.literal(1), z.literal(7)]),
  collection: z.string().optional(), encoder: z.string().optional(), manifest_sha256: z.string().optional(),
  release_failures: z.array(z.string()).optional(),
  model: z.object({
    trained_at: z.string().optional(), selection_protocol: z.string().optional(),
    training_subjects: z.number().int().nullable().optional(), heldout_subjects: z.number().int().nullable().optional(),
    heldout_mae: z.number().finite().nullable().optional(), heldout_spearman: z.number().finite().nullable().optional(),
    baseline_mae: z.number().finite().nullable().optional(),
  }).optional(),
});
const historySchema = z.array(researchJobSchema);
const shortPin = (pin: string) => pin.slice(0, 12);
const inputCheckSchema = z.object({verdict: z.enum(["typical", "unusual", "outside", "unchecked"]), distance: z.number().finite().nullable().optional(), caution_above: z.number().finite().nullable().optional(), outside_above: z.number().finite().nullable().optional()});
export const nativeResultSchema = z.object({predicted_rating: z.number().finite().min(1).max(7).nullable(), input_check: inputCheckSchema.default({verdict: "unchecked"}), native_scale: z.tuple([z.literal(1), z.literal(7)]), research_only: z.literal(true), consumer_enabled: z.literal(false), synthetic: z.literal(false), manifest_sha256: z.string().regex(/^[a-f0-9]{64}$/), collection: z.string(), encoder: z.string()}).refine(v => {
  const c=v.input_check;
  if(c.verdict === "unchecked") return true; // Historical records, explicitly labelled below.
  if(c.distance == null || c.caution_above == null || c.outside_above == null || c.distance < 0 || c.caution_above <= 0 || c.outside_above <= c.caution_above) return false;
  const expected=c.distance > c.outside_above ? "outside" : c.distance > c.caution_above ? "unusual" : "typical";
  return c.verdict === expected && (v.predicted_rating === null) === (c.verdict === "outside");
}, "Input check and score must agree");
const pending = (job: ResearchJob | null) => job?.status === "QUEUED" || job?.status === "RUNNING";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const RESULT_HOURS = 24;

/** Plain-language reasons the release gate recorded. Unknown codes are shown verbatim. */
export const releaseReasons: Record<string, string> = {
  insufficient_test_subjects: "Too few independent people in the held-out test",
  does_not_beat_baselines: "Does not beat simple average-rating baselines on held-out people",
  weak_rank_correlation: "Weak rank agreement with the annotators on held-out people",
  real_pose_review_missing: "No independent pose and framing review",
  cohort_review_underpowered: "Too few people per cohort to review differences between groups",
  photographic_sensitivity: "Predictions move too much when lighting, crop or rotation change",
  robustness_evaluation_missing: "Lighting, crop and rotation checks are incomplete",
  incomplete_evaluation: "The evaluation record is incomplete",
  nonfinite_evaluation: "The evaluation record is incomplete",
  synthetic_data: "Trained on generated data",
};

type Failure = {status: number; message: string};
const failure = (error: unknown): Failure => error instanceof AccountError
  ? {status: error.status, message: error.message}
  : {status: 0, message: error instanceof Error ? error.message : "Service temporarily unavailable."};

function setJobParam(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("job", id); else url.searchParams.delete("job");
  window.history.replaceState(window.history.state, "", url);
}

export function NativePreviewPage() {
  const {t, locale} = useI18n();
  const [status, setStatus] = useState<z.infer<typeof statusSchema> | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [history, setHistory] = useState<ResearchJob[] | null>(null);
  const [historyFailed, setHistoryFailed] = useState(false);
  const key = useRef("");
  const busyRef = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const picker = useRef<HTMLInputElement | null>(null);
  const alertRef = useRef<HTMLParagraphElement | null>(null);
  const clearRequest = useCallback(() => {
    setJob(null); setFile(null); setPreview(null); key.current = ""; setProgress(null); setConsent(false); setJobParam(null);
    if (picker.current) picker.current.value = "";
  }, []);
  const currentId = job?.id;
  const currentStatus = job?.status;
  const settled = !["QUEUED", "RUNNING"].includes(currentStatus ?? "");
  // Refresh the list whenever the open request settles, is created or is removed.
  useEffect(() => {
    if (!settled) return;
    let active = true;
    accountRequest(`${path}/jobs`, historySchema)
      .then(rows => {if (active) {setHistory(rows); setHistoryFailed(false);}})
      .catch(() => {if (active) setHistoryFailed(true);});
    return () => {active = false;};
  }, [currentId, settled]);
  useEffect(() => {
    let active = true;
    const checking = accountRequest(`${path}/status`, statusSchema).then(value => {if (active) setStatus(value);}).catch(e => {if (active) setError(failure(e));});
    // Restore a request after reload; the server re-checks Owner access and ownership.
    const saved = new URLSearchParams(window.location.search).get("job");
    let restored: Promise<unknown> = Promise.resolve();
    if (saved && uuid.test(saved)) {
      restored = accountRequest(`${path}/jobs/${saved}`, researchJobSchema).then(value => {if (active) setJob(value);}).catch(e => {
        if (!active) return;
        const value = failure(e);
        if (value.status === 404) {clearRequest(); setNotice("That preview request has expired or was deleted. Nothing was kept.");}
        else setError(value);
      });
    } else if (saved) setJobParam(null);
    void Promise.all([checking, restored]).then(() => {if (active) setRestoring(false);});
    return () => {active = false; abort.current?.abort();};
  }, [clearRequest]);
  // Errors render above the form; move focus there so they are not missed off-screen.
  useEffect(() => {if (error) alertRef.current?.focus();}, [error]);
  useEffect(() => () => {if (preview) URL.revokeObjectURL(preview);}, [preview]);
  useEffect(() => {
    if (!currentId || !["QUEUED", "RUNNING"].includes(currentStatus ?? "")) return;
    let active = true;
    const stop = pollWhileVisible(async () => {
      const value = await accountRequest(`${path}/jobs/${currentId}`, researchJobSchema);
      if (active) {setJob(value); if (!pending(value)) setProgress(null);}
      return pending(value);
    }, e => {
      if (!active) return;
      const value = failure(e);
      if (value.status === 404) {clearRequest(); setError(null); setNotice("That preview request has expired or was deleted. Nothing was kept.");}
      else setError(value);
    }, 1000); // Owner-only, one job: inference takes well under a second on CPU.
    return () => {active = false; stop();};
  }, [currentId, currentStatus, clearRequest]);
  function choose(next: File | null) {
    setJob(null); setJobParam(null);
    setFile(next); setPreview(next ? URL.createObjectURL(next) : null); key.current = ""; setProgress(null); setError(null); setNotice(null);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !consent || busyRef.current || restoring || pending(job)) return;
    busyRef.current = true; setBusy(true); setError(null); setNotice(null); setProgress({stage: "preparing"});
    try {
      validateUpload(file);
      key.current ||= crypto.randomUUID();
      abort.current = new AbortController();
      const value = await sendImage(`${path}/jobs`, file, {idempotency_key: key.current, adult_subject_attested: true, single_subject_attested: true, authorized_consent: true}, researchJobSchema, await csrfToken(), setProgress, abort.current.signal);
      // The server confirmed saving the request, not a prediction. Keep the key for safe retries.
      setJob(value); setJobParam(value.id);
    } catch (e) {setError(failure(e)); setProgress({stage: "failed"});}
    finally {busyRef.current = false; setBusy(false);}
  }
  async function remove() {
    if (!job || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(null);
    try {
      await accountRequest(`${path}/jobs/${job.id}/delete`, z.object({deleted: z.literal(true)}), {});
      clearRequest();
      setNotice("Preview deleted. Its image and result were removed.");
    } catch (e) {
      const value = failure(e);
      // Already expired or removed on the server: nothing remains to delete.
      if (value.status === 404) {clearRequest(); setNotice("That preview request has expired or was deleted. Nothing was kept.");}
      else setError(value);
    }
    finally {busyRef.current = false; setBusy(false);}
  }
  const parsed = job?.status === "COMPLETED" && job.result ? nativeResultSchema.safeParse(job.result) : null;
  const result = parsed?.success ? parsed.data : null;
  const expires = job ? new Date(new Date(job.created_at).getTime() + RESULT_HOURS * 3600_000) : null;
  const signIn = error && (error.status === 401 || error.message === freshOwnerSignIn);
  const locked = busy || restoring || pending(job);
  const failures = status?.release_failures ?? [];
  const model = status?.model;
  const activePin = status?.manifest_sha256;
  const open = async (row: ResearchJob) => {
    if (busyRef.current) return;
    busyRef.current=true; setBusy(true); setJob(null); setProgress(null); setError(null);
    try {
      const current=await accountRequest(`${path}/jobs/${row.id}`,researchJobSchema);
      setJob(current); setJobParam(current.id); setNotice(null);
    } catch(e) {
      const value=failure(e);
      if(value.status === 404) {clearRequest();setHistory(rows=>rows?.filter(r=>r.id!==row.id)??null);setNotice("That preview request has expired or was deleted. Nothing was kept.");}
      else setError(value);
    } finally {busyRef.current=false;setBusy(false);}
  };
  return <section aria-labelledby="native-preview-title" className="aesthetic-workspace native-preview">
    <header className="research-heading">
      <p className="eyebrow">{t("Owner laboratory · private research")}</p>
      <h1 id="native-preview-title">{t("Native Auvylen research preview")}</h1>
      <p>{t("A real human-trained feasibility model. Its prediction estimates the original annotators' subjective ratings on a 1–7 scale. It is not an objective judgment about a person.")}</p>
    </header>
    <div className="aesthetic-content">
      <div className="research-notice" role="note">
        <p>{t("Consumer release remains blocked. The pilot is small, uncertainty is substantial, and independent pose, lighting and demographic evaluation is incomplete. No calibrated interval is available for an individual portrait.")}</p>
        <p className="mt-3 text-sm">{t("The experimental input check measures feature distance, not face detection, adulthood, fairness or prediction accuracy. A passing check is not evidence that an image is suitable.")}</p>
      </div>
      {error && <p ref={alertRef} tabIndex={-1} role="alert" className="mt-6 scroll-mt-28">{t(error.message)} {signIn && <Link href="/login" className="underline">{t("Sign in again")}</Link>}</p>}
      {notice && <p role="status" className="mt-6">{t(notice)}</p>}
      {!status && !error ? <p className="mt-6" role="status">{t("Checking private research access…")}</p> : status && !status.available ? <p className="mt-6" role="status">{t("This research preview is disabled or its reviewed checkpoint is unavailable.")}</p> : null}
      {status?.available && <>
        <h2 className="native-section-title">{t("Pinned checkpoint")}</h2>
        <dl className="model-facts mt-4 text-sm">
          <dt>{t("Training collection")}</dt><dd>{status.collection}</dd>
          <dt>{t("Visual features")}</dt><dd>{status.encoder}</dd>
          <dt>{t("Pinned manifest SHA-256")}</dt><dd className="font-mono text-xs">{status.manifest_sha256}</dd>
        </dl>
        {failures.length > 0 && <details className="native-gate mt-5">
          <summary>{t("Why release is blocked ({count} open checks)", {count: failures.length})}</summary>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{failures.map(code => <li key={code}>{releaseReasons[code] ? t(releaseReasons[code]) : <span className="font-mono">{code}</span>}</li>)}</ul>
        </details>}
        <form onSubmit={submit} className="upload-zone mt-10">
          <h2>{t("Run a private preview")}</h2>
          <p className="mt-2 text-sm">{t("Owner access and a recent sign-in are required. Upload only one authorized adult. JPEG or PNG, up to 4 MiB and 4096 pixels, at least 224 pixels on the shorter side. Adult status and one-person content are attested, not automatically detected.")}</p>
          <label className="analysis-file-picker">{t("Authorized adult portrait")}<span className="analysis-file-picker-row"><span className="button-secondary" aria-hidden="true">{t("Choose photograph")}</span><input ref={picker} aria-label={t("Authorized adult portrait")} aria-describedby="native-selected-file" className="sr-only" type="file" accept="image/jpeg,image/png" disabled={locked} onChange={e => choose(e.target.files?.[0] ?? null)} /><span id="native-selected-file" className="selected-file-name" aria-live="polite">{file?.name ?? t("No photograph selected")}</span></span></label>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {preview && <img src={preview} alt={t("Selected photograph preview")} className="analysis-preview mt-4" />}
          <label className="mt-5 flex items-start gap-3"><input className="mt-1" type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={locked} /><span>{t("I confirm one adult subject and permission for private research inference. This upload is not consent to training or public display.")}</span></label>
          <button className="button-primary mt-6" disabled={!file || !consent || locked}>{t("Run private native preview")}</button>
          {progress && progress.stage !== "failed" && <p className="mt-4" role="status">{progress.stage === "uploading" ? (progress.percent === undefined ? t("Uploading image…") : t("Uploading {percent}%", {percent: progress.percent})) : progress.stage === "preparing" ? t("Preparing image") : progress.stage === "processing" ? t("Processing image") : t("Request saved; waiting for the research worker.")}</p>}
          <p className="mt-5 text-sm wizard-note">{t("Uploads are private and never used for training. Images are removed when work finishes or within one hour; results expire within 24 hours. Deletion cancels pending work and removes its result. Cleanup requires the research worker to be running.")}</p>
        </form>
      </>}
      {job && <section className="result-card native-result mt-10" aria-live="polite" aria-labelledby="native-result-title">
        <h2 id="native-result-title">{result?.predicted_rating != null ? t("Research prediction · native scale 1–7") : t("Private preview request")}</h2>
        {pending(job) && <p className="mt-4" role="status">{t("Native inference queued or running. The result appears only after verified worker completion.")}</p>}
        {job.status === "FAILED" && <p className="mt-4" role="alert">{t("Research inference failed or expired. No score was generated. Delete this request before starting again.")}</p>}
        {job.status === "COMPLETED" && !result && <p className="mt-4" role="alert">{t("The research result could not be verified.")}</p>}
        {result?.input_check.verdict === "unchecked" && <p role="status" className="mt-4">{t("This checkpoint has no supported input check. New predictions are withheld; an older retained score may predate this safeguard.")}</p>}
        {result && result.predicted_rating === null && <div className="native-reading mt-5" role="status">
          <h3>{t("No score for this image")}</h3>
          <p className="mt-2 text-sm">{result.input_check.verdict === "unchecked" ? t("No supported input check is available for this checkpoint.") : t("It does not resemble the frontal adult portraits the model learned from, so no number is shown. Use a clear, front-facing photograph of one adult that fills most of the frame.")}</p>
        </div>}
        {result && result.predicted_rating !== null && <>
          {result.input_check.verdict === "unusual" && <p className="mt-4" role="status">{t("This image looks unlike the frontal portraits the model learned from (for example rotated, tightly cropped or unusually lit). Treat the number with extra caution.")}</p>}
          <p className="score-hero">{result.predicted_rating.toFixed(2)}<span> / 7</span></p>
          <div className="native-scale" aria-hidden="true"><span className="native-scale-marker" style={{left: `${(result.predicted_rating - 1) / 6 * 100}%`}} /></div>
          <p className="native-scale-labels text-xs" aria-hidden="true"><span>1</span><span>4</span><span>7</span></p>
          <p className="mt-5">{t("For research inspection only. This result does not unlock consumer scoring or establish model validity for this photograph.")}</p>
          <div className="native-reading mt-5">
            <h3>{t("How to read this number")}</h3>
            <p className="mt-2 text-sm">{t("4 is the scale's average anchor, not necessarily the observed sample mean. The prediction estimates the original adult raters' response to a similar portrait.")}</p>
            {model?.heldout_mae != null && model.heldout_subjects != null && result.manifest_sha256 === activePin && <p className="mt-2 text-sm">{t("On {count} people the model never saw, its predictions differed from the raters' average by {mae} points on average. Always guessing the training average differed by {baseline}.", {count: model.heldout_subjects, mae: model.heldout_mae.toFixed(2), baseline: model.baseline_mae == null ? "—" : model.baseline_mae.toFixed(2)})}</p>}
          </div>
          <dl className="model-facts mt-4 text-sm"><dt>{t("Prediction checkpoint SHA-256")}</dt><dd className="font-mono text-xs">{result.manifest_sha256}</dd></dl>
          <p className="mt-3 text-sm wizard-note">{t("Two decimals are shown for inspection; they do not indicate precision.")}</p>
        </>}
        {expires && <p className="mt-4 text-sm wizard-note">{t("This request and any result are removed by {time}.", {time: expires.toLocaleString(locale)})}</p>}
        <button className="button-secondary mt-6" disabled={busy} onClick={() => void remove()}>{pending(job) ? t("Delete preview and cancel pending work") : t("Delete this preview now")}</button>
      </section>}
      {status?.available && <section className="native-history mt-12" aria-labelledby="native-history-title">
        <h2 id="native-history-title" className="native-section-title">{t("Your retained previews")}</h2>
        <p className="mt-2 text-sm wizard-note">{t("Each result keeps the checkpoint that produced it. Results are deleted automatically after 24 hours.")}</p>
        {historyFailed && <p className="mt-4 text-sm" role="status">{t("Preview history is temporarily unavailable.")}</p>}
        {history && history.length === 0 && <p className="mt-4 text-sm">{t("No retained previews.")}</p>}
        {history && history.length > 0 && <ul className="native-history-list mt-4">{history.map(row => {
          const value = row.status === "COMPLETED" && row.result ? nativeResultSchema.safeParse(row.result) : null;
          const scored = value?.success ? value.data : null;
          return <li key={row.id} aria-current={row.id === job?.id ? "true" : undefined}>
            {scored?.predicted_rating != null ? <span className="native-history-score">{scored.predicted_rating.toFixed(2)}</span> : <span className="native-history-score native-history-label">{t(scored || row.status === "FAILED" ? "No score" : "Pending")}</span>}
            <span className="native-history-meta">{new Date(row.created_at).toLocaleString(locale)}{scored && <> · <span className="font-mono">{shortPin(scored.manifest_sha256)}</span> · {scored.manifest_sha256 === activePin ? t("current model") : t("earlier model")}</>}</span>
            <button className="button-secondary" disabled={locked || row.id === job?.id} onClick={() => void open(row)}>{t("Open")}</button>
          </li>;})}</ul>}
      </section>}
    </div>
  </section>;
}
