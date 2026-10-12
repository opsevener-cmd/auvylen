"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {z} from "zod";
import type {ResearchJob, ResearchStatus} from "@auvylen/contracts";
import {accountRequest} from "@/lib/account-api";
import {researchJobSchema, researchScoreSchema, researchStatusSchema} from "@/lib/research-api";

export function ResearchPage() {
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
    let polls = 0;
    const timer = setInterval(() => {
      if (++polls > 60) {clearInterval(timer); setError("Still queued. Reload to check the saved job."); return;}
      accountRequest(`/research/jobs/${jobId}`, researchJobSchema).then(updated => {
        if (active) {setJob(updated); setJobs(jobs => [updated, ...jobs.filter(item => item.id !== updated.id)]);}
      }).catch(() => {if (active) {setError("Cannot check job status. Reload to retry."); clearInterval(timer);}});
    }, 1500);
    return () => {active = false; clearInterval(timer);};
  }, [jobId, jobStatus]);
  const score = researchScoreSchema.safeParse(job?.result);
  return <section className="max-w-2xl">
    <h1 className="text-3xl font-medium">Research workspace</h1>
    <p className="mt-5">Authorized, non-commercial testing. Research jobs do not deduct Credits.</p>
    <p className="mt-3"><Link href="/research/preferences" className="underline">Manage personal preference datasets</Link></p>
    <p className="mt-3">Only Synthetic / Development Analysis is runnable. No real facial model or training algorithm is installed.</p>
    {error && <p role="alert" className="mt-5">{error} <Link href="/login" className="underline">Sign in</Link></p>}
    {status && !status.authorized && <p className="mt-5">Research is disabled or operator authorization is required.</p>}
    {status?.synthetic_available && <button disabled={busy || !!job && ["QUEUED", "RUNNING"].includes(job.status)} className="mt-6 rounded-md bg-[#253e34] px-5 py-3 text-white disabled:opacity-50" onClick={async () => {
      setBusy(true); setError("");
      try {
        const queued = await accountRequest("/research/jobs", researchJobSchema, {provider: "mock", idempotency_key: crypto.randomUUID()});
        setJob(queued); setJobs(jobs => [queued, ...jobs]);
      } catch (error) {setError(error instanceof Error ? error.message : "Research unavailable.");}
      finally {setBusy(false);}
    }}>Run Synthetic Research Analysis</button>}
    {job && <div className="mt-8 rounded-lg border border-black/10 p-5"><p>Research status: {job.status}</p>
      {score.success && <><p className="mt-4 text-2xl">Synthetic score: {score.data.display_score.toFixed(1)}</p><p>Raw score: {score.data.raw_score}</p><p>Engine: {score.data.engine} · Version: {score.data.version}</p></>}
      {job.failure_reason && <p>{job.failure_reason}</p>}
      {["QUEUED", "RUNNING"].includes(job.status) && <button className="underline mt-3" disabled={busy} onClick={async () => {
        setBusy(true); setError("");
        try {
          const cancelled = await accountRequest(`/research/jobs/${job.id}/cancel`, researchJobSchema, {});
          setJob(cancelled); setJobs(jobs => jobs.map(item => item.id === cancelled.id ? cancelled : item));
        } catch (error) {setError(error instanceof Error ? error.message : "Cancellation unavailable.");}
        finally {setBusy(false);}
      }}>Cancel research job</button>}
    </div>}
    <h2 className="mt-10 text-xl">Model availability</h2>
    <ul className="mt-4 space-y-2">{status?.providers.map(provider => <li key={provider.slug}>{provider.display_name}: {provider.available ? "Adapter available; image inference not integrated" : "Unavailable"}</li>)}</ul>
    <h2 className="mt-10 text-xl">Your research jobs</h2>
    <ul className="mt-4 space-y-3">{jobs.map(item => <li key={item.id}><button className="underline" onClick={() => setJob(item)}>{item.provider} · {item.status}</button></li>)}</ul>
  </section>;
}
