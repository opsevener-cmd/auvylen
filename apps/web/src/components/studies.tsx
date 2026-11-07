"use client";
import Link from "next/link";
import {useCallback, useEffect, useRef, useState} from "react";
import {z} from "zod";
import type {CollectionStudy, StudyAssignment, StudyExport, StudyMember, StudyPhoto} from "@auvylen/contracts";
import {useI18n} from "./i18n/provider";
import {accountRequest, csrfToken, requestError} from "@/lib/account-api";
import {sendImage, type UploadProgress} from "@/lib/upload";
import {studiesPath as base, studySchema, studyStatusSchema, studyPhotoSchema, studyAssignmentSchema, studyExportSchema} from "@/lib/studies-api";

const ok = z.record(z.string(), z.unknown());
const qualitySchema = z.array(z.object({member_id:z.string(),primary_ratings:z.number(),repeat_checks:z.number(),mean_absolute_repeat_difference:z.number().nullable(),automatic_exclusion:z.literal(false)}));
const auditSchema = z.array(z.object({action:z.string(),actor_ref:z.string(),created_at:z.string(),details:z.record(z.string(),z.unknown())}));
const auditLabels: Record<string,string> = {"study.consent_accepted":"Consent accepted","study.consent_published":"Consent version published","study.photo_submitted":"Portrait submitted","study.photo_deleted":"Portrait deleted","study.assignment":"Rating assignment created","study.rating_saved":"Rating saved","study.withdraw":"Participant withdrawal","study.governance":"Study governance action","study.member_review":"Participant verification reviewed","study.photo_review":"Portrait reviewed","study.sealed":"Holdout sealed","study.seal_invalidated":"Holdout seal invalidated"};
const statusLabels: Record<string,string> = {DRAFT:"Draft",OPEN:"Collecting",PAUSED:"Paused",CLOSED:"Closed",SEALED:"Sealed",PENDING:"Awaiting review",APPROVED:"Portrait approved",REJECTED:"Portrait rejected"};
const poseLabels: Record<string,string> = {frontal:"Front-facing",left:"Left-facing",right:"Right-facing",other:"Other pose"};
const lightingLabels: Record<string,string> = {diffuse:"Diffuse lighting",side:"Side lighting",low:"Low light",other:"Other lighting"};
const command = () => ({idempotency_key: crypto.randomUUID()});
const enConsent = "This is a voluntary private adult portrait and human-rating study. Ratings use the subjective 1–7 relative-to-average scale, not an objective judgment of a person. With separate agreement, your own authorized portrait may be viewed privately by adult research raters and used with their ratings for cloud-based non-commercial research training and private derived model weights. No public images, consumer scoring, marketing or identity inference. Some portraits repeat for consistency checks; unusual aesthetic opinions are not automatically rejected. You may skip or withdraw. Withdrawal deletes source images and ratings and revokes exports, but cannot recall already downloaded files or guarantee machine unlearning. Minimal consent, pseudonymous partition and audit evidence is retained for accountability. The study's operator must explain processors, locations, retention and a working removal contact before real collection is approved.";
const zhConsent = "这是自愿参与的私密成人肖像与人工评分研究。使用相对于平均水平的主观1–7分量表，不是对个人的客观判断。单独同意后，您本人已获授权的肖像可供成人研究评分者私密查看，并与其评分一起用于非商业云端研究训练及私密衍生模型。不公开照片，不进行消费者评分、营销或身份推断。部分肖像会重复展示以检查一致性，不会因审美观点不同而自动排除。您可以跳过或撤回。撤回会删除原始照片和评分、撤销导出，但无法远程收回已下载的文件，也不能保证模型遗忘。为问责保留最少的同意、化名分区及审计记录。正式采集获批前，负责人须说明处理方、地点、保留期限及有效的删除联系渠道。";

function StudyImage({endpoint, loaded, failed}: {endpoint: string; loaded?: () => void; failed: (error: Error) => void}) {
  const {t} = useI18n();
  const [source, setSource] = useState("");
  const failure = useRef(failed);
  useEffect(() => {failure.current = failed;}, [failed]);
  useEffect(() => {
    const abort = new AbortController(); let active = true; let url = "";
    fetch(`/api/v1${endpoint}`, {credentials: "same-origin", cache: "no-store", signal: abort.signal}).then(async response => {
      if (!response.ok) throw requestError(endpoint, response.status, await response.text());
      const blob = await response.blob();
      if (active) {url = URL.createObjectURL(blob); setSource(url);}
    }).catch(error => {if (active) failure.current(error instanceof Error ? error : new Error("Service temporarily unavailable."));});
    return () => {active = false; abort.abort(); if (url) URL.revokeObjectURL(url);};
  }, [endpoint]);
  // Authenticated blob only; never a public decorative image or external request.
  // eslint-disable-next-line @next/next/no-img-element
  return source ? <img src={source} alt={t("Private study portrait")} onLoad={loaded} className="study-portrait" /> : <p role="status">{t("Loading private portrait…")}</p>;
}

function MemberApproval({study, member, run}: {study: CollectionStudy; member: StudyMember; run: (action: () => Promise<unknown>) => Promise<void>}) {
  const {t} = useI18n();
  const [reference, setReference] = useState(member.verification_reference ?? "");
  return <div className="study-member"><p className="text-sm break-words">{t(member.role)} · <code>{member.id}</code> · {member.active ? member.approved ? t("Verified") : t("Waiting for verification") : t("Withdrawn")}</p>
    {member.active && member.role !== "custodian" && <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={e => {e.preventDefault(); void run(() => accountRequest(`${base}/${study.id}/members/${member.id}/review`, ok, {...command(), approved: true, verification_reference: reference}));}}>
      <label className="grow text-sm">{t("Opaque verification reference")}<input value={reference} onChange={e => setReference(e.target.value)} minLength={3} maxLength={80} pattern="[A-Za-z0-9][A-Za-z0-9_.-]{2,79}" required /></label>
      <button className="button-secondary">{t("Verify participation")}</button>
      {member.approved && <button className="button-secondary" type="button" onClick={() => void run(() => accountRequest(`${base}/${study.id}/members/${member.id}/review`, ok, {...command(), approved: false, verification_reference: reference}))}>{t("Suspend study eligibility")}</button>}
    </form>}
  </div>;
}

function Rater({study, failed, saved}: {study: CollectionStudy; failed: (e: unknown) => void; saved: () => void}) {
  const {t} = useI18n();
  const [assignment, setAssignment] = useState<StudyAssignment | null>(null);
  const [score, setScore] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewing = useRef("");
  const lock = useRef(false);
  useEffect(() => () => {if (timer.current) clearTimeout(timer.current);}, []);
  async function next() {
    const value = await accountRequest(`${base}/${study.id}/assignments`, studyAssignmentSchema.nullable(), command());
    setScore(null); setReady(false); viewing.current = ""; setAssignment(value);
    if (!value) setNotice("There are no eligible portraits right now. Staff may still be reviewing submissions.");
  }
  const viewed = useCallback(() => {
    if (!assignment || viewing.current === assignment.id) return;
    viewing.current = assignment.id;
    accountRequest(`${base}/${study.id}/assignments/${assignment.id}/view`, studyAssignmentSchema, command()).then(() => {
      if (viewing.current !== assignment.id) return;
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {if (viewing.current === assignment.id) setReady(true);}, 2100);
    }).catch(failed);
  }, [assignment, study.id, failed]);
  async function work(skip?: boolean) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setNotice("");
    try {
      if (assignment) {
        await accountRequest(`${base}/${study.id}/assignments/${assignment.id}/rating`, ok, {score: skip ? null : score, skip: !!skip});
        setNotice(skip ? "Portrait skipped." : "Your independent rating was saved."); saved();
      }
      await next();
    } catch (e) {failed(e); setAssignment(null); setReady(false);}
    finally {lock.current = false; setBusy(false);}
  }
  return <section className="study-panel" aria-labelledby="study-rating-heading"><h2 id="study-rating-heading">{t("Independent human rating")}</h2>
    <p className="mt-3 text-sm">{t("Rate your response to this photograph, not a person's worth. Other ratings and model predictions are hidden. You may skip; repeated portraits are quality checks, not extra independent votes.")}</p>
    {notice && <p className="mt-4" role="status">{t(notice)}</p>}
    {!assignment ? <button disabled={busy || study.status !== "OPEN"} className="button-primary mt-5" onClick={() => void work()}>{t("Get a portrait to rate")}</button> : <>
      <StudyImage key={assignment.id} endpoint={`${base}/${study.id}/assignments/${assignment.id}/content`} loaded={viewed} failed={failed} />
      <fieldset disabled={busy} className="mt-5"><legend>{t("Choose your personal rating, 1–7")}</legend><div className="study-score-grid mt-3">{[1,2,3,4,5,6,7].map(n => <label className={score === n ? "study-score selected" : "study-score"} key={n}><input type="radio" name="study-score" value={n} checked={score === n} onChange={() => setScore(n)} aria-label={t("Rating {score}", {score: n})} /><span>{n}</span></label>)}</div></fieldset>
      <p className="mt-3 text-sm">{t("1 · Much less than average · 4 · Average · 7 · Much more than average")}</p>
      {!ready && <p role="status" className="mt-3 text-sm">{t("Please view the portrait before saving. A minimum viewing time applies.")}</p>}
      <div className="mt-5 flex flex-wrap gap-3"><button className="button-primary" disabled={busy || study.status !== "OPEN" || !ready || score === null} onClick={() => void work(false)}>{t("Save rating and continue")}</button><button className="button-secondary" disabled={busy} onClick={() => void work(true)}>{t("Skip this portrait")}</button></div>
    </>}
  </section>;
}

function PortraitReviewCard({study, p, run, failed, notify}: {study: CollectionStudy; p: StudyPhoto; run: (action: () => Promise<unknown>) => Promise<void>; failed: (e: Error) => void; notify: (message: string) => void}) {
  const {t} = useI18n();
  return <article className="study-photo-card"><StudyImage endpoint={`${base}/${study.id}/photos/${p.id}/content`} failed={failed} /><p className="mt-3 text-sm">{t(statusLabels[p.review] ?? p.review)} · {t(poseLabels[p.pose] ?? p.pose)} · {t(lightingLabels[p.lighting] ?? p.lighting)} · {t("{count} independent ratings",{count:p.rating_count})}</p><div className="mt-3 flex flex-wrap gap-2">{study.can_manage && [true,false].map(approved=><button key={String(approved)} className="button-secondary" onClick={()=>void run(()=>accountRequest(`${base}/${study.id}/photos/${p.id}/review`,ok,{...command(),approved,reason:approved?"Adult consent, rights and image requirements reviewed":"Submission requires correction or removal"}))}>{approved?t("Approve portrait"):t("Reject portrait")}</button>)}<button className="button-secondary" onClick={()=>{if(confirm(t("Delete this portrait and its ratings? Existing exports will be revoked."))) void run(async()=>{const result=await accountRequest(`${base}/${study.id}/photos/${p.id}/delete`,ok,command());notify(result.cleanup_pending ? "Access revoked. Physical cleanup is queued for the worker." : "Portrait and associated ratings removed; exports revoked.");});}}>{t("Delete portrait")}</button></div></article>;
}

export function StudyWorkspace() {
  const {t, locale} = useI18n();
  const [status, setStatus] = useState<z.infer<typeof studyStatusSchema> | null>(null);
  const [studies, setStudies] = useState<CollectionStudy[]>([]);
  const [study, setStudy] = useState<CollectionStudy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [invite, setInvite] = useState("");
  const [issued, setIssued] = useState("");
  const [title, setTitle] = useState("");
  const [partition, setPartition] = useState<"development" | "holdout">("development");
  const [custodian, setCustodian] = useState("");
  const [real, setReal] = useState(false);
  const [role, setRole] = useState("contributor");
  const [confirmations, setConfirmations] = useState([false, false, false, false]);
  const [textEn, setTextEn] = useState(enConsent);
  const [textZh, setTextZh] = useState(zhConsent);
  const [contactEn, setContactEn] = useState("");
  const [contactZh, setContactZh] = useState("");
  const [rights, setRights] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pose, setPose] = useState("frontal");
  const [lighting, setLighting] = useState("diffuse");
  const [uploadConsent, setUploadConsent] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [exported, setExported] = useState<StudyExport | null>(null);
  const [quality, setQuality] = useState<z.infer<typeof qualitySchema> | null>(null);
  const [audit, setAudit] = useState<z.infer<typeof auditSchema> | null>(null);
  const [limit, setLimit] = useState(12);
  const selectedId = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const key = useRef("");
  const lock = useRef(false);
  const alert = useRef<HTMLParagraphElement | null>(null);
  const failed = useCallback((e: unknown) => setError(e instanceof Error ? e.message : "Service temporarily unavailable."), []);
  useEffect(() => {if (error) alert.current?.focus();}, [error]);
  const refresh = useCallback(async (id?: string) => {
    const list = await accountRequest(base, z.array(studySchema)); setStudies(list);
    if (id) {
      const selected = await accountRequest(`${base}/${id}`, studySchema); if (selectedId.current === id) setStudy(selected);
      const url = new URL(window.location.href); url.searchParams.set("study", id); window.history.replaceState(window.history.state, "", url);
    }
  }, []);
  useEffect(() => {
    let active = true;
    accountRequest(`${base}/status`, studyStatusSchema).then(async value => {
      if (!active) return; setStatus(value);
      {
        const list = await accountRequest(base, z.array(studySchema)); if (!active) return; setStudies(list);
        const id = new URLSearchParams(window.location.search).get("study");
        if (id && z.uuid().safeParse(id).success) {selectedId.current = id; const selected = await accountRequest(`${base}/${id}`, studySchema); if (active && selectedId.current === id) setStudy(selected);}
      }
    }).catch(e => {if (active) failed(e);});
    return () => {active = false;};
  }, [failed]);
  async function run(action: () => Promise<unknown>, detail = true) {
    if (lock.current) return; lock.current = true; setBusy(true); setError(""); setNotice("");
    try {await action(); await refresh(detail ? selectedId.current ?? undefined : undefined);}
    catch (e) {failed(e);} finally {lock.current = false; setBusy(false);}
  }
  function selected(value: CollectionStudy) {
    selectedId.current = value.id;
    setStudy(value); setError(""); setNotice(""); setIssued(""); setExported(null); setQuality(null); setAudit(null); setConfirmations([false,false,false,false]); setFile(null); setProgress(null); key.current = "";
    const url = new URL(window.location.href); url.searchParams.set("study", value.id); window.history.replaceState(window.history.state, "", url);
  }
  async function create(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => {
      const result = await accountRequest(base, z.object({id: z.uuid()}), {...command(), title, partition, custodian_public_id: custodian || null, fixture_only: !real});
      const next = await accountRequest(`${base}/${result.id}`, studySchema); selected(next); setTitle("");
    });
  }
  async function action(name: string) {
    if (!study) return;
    await run(async () => {
      const response = await accountRequest(`${base}/${study.id}/action`, z.object({value: z.string().nullable()}), {...command(), action: name, reason: "Study operator action"});
      if (name === "rotate_invite") setIssued(response.value ?? "");
      setNotice(name === "seal" ? "The holdout was sealed. Its images and labels cannot be exported for development." : "Study action saved.");
    });
  }
  async function accept(event: React.FormEvent) {
    event.preventDefault(); if (!study?.consent) return;
    await run(async () => {
      await accountRequest(`${base}/join`, ok, {invite_code: invite, role, consent_id: study.consent!.id,
        consent_sha256: study.consent!.sha256, adult_confirmed: true, voluntary: true,
        understood: true, research_permission: true, fixture_confirmed: study.fixture_only});
      setNotice("Your consent receipt is saved. Staff verification is required before upload or rating.");
    });
  }
  async function upload(event: React.FormEvent) {
    event.preventDefault(); if (!study || !file || !uploadConsent) return;
    await run(async () => {
      key.current ||= crypto.randomUUID();
      await sendImage(`${base}/${study.id}/photos`, file, {idempotency_key: key.current, self_portrait: true, adult_confirmed: true, rights_confirmed: true, fixture_confirmed: study.fixture_only, pose, lighting}, studyPhotoSchema, await csrfToken(), setProgress);
      setFile(null); if (fileInput.current) fileInput.current.value = ""; key.current = ""; setNotice("Portrait saved privately and waiting for staff review.");
    });
  }
  async function download(path: string, name: string) {
    const response = await fetch(`/api/v1${path}`, {credentials: "same-origin", cache: "no-store"});
    if (!response.ok) throw requestError(path, response.status, await response.text());
    const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const active = study?.memberships.filter(m => m.active) ?? [];
  const contributor = active.some(m => m.role === "contributor" && m.approved);
  const rater = active.some(m => m.role === "rater" && m.approved);
  return <section className="study-workspace" aria-labelledby="study-heading">
    <header className="research-heading"><p className="eyebrow">{t("Voluntary research · private by design")}</p><h1 id="study-heading">{t("Human rating studies")}</h1><p>{t("Contribute an authorized adult self-portrait or independent human ratings. Consumer scoring remains disabled; this workflow collects research evidence, not objective judgments about people.")}</p></header>
    <div className="research-notice mt-6" role="note">{t("Collection is disabled by default. Use authorized test fixtures until real collection, consent and processing arrangements have been explicitly reviewed and approved.")}</div>
    {error && <p ref={alert} tabIndex={-1} className="mt-6" role="alert">{t(error)} <Link className="underline" href="/login">{t("Sign in")}</Link></p>}
    {notice && <p className="mt-5" role="status">{t(notice)}</p>}
    {!status && !error && <p className="mt-5" role="status">{t("Checking study access…")}</p>}
    {status && !status.enabled && <p className="mt-6">{t("Research collection is disabled. No participant data can be collected.")}</p>}
    {status && <fieldset disabled={busy} className="study-controls">
      <section className="study-panel"><h2>{t("Your private studies")}</h2><p className="mt-3 text-sm">{t("1. Read the invitation and consent. 2. Obtain staff verification. 3. Submit portraits or rate independently. You can withdraw at any time.")}</p>
        <div className="mt-5 flex flex-wrap gap-3">{studies.map(item => <button className="button-secondary" key={item.id} onClick={() => selected(item)} aria-pressed={study?.id === item.id}>{item.title} · {t(statusLabels[item.status] ?? item.status)}</button>)}</div>
        {!studies.length && <p className="mt-4">{t("No study membership yet. A private invitation is required; no one is enrolled automatically.")}</p>}
        <form onSubmit={e => {e.preventDefault(); void run(async () => {const value = await accountRequest(`${base}/resolve-invite`, studySchema, {invite_code: invite}); selected(value);}, false);}} className="mt-6 study-form"><label>{t("Private invitation code")}<input value={invite} onChange={e => setInvite(e.target.value)} autoComplete="off" type="password" minLength={32} maxLength={120} required /></label><button disabled={!status.enabled} className="button-secondary">{t("Read study invitation")}</button></form>
        <p className="mt-3 text-sm wizard-note">{t("Invitation codes are not stored in URLs. Do not post them publicly or contact participants from this interface.")}</p>
      </section>
      {status.owner && status.enabled && <details className="study-panel"><summary>{t("Create an Owner-managed study")}</summary><form className="study-form mt-5" onSubmit={create}>
        <label>{t("Study title")}<input value={title} onChange={e => setTitle(e.target.value)} minLength={3} maxLength={120} required /></label>
        <label>{t("Research partition")}<select value={partition} onChange={e => setPartition(e.target.value as "development" | "holdout")}><option value="development">{t("Development data")}</option><option value="holdout">{t("Independent holdout")}</option></select></label>
        {partition === "holdout" && <label>{t("Independent custodian public account ID")}<input value={custodian} onChange={e => setCustodian(e.target.value)} placeholder="usr_…" required /></label>}
        <label className="flex gap-3"><input type="checkbox" checked={real} onChange={e => setReal(e.target.checked)} disabled={!status.real_collection_enabled} /><span>{t("Approved real collection (requires operator authorization)")}</span></label>
        <p className="text-sm">{t("Partitions and custodians cannot be changed after creation. Holdout contents are unavailable to the Owner and cannot be exported for training.")}</p><button className="button-primary">{t("Create study draft")}</button>
      </form></details>}
      {study && <section aria-labelledby="selected-study-heading"><h2 className="native-section-title" id="selected-study-heading">{study.title}</h2><button className="button-secondary mt-3" onClick={() => void refresh(study.id).catch(failed)}>{t("Refresh study status")}</button><p className="mt-3">{t(study.partition === "holdout" ? "Independent holdout" : "Development data")} · {t(statusLabels[study.status] ?? study.status)} · {study.fixture_only ? t("Authorized fixtures only") : t("Approved real collection")} · {t("Retention: {days} days", {days: study.retention_days})}</p><p className="text-sm mt-2">{t("{photos} portraits · {ratings} primary human ratings", {photos: study.photo_count, ratings: study.rating_count})}</p>
        {study.can_administer && status.enabled && <section className="study-panel"><h3>{t("Study governance")}</h3><p className="mt-3 text-sm">{t("Publish bilingual consent, create a private invitation, then open collection. A holdout custodian must acknowledge consent first. Closing cancels pending assignments; reopening revokes old exports.")}</p>
          <div className="mt-5 flex flex-wrap gap-3">{["rotate_invite","open","pause","close"].map(name => <button className="button-secondary" key={name} onClick={() => void action(name)}>{t({rotate_invite:"Create or rotate invitation",open:"Open collection",pause:"Pause collection",close:"Close collection"}[name]!)}</button>)}</div>
          {issued && <div role="status" className="mt-5"><p>{t("Copy this code now. It is shown once and never written to the audit log.")}</p><code className="break-all">{issued}</code><button className="button-secondary mt-3" onClick={() => {setInvite(issued); setNotice("Invitation selected for this session.");}}>{t("Use this invitation in this session")}</button><button className="button-secondary mt-3" onClick={() => setIssued("")}>{t("Hide private invitation")}</button></div>}
          <details className="mt-6"><summary>{t("Publish a new consent version")}</summary><p className="mt-3 text-sm">{t("The sample is a starting point, not legal approval. State purpose, processors and locations, permissions for portraits, annotations and research weights, risks, removal contact, retention and limits of deleting derived models. New versions pause collection and require fresh consent for new work.")}</p><form className="study-form mt-4" onSubmit={e => {e.preventDefault(); void run(() => accountRequest(`${base}/${study.id}/consent`, ok, {...command(),text_en:textEn,text_zh:textZh,contact_en:contactEn,contact_zh:contactZh,rights_reference:rights}));}}>
            <label>{t("Consent text · English")}<textarea rows={8} value={textEn} onChange={e => setTextEn(e.target.value)} minLength={100} maxLength={12000} required /></label><label>{t("Consent text · 简体中文")}<textarea rows={8} value={textZh} onChange={e => setTextZh(e.target.value)} minLength={50} maxLength={12000} required /></label>
            <label>{t("Removal contact and operator · English")}<input value={contactEn} onChange={e => setContactEn(e.target.value)} minLength={3} maxLength={300} required /></label><label>{t("Removal contact and operator · 简体中文")}<input value={contactZh} onChange={e => setContactZh(e.target.value)} minLength={3} maxLength={300} required /></label><label>{t("Rights review reference")}<input value={rights} onChange={e => setRights(e.target.value)} minLength={3} maxLength={200} required /></label><button className="button-primary">{t("Publish immutable consent version")}</button>
          </form></details>
        </section>}
        {study.consent && <details className="study-panel" open={study.memberships.length === 0}><summary>{t("Read the exact consent version")}: {study.consent.version}</summary><p className="mt-3 whitespace-pre-wrap">{locale === "zh-CN" ? study.consent.text_zh : study.consent.text_en}</p><p className="mt-4 text-sm">{locale === "zh-CN" ? study.consent.contact_zh : study.consent.contact_en}</p><p className="mt-3 text-xs font-mono break-all">SHA-256 {study.consent.sha256}</p>
          <p className="mt-4 text-sm">{t("Your account stays in one research partition, including after withdrawal. Minimal consent, audit and partition records remain; images and ratings are removed on withdrawal. Previously downloaded copies cannot be recalled.")}</p>
          {!study.memberships.some(m => !m.active) && study.status !== "CLOSED" && study.status !== "SEALED" && <form className="study-form mt-5" onSubmit={accept}><label>{t("Participation role")}<select value={role} onChange={e => setRole(e.target.value)}><option value="contributor">{t("contributor")}</option><option value="rater">{t("rater")}</option><option value="custodian">{t("custodian")}</option></select></label>
            {["I confirm I am an adult (18+).","I read and understood this version and am participating voluntarily.","I authorize the described private research processing, human ratings and research-derived weights, without commercial or public-display permission.","I confirm this is an authorized test-fixture workflow, not real participant collection."].slice(0, study.fixture_only ? 4 : 3).map((label,index) => <label className="flex items-start gap-3" key={label}><input type="checkbox" checked={confirmations[index]} onChange={e => setConfirmations(value => value.map((old,i) => i === index ? e.target.checked : old))} /><span>{t(label)}</span></label>)}
            <button className="button-primary" disabled={!status.enabled || !invite || !confirmations.slice(0, study.fixture_only ? 4 : 3).every(Boolean)}>{t("Accept this consent version")}</button>
          </form>}
        </details>}
        {study.memberships.length > 0 && <section className="study-panel"><h3>{t("Your participation and removal controls")}</h3>{study.memberships.map(m => <p className="mt-3 break-all" key={m.id}>{t(m.role)} · {m.active ? m.approved ? t("Verified") : t("Waiting for verification") : t("Withdrawn")} · {t("Receipt code")}: <code>{m.id}</code></p>)}<div className="mt-5 flex flex-wrap gap-3"><button className="button-secondary" onClick={() => void run(async () => {const result = await accountRequest(`${base}/${study.id}/receipts`, z.array(z.unknown())); const a = document.createElement("a"); const url = URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"})); a.href=url;a.download="study-consent-receipts.json";a.click();setTimeout(() => URL.revokeObjectURL(url),1000);})}>{t("Download my consent receipts")}</button><button className="button-secondary" onClick={() => {if (confirm(t("Withdraw from this study and delete your portraits and ratings? Exports will be revoked. Your account and Credits remain unchanged."))) void run(async () => {const result = await accountRequest(`${base}/${study.id}/withdraw`,ok,command()); setInvite(""); setIssued(""); setNotice(result.cleanup_pending ? "Participation withdrawn and access revoked. Physical cleanup is queued for the worker; contact the operator if it does not finish." : "Participation withdrawn. Your portraits and ratings were removed and exports revoked.");});}}>{t("Withdraw and delete my study data")}</button></div></section>}
        {status.enabled && contributor && <form className="study-panel study-form" onSubmit={upload}><h3>{t("Submit your authorized adult portrait")}</h3><p className="text-sm">{t("JPEG or PNG, up to 4 MiB and 4096 pixels. The stored derivative removes metadata. Staff check consent and technical quality before raters can see it.")}</p><label>{t("Your own adult portrait")}<input ref={fileInput} type="file" accept="image/jpeg,image/png" disabled={study.status !== "OPEN"} onChange={e => {setFile(e.target.files?.[0] ?? null);key.current="";setProgress(null);}} /></label>
          <label>{t("Capture pose")}<select value={pose} onChange={e=>setPose(e.target.value)}>{["frontal","left","right","other"].map(v=><option key={v} value={v}>{t(poseLabels[v])}</option>)}</select></label><label>{t("Capture lighting")}<select value={lighting} onChange={e=>setLighting(e.target.value)}>{["diffuse","side","low","other"].map(v=><option key={v} value={v}>{t(lightingLabels[v])}</option>)}</select></label><label className="flex gap-3"><input type="checkbox" checked={uploadConsent} onChange={e=>setUploadConsent(e.target.checked)} /><span>{t("This is my own adult portrait, or an authorized generated test fixture in a fixture study. I hold the necessary photograph rights.")}</span></label><button className="button-primary" disabled={!file || !uploadConsent || study.status !== "OPEN"}>{t("Upload portrait for review")}</button>
          {progress && <p role="status">{progress.stage === "uploading" ? progress.percent === undefined ? t("Uploading image…") : t("Uploading {percent}%",{percent:progress.percent}) : progress.stage === "saved" ? t("Portrait saved privately and waiting for staff review.") : t("Processing image")}</p>}
        </form>}
        {status.enabled && rater && <Rater key={study.id} study={study} failed={failed} saved={() => setNotice("Your independent rating was saved.")} />}
        {status.enabled && (study.can_manage || study.photos.length > 0) && <section className="study-panel"><h3>{t("Private portrait review")}</h3><p className="mt-3 text-sm">{t("Approval requires verified adult consent and source rights; do not infer age from appearance. Reject or remove unsuitable submissions without assigning an aesthetic score.")}</p><div className="study-photo-grid mt-5">{study.photos.slice(0,limit).map(p=><PortraitReviewCard key={p.id} study={study} p={p} run={run} failed={failed} notify={setNotice}/>)}</div>{study.photos.length>limit&&<button className="button-secondary mt-5" onClick={()=>setLimit(v=>v+12)}>{t("Show more portraits")}</button>}</section>}
        {status.enabled && study.can_manage && <section className="study-panel"><h3>{t("Participant verification and quality review")}</h3><p className="mt-3 text-sm">{t("Participants present their receipt code. Verify adulthood, consent, independence and portrait ownership using the approved process. Enter an opaque proof reference, never a name, email or identity document. Reuse the same reference for the same person across studies. Unusual ratings are not automatic grounds for exclusion.")}</p>{study.members.map(m=><MemberApproval key={m.id} study={study} member={m} run={run}/>)}<div className="mt-5 flex flex-wrap gap-3"><button className="button-secondary" onClick={()=>void run(async()=>setQuality(await accountRequest(`${base}/${study.id}/quality`,qualitySchema)))}>{t("Review repeat-check quality")}</button><button className="button-secondary" onClick={()=>void run(async()=>setAudit(await accountRequest(`${base}/${study.id}/audit`,auditSchema)))}>{t("Review study audit")}</button>{study.partition==="holdout"&&<button className="button-secondary" onClick={()=>void action("seal")}>{t("Seal closed holdout")}</button>}</div>{quality&&<div className="mt-5 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>{t("Receipt code")}</th><th>{t("Primary ratings")}</th><th>{t("Repeat checks")}</th><th>{t("Mean repeat difference")}</th></tr></thead><tbody>{quality.map(row=><tr key={row.member_id}><td className="max-w-32 break-all">{row.member_id}</td><td>{row.primary_ratings}</td><td>{row.repeat_checks}</td><td>{row.mean_absolute_repeat_difference===null?t("Not enough repeat checks"):row.mean_absolute_repeat_difference.toFixed(2)}</td></tr>)}</tbody></table><p className="mt-3">{t("Quality signals require manual review. They do not automatically exclude unusual preferences.")}</p></div>}{audit&&<div className="mt-5 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>{t("Time")}</th><th>{t("Study action")}</th><th>{t("Pseudonymous actor")}</th></tr></thead><tbody>{audit.map((row,index)=><tr key={index}><td>{new Date(row.created_at).toLocaleString(locale)}</td><td>{t(auditLabels[row.action]??row.action)}</td><td><code>{row.actor_ref.slice(0,12)}</code></td></tr>)}</tbody></table></div>}</section>}
        {study.seal_sha256&&<div className="study-panel"><h3>{t("Frozen holdout commitment")}</h3><p className="mt-3 font-mono break-all text-xs">{study.seal_sha256}</p><p className="mt-3 text-sm">{t("No holdout labels or portraits are available to development exports. Withdrawal invalidates this seal; it cannot silently define a replacement test set.")}</p></div>}
        {status.enabled&&study.can_administer&&study.partition==="development"&&<section className="study-panel"><h3>{t("Secure development export")}</h3><p className="mt-3 text-sm">{t("Close collection first. Only approved portraits with at least three independently verified primary ratings are included. Consistency repeats are excluded. Exports expire after 24 hours and are revoked by withdrawal or changed eligibility. Validate live status immediately before every training use; already downloaded files cannot be recalled.")}</p><button className="button-primary mt-5" disabled={study.status!=="CLOSED"} onClick={()=>void run(async()=>setExported(await accountRequest(`${base}/${study.id}/exports`,studyExportSchema,command())))}>{t("Create private development export")}</button>{exported&&<div className="mt-4"><p>{t("{images} images · {subjects} subjects",{images:exported.images,subjects:exported.subjects})}</p><code className="block break-all text-xs mt-2">{exported.sha256}</code><button className="button-secondary mt-4" onClick={()=>void run(()=>download(`${base}/${study.id}/exports/${exported.id}/content`,`auvylen-development-${exported.id}.zip`))}>{t("Download verified private archive")}</button></div>}</section>}
      </section>}
    </fieldset>}
  </section>;
}
