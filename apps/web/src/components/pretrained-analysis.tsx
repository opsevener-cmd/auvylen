"use client";
import Link from "next/link";
import {useEffect, useRef, useState} from "react";
import type {ResearchJob, ResearchStatus} from "@auvylen/contracts";
import {z} from "zod";
import {accountRequest, csrfToken} from "@/lib/account-api";
import {researchJobSchema, researchStatusSchema} from "@/lib/research-api";
import {sendImage, validateUpload, type UploadProgress} from "@/lib/upload";
import {pollWhileVisible} from "@/lib/polling";
import {useI18n} from "./i18n/provider";

const nativeResult = z.object({raw_score:z.number().finite(), engine:z.literal("comboloss"),
  version:z.string(), synthetic:z.literal(false), native_scale:z.tuple([z.literal(1),z.literal(5)]), calibrated:z.literal(false)});
export function PretrainedAnalysis() {
  const {t} = useI18n();
  const requestKey = useRef("");
  const [status,setStatus]=useState<ResearchStatus|null>(null),[job,setJob]=useState<ResearchJob|null>(null);
  const [file,setFile]=useState<File|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [progress,setProgress]=useState<UploadProgress|null>(null);
  useEffect(()=>{let active=true;accountRequest("/research/pretrained/status",researchStatusSchema).then(x=>{if(active)setStatus(x)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
  useEffect(()=>{if(!job||!["QUEUED","RUNNING"].includes(job.status))return;
    return pollWhileVisible(async()=>{const next=await accountRequest(`/research/jobs/${job.id}`,researchJobSchema);setJob(next);return ["QUEUED","RUNNING"].includes(next.status)},()=>setError("Service temporarily unavailable."));
  },[job]);
  const provider=status?.providers.find(x=>x.slug==="comboloss"),ready=!!(status?.enabled&&status.authorized&&provider?.available);
  const result=job?.result?nativeResult.safeParse(job.result):null;
  return <div className="page-wrap"><p className="eyebrow">{t("Independent research models")}</p><h1>{t("Pretrained Model Analysis")}</h1>
    <p className="mt-5">{t("Upload one authorized adult portrait. No personal dataset, ratings or training required.")}</p>
    <p className="mt-3">{t("Predictions reflect the training annotators' preferences, not objective beauty or a person's worth. Pose, lighting and cropping affect results. No age estimation or face alignment is performed.")}</p>
    <p className="mt-3"><Link href="/research/preferences">{t("Personal research")}</Link> · <a href="https://github.com/lucasxlu/ComboLoss/tree/2543efff58b287cb7b0ca4f7665d36855e8c62d9" rel="noreferrer" target="_blank">{t("Official model source")}</a></p>
    <form className="workspace-panel mt-6" onSubmit={async e=>{e.preventDefault();if(!file||busy||!ready)return;setBusy(true);setError("");
      try{const data=await sendImage("/research/pretrained/comboloss",file,{idempotency_key:(requestKey.current ||= crypto.randomUUID()),adult_subject_attested:true,single_subject_attested:true,authorized_consent:true},researchJobSchema,await csrfToken(),setProgress);setJob(data)}
      catch(e){setError(e instanceof Error?e.message:"Service temporarily unavailable.")}finally{setBusy(false)}}}>
      <label>{t("Model")}<select className="block w-full max-w-full" value="comboloss" onChange={()=>{}}><option value="comboloss">ComboLoss / SEResNeXt50 · SCUT-FBP5500</option></select></label>
      <p className="mt-3">{t("Native annotator scale: 1–5. Raw regression output is not clipped or converted to 1–10. No calibrated error range is available.")}</p>
      {!ready&&<p role="status" className="status-note mt-4">{t("Pretrained analysis is unavailable until checkpoint integrity, reference predictions and research-use rights are verified.")}</p>}
      <label className="analysis-file-picker">{t("Photograph of one adult")}<span className="analysis-file-picker-row"><span className="button-secondary">{t("Choose photograph")}</span><input className="sr-only" aria-label={t("Photograph of one adult")} type="file" accept="image/jpeg,image/png" required disabled={!ready||busy} onChange={e=>{setError("");const f=e.target.files?.[0]??null;try{if(f)validateUpload(f);setFile(f);requestKey.current=""}catch(err){setFile(null);setError(err instanceof Error?err.message:"Service temporarily unavailable.")}}}/><span className="selected-file-name" aria-live="polite">{file?.name??t("No photograph selected")}</span></span></label>
      <p>{t("JPEG or PNG, up to 4 MiB and 4096px; minimum short edge 224px. Images are deleted after completion or failure, with a 24-hour retention ceiling. Results expire after 24 hours.")}</p>
      <label className="mt-4 block"><input type="checkbox" required disabled={!ready||busy}/> {t("I confirm exactly one adult (18+), permission to upload and research use, and understand these limitations.")}</label>
      <button className="button-primary mt-5" disabled={!ready||busy||["QUEUED","RUNNING"].includes(job?.status??"")}>{t(busy?"Uploading photograph":"Analyze photograph")}</button>
      {progress&&<p role="status">{t(progress.stage === "uploading" ? "Uploading photograph" : progress.stage === "processing" ? "Processing image" : "Saved successfully")} {progress.percent===undefined?"":`${progress.percent}%`}</p>}
    </form>
    {error&&<p role="alert">{t(error)}</p>}
    {job&&<section className="result-card mt-5" aria-live="polite"><p>{t(job.status)}</p>
      {result?.success&&<><p className="score-hero">{result.data.raw_score.toFixed(3)}<span> {t("Native scale 1–5")}</span></p><p>ComboLoss · {result.data.version}</p></>}
      {job.status==="FAILED"&&<p>{t("Model execution failed or is unavailable. No score was generated.")}</p>}
      <button onClick={async()=>{try{await accountRequest(`/research/pretrained/jobs/${job.id}/delete`,z.object({deleted:z.boolean()}),{});setJob(null)}catch(e){setError(e instanceof Error?e.message:"Service temporarily unavailable.")}}}>{t("Delete analysis")}</button>
    </section>}
  </div>;
}
