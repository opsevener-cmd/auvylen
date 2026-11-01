"use client";
import {useEffect, useRef, useState} from "react";
import {z} from "zod";
import {useI18n} from "./i18n/provider";
import {accountRequest, csrfToken} from "@/lib/account-api";
import {researchJobSchema} from "@/lib/research-api";
import {pollWhileVisible} from "@/lib/polling";
import {sendImage, validateUpload, type UploadProgress} from "@/lib/upload";
import type {ResearchJob} from "@auvylen/contracts";

const path = "/research/native-preview";
const statusSchema = z.object({available: z.boolean(), consumer_enabled: z.literal(false), native_scale: z.tuple([z.literal(1), z.literal(7)]), collection: z.string().optional(), encoder: z.string().optional(), manifest_sha256: z.string().optional()});
export const nativeResultSchema = z.object({predicted_rating: z.number().finite().min(1).max(7), native_scale: z.tuple([z.literal(1), z.literal(7)]), research_only: z.literal(true), consumer_enabled: z.literal(false), synthetic: z.literal(false), manifest_sha256: z.string().regex(/^[a-f0-9]{64}$/), collection: z.string(), encoder: z.string()});
const pending = (job: ResearchJob | null) => job?.status === "QUEUED" || job?.status === "RUNNING";

export function NativePreviewPage() {
  const {t} = useI18n();
  const [status, setStatus] = useState<z.infer<typeof statusSchema> | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState(false);
  const key = useRef("");
  const busyRef = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const currentId = job?.id;
  const currentStatus = job?.status;
  useEffect(() => {
    let active = true;
    accountRequest(`${path}/status`, statusSchema).then(value => {if (active) setStatus(value);}).catch(() => {if (active) setError(true);});
    return () => {active = false; abort.current?.abort();};
  }, []);
  useEffect(() => {
    if (!currentId || !["QUEUED", "RUNNING"].includes(currentStatus ?? "")) return;
    let active = true;
    const stop = pollWhileVisible(async () => {
      const value = await accountRequest(`${path}/jobs/${currentId}`, researchJobSchema);
      if (active) setJob(value);
      return pending(value);
    }, () => {if (active) setError(true);});
    return () => {active = false; stop();};
  }, [currentId, currentStatus]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !consent || busyRef.current || pending(job)) return;
    busyRef.current = true; setBusy(true); setError(false); setProgress({stage: "preparing"});
    try {
      validateUpload(file);
      key.current ||= crypto.randomUUID();
      abort.current = new AbortController();
      const value = await sendImage(`${path}/jobs`, file, {idempotency_key: key.current, adult_subject_attested: true, single_subject_attested: true, authorized_consent: true}, researchJobSchema, await csrfToken(), setProgress, abort.current.signal);
      setJob(value);
      // The server confirmed saving the request, not a prediction. Keep the key for safe retries.
    } catch {setError(true); setProgress({stage: "failed"});}
    finally {busyRef.current = false; setBusy(false);}
  }
  async function remove() {
    if (!job || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(false);
    try {
      await accountRequest(`${path}/jobs/${job.id}/delete`, z.object({deleted: z.literal(true)}), {});
      setJob(null); setFile(null); key.current = ""; setProgress(null); setConsent(false);
    } catch {setError(true);}
    finally {busyRef.current = false; setBusy(false);}
  }
  const parsed = job?.result ? nativeResultSchema.safeParse(job.result) : null;
  const result = parsed?.success ? parsed.data : null;
  return <section aria-labelledby="native-preview-title" className="mx-auto max-w-4xl px-5 py-14">
    <p className="eyebrow">{t("Owner laboratory · private research")}</p>
    <h1 id="native-preview-title" className="mt-3 text-4xl">{t("Native Auvylen research preview")}</h1>
    <p className="mt-5">{t("A real human-trained feasibility model. Its prediction estimates the original annotators' subjective ratings on a 1–7 scale. It is not an objective judgment about a person.")}</p>
    <div className="mt-6 rounded border border-amber-700/30 bg-amber-50 p-5" role="note">{t("Consumer release remains blocked. The pilot is small, uncertainty is substantial, and independent pose, lighting and demographic evaluation is incomplete. No calibrated interval is available for an individual portrait.")}</div>
    <p className="mt-5 text-sm">{t("Owner access and a recent sign-in are required. Upload only one authorized adult. JPEG or PNG, up to 4 MiB and 4096 pixels, at least 224 pixels on the shorter side. Adult status and one-person content are attested, not automatically detected.")}</p>
    <p className="mt-3 text-sm">{t("Uploads are private and never used for training. Images are removed when work finishes or within one hour; results expire within 24 hours. Deletion cancels pending work and removes its result. Cleanup requires the research worker to be running.")}</p>
    {error && <p role="alert" className="mt-5">{t("Research preview unavailable. Check your Owner sign-in and connection, then retry. Requests reuse the same key. No fallback score is generated.")}</p>}
    {!status && !error ? <p className="mt-6" role="status">{t("Checking private research access…")}</p> : !status?.available ? <p className="mt-6" role="status">{t("This research preview is disabled or its reviewed checkpoint is unavailable.")}</p> : <>
      <dl className="mt-6 break-words text-sm"><dt>{t("Training collection")}</dt><dd>{status.collection}</dd><dt>{t("Visual features")}</dt><dd>{status.encoder}</dd><dt>{t("Pinned manifest SHA-256")}</dt><dd className="font-mono text-xs">{status.manifest_sha256}</dd></dl>
      <form onSubmit={submit} className="mt-8 space-y-5 rounded border border-black/15 p-6">
        <label className="block">{t("Authorized adult portrait")}<input className="mt-2 block max-w-full" type="file" accept="image/jpeg,image/png" disabled={busy || pending(job)} onChange={e => {setFile(e.target.files?.[0] ?? null); key.current = ""; setJob(null); setProgress(null);}} /></label>
        <label className="flex items-start gap-3"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={busy || pending(job)} /><span>{t("I confirm one adult subject and permission for private research inference. This upload is not consent to training or public display.")}</span></label>
        <button className="btn-primary disabled:opacity-40" disabled={!file || !consent || !status.available || busy || pending(job)}>{t("Run private native preview")}</button>
        {progress && <p role="status">{progress.stage === "uploading" ? (progress.percent === undefined ? t("Uploading image…") : t("Uploading {percent}%", {percent: progress.percent})) : progress.stage === "preparing" ? t("Preparing image") : progress.stage === "processing" ? t("Processing image") : progress.stage === "saved" ? t("Request saved; waiting for the research worker.") : t("Upload failed")}</p>}
      </form>
    </>}
    {job && <section className="mt-6 rounded border border-black/15 p-6" aria-live="polite">
      {pending(job) && <p role="status">{t("Native inference queued or running. The result appears only after verified worker completion.")}</p>}
      {job.status === "FAILED" && <p role="alert">{t("Research inference failed or expired. No score was generated. Delete this request before starting again.")}</p>}
      {job.status === "COMPLETED" && !result && <p role="alert">{t("The research result could not be verified.")}</p>}
      {result && <><h2>{t("Research prediction · native scale 1–7")}</h2><p className="my-5 text-5xl tabular-nums">{result.predicted_rating.toFixed(2)} <span className="text-xl">/ 7</span></p><p>{t("For research inspection only. This result does not unlock consumer scoring or establish model validity for this photograph.")}</p></>}
      <button className="mt-5 rounded border px-4 py-2 disabled:opacity-40" disabled={busy} onClick={() => void remove()}>{t("Delete preview and cancel pending work")}</button>
    </section>}
  </section>;
}
