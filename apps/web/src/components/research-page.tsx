"use client";
import {useI18n} from "@/components/i18n/provider";

import Link from "next/link";
import {pollWhileVisible} from "@/lib/polling";
import {useEffect, useState} from "react";
import {z} from "zod";
import type {ResearchJob, ResearchStatus} from "@auvylen/contracts";
import {accountRequest} from "@/lib/account-api";
import {researchJobSchema, researchScoreSchema, researchStatusSchema} from "@/lib/research-api";

export function ResearchPage() {
  const {t} = useI18n();
  const [status, setStatus] = useState<ResearchStatus | null>(null);
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const jobId = job?.id;
  const jobStatus = job?.status;
  useEffect(() => {
    let active = true;
    Promise.all([accountRequest("/research/status", researchStatusSchema),
      accountRequest("/research/jobs", z.array(researchJobSchema))]).then(([status, jobs]) => {
        if (active) {setStatus(status); setJobs(jobs);}
      }).catch(error => {if (active) setError(error instanceof Error ? error.message : "Research unavailable.");});
    return () => {active = false;};
  }, []);
  useEffect(() => {
    if (!jobId || !jobStatus || !["QUEUED", "RUNNING"].includes(jobStatus)) return;
    let active = true;
    const stop = pollWhileVisible(async () => {
      const updated = await accountRequest(`/research/jobs/${jobId}`, researchJobSchema);
      if (!active) return false;
      setJob(updated); setJobs(jobs => [updated, ...jobs.filter(item => item.id !== updated.id)]);
      return ["QUEUED", "RUNNING"].includes(updated.status);
    }, () => {if (active) setError("Cannot check job status. Reload to retry.");});
    return () => {active = false; stop();};
  }, [jobId, jobStatus]);
  const score = researchScoreSchema.safeParse(job?.result);
  return <section className="max-w-2xl">
    <h1 className="text-3xl font-medium">{t("Research workspace")}</h1>
    <p className="mt-5">{t("Authorized, non-commercial testing. Research jobs do not deduct Credits.")}</p>
    <p className="mt-6"><Link href="/research/preferences" className="button-primary">{t("Manage personal preference datasets")}</Link> <Link href="/research/aesthetic" className="button-secondary">{t("Aesthetic analysis")}</Link></p>
    <p className="mt-3">{t("Use personal preference datasets to train numerical rating models and predict from new photographs. Synthetic / Development Analysis remains available separately.")}</p>
    {error && <p role="alert" className="mt-5">{t(error)} <Link href="/login" className="underline">{t("Sign in")}</Link></p>}
    {status && !status.authorized && <p className="mt-5">{t("Research is disabled or operator authorization is required.")}</p>}
    {status?.synthetic_available && <button disabled={busy || !!job && ["QUEUED", "RUNNING"].includes(job.status)} className="mt-6 rounded-md bg-[#253e34] px-5 py-3 text-white disabled:opacity-50" onClick={async () => {
      setBusy(true); setError("");
      try {
        const queued = await accountRequest("/research/jobs", researchJobSchema, {provider: "mock", idempotency_key: crypto.randomUUID()});
        setJob(queued); setJobs(jobs => [queued, ...jobs]);
      } catch (error) {setError(error instanceof Error ? error.message : "Research unavailable.");}
      finally {setBusy(false);}
    }}>{t("Run Synthetic Research Analysis")}</button>}
    {job && <div className="mt-8 rounded-lg border border-black/10 p-5"><p>{t("Research status:")} {t(job.status)}</p>
      {score.success && <><p className="mt-4 text-2xl">{t("Synthetic score:")} {score.data.display_score.toFixed(1)}</p><p>{t("Raw score:")} {score.data.raw_score}</p><p>{t("Engine:")} {score.data.engine} {t("· Version:")} {score.data.version}</p></>}
      {job.failure_reason && <p>{t(job.failure_reason)}</p>}
      {["QUEUED", "RUNNING"].includes(job.status) && <button className="underline mt-3" disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try {
          const cancelled = await accountRequest(`/research/jobs/${job.id}/cancel`, researchJobSchema, {});
          setJob(cancelled); setJobs(jobs => jobs.map(item => item.id === cancelled.id ? cancelled : item));
        } catch (error) {setError(error instanceof Error ? error.message : "Cancellation unavailable.");}
        finally {setBusy(false);}
      }}>{t("Cancel research job")}</button>}
    </div>}
    <h2 className="mt-10 text-xl">{t("Model availability")}</h2>
    <ul className="mt-4 space-y-2">{status?.providers.map(provider => <li key={provider.slug}>{t(provider.display_name)}: {provider.available ? (provider.slug === "custom" ? t("Personal rating workflow available") : t("Adapter available; image inference not integrated")) : t("Unavailable")}</li>)}</ul>
    <h2 className="mt-10 text-xl">{t("Your research jobs")}</h2>{jobs.length === 0 && <p className="mt-3">{t("No saved jobs yet. Open personal preference datasets to upload and rate photographs.")}</p>}
    <ul className="mt-4 space-y-3">{jobs.map(item => <li key={item.id}><button className="underline" onClick={() => setJob(item)}>{item.provider} · {t(item.status)}</button></li>)}</ul>
  </section>;
}
