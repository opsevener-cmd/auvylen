"use client";
import {useI18n} from "@/components/i18n/provider";

import Link from "next/link";
import {PhotoUpload, consentText} from "@/components/photo-upload";
import {PersonalModels} from "@/components/personal-models";
import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {z} from "zod";
import type {PreferenceDataset, PreferenceDetail, PreferenceImage, PreferencePair, PreferenceProject, TrainingReadiness} from "@auvylen/contracts";
import {accountRequest} from "@/lib/account-api";
import {datasetSchema, detailSchema, imageSchema, imageUrl, nextPair, pairSchema, preferencePath as base, projectSchema, readinessSchema} from "@/lib/preferences-api";
import {annotationImages, firstPending, nextPending, ratingSummary, reachableStep, readSelection, resolveSelection, resumeStep, selectionQuery, steps, type Step} from "@/lib/workflow";

const button = "rounded border border-black/20 px-3 py-2 disabled:opacity-40";
const field = "block w-full rounded border border-black/20 p-2 mt-1 mb-3";
type Perform = (action: () => Promise<void>) => Promise<void>;

/** Four sequential steps. Only the active step renders; progress is re-derived from server data. */
export function PreferencesPage() {
  const {t} = useI18n();
  const [projects, setProjects] = useState<PreferenceProject[]>([]);
  const [datasets, setDatasets] = useState<PreferenceDataset[]>([]);
  const [project, setProject] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [detail, setDetail] = useState<PreferenceDetail | null>(null);
  const [step, setStep] = useState<Step>(1);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const moved = useRef(false);
  const dataset = datasets.find(item => item.id === datasetId);
  const images = detail?.dataset.id === datasetId ? detail.images : null;
  const reachable = reachableStep(project, dataset, images);

  const loadDetail = useCallback(async (id: string) => {
    const loadedDetail = await accountRequest(`${base}/datasets/${id}`, detailSchema);
    setDetail(loadedDetail);
    setDatasets(current => current.map(item => item.id === id ? loadedDetail.dataset : item));
    return loadedDetail;
  }, []);
  const refresh = useCallback(async () => {
    const [p, d] = await Promise.all([accountRequest(`${base}/projects`, z.array(projectSchema)), accountRequest(`${base}/datasets`, z.array(datasetSchema))]);
    setProjects(p); setDatasets(d);
    return {p, d};
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      const {p, d} = await refresh();
      const saved = readSelection(window.location.search);
      const chosen = resolveSelection(saved, p, d);
      const loadedDetail = chosen.dataset ? await accountRequest(`${base}/datasets/${chosen.dataset}`, detailSchema) : null;
      if (!active) return;
      setProject(chosen.project); setDatasetId(chosen.dataset); setDetail(loadedDetail);
      setStep(resumeStep(chosen.project, d.find(item => item.id === chosen.dataset), loadedDetail?.images ?? null, saved.step));
      setLoaded(true);
    })().catch(e => {if (active) {setError(e instanceof Error ? e.message : "Research unavailable."); setLoaded(true);}});
    return () => {active = false;};
  }, [refresh]);

  // Remember choices in the URL so refresh and back/forward restore the same place.
  useEffect(() => {
    if (!loaded) return;
    const query = selectionQuery({project, dataset: datasetId, step});
    if (window.location.search !== query) window.history.replaceState(null, "", `${window.location.pathname}${query}`);
  }, [loaded, project, datasetId, step]);
  useEffect(() => {if (moved.current) heading.current?.focus(); moved.current = false;}, [step]);

  function go(target: Step) {
    if (target > reachable || uploading) return;
    moved.current = true; setError(""); setStep(target);
  }
  const perform: Perform = async action => {
    setBusy(true); setError("");
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : "Request failed.");}
    finally {setBusy(false);}
  };
  async function chooseProject(id: string) {
    setProject(id);
    const newest = [...datasets].filter(item => item.project_id === id).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
    setDatasetId(newest?.id ?? ""); setDetail(null);
    if (newest) await loadDetail(newest.id);
  }
  async function chooseDataset(id: string) {setDatasetId(id); setDetail(null); await loadDetail(id);}

  const title = steps[step - 1].label;
  const nextAllowed = step < 4 && step + 1 <= reachable;
  return <section className="research-wizard max-w-4xl">
    <Link className="underline" href="/research">{t("Research workspace")}</Link>
    <header className="research-heading mt-4"><p className="eyebrow">{t("Your private research studio")}</p><h1>{t("Personal preference datasets")}</h1><p>{t("Create a project, collect authorized photographs and explore patterns in your own ratings.")}</p></header>
    <nav aria-label={t("Research steps")} className="wizard-steps"><ol>{steps.map(item => {
      const done = item.step < reachable || (item.step === 4 && !!images && ratingSummary(images).awaiting === 0 && ratingSummary(images).total > 0);
      const status = item.step === step ? t("current step") : done ? t("completed") : item.step <= reachable ? t("available") : t("locked");
      return <li key={item.step} className={item.step === step ? "is-current" : done ? "is-done" : ""}>
        <button type="button" disabled={item.step > reachable || uploading} aria-current={item.step === step ? "step" : undefined} onClick={() => go(item.step)} aria-label={t("Step {number}: {label} ({status})", {number: item.step, label: t(item.label), status})}>
          <span className="wizard-number" aria-hidden="true">{done && item.step !== step ? "✓" : item.step}</span><span className="wizard-label">{t(item.label)}</span>
        </button></li>;
    })}</ol></nav>
    {error && <p role="alert" className="mt-6">{t(error)} <Link className="underline" href="/login">{t("Sign in")}</Link></p>}
    {!loaded ? <p className="mt-10" role="status">{t("Loading your saved research…")}</p> : <div className="wizard-panel">
      <p className="wizard-kicker">{t("Step {number} of 4", {number: step})}</p>
      <h2 ref={heading} tabIndex={-1} className="wizard-title">{t(title)}</h2>
      <fieldset disabled={busy} className="mt-6 space-y-6">
        {step === 1 && <ProjectStep projects={projects} datasets={datasets} project={project} perform={perform} onChoose={id => perform(() => chooseProject(id))} onCreated={async created => {await refresh(); setProject(created.id); setDatasetId(""); setDetail(null); moved.current = true; setStep(2);}} />}
        {step === 2 && <DatasetStep project={projects.find(item => item.id === project)} datasets={datasets.filter(item => item.project_id === project)} selected={dataset} perform={perform}
          onChoose={id => perform(() => chooseDataset(id))}
          onCreated={async created => {await refresh(); setDatasetId(created.id); await loadDetail(created.id); moved.current = true; setStep(3);}}
          onChanged={async () => {await refresh(); if (datasetId) await loadDetail(datasetId);}}
          onDeleted={async () => {setDatasetId(""); setDetail(null); await refresh();}} />}
        {step === 3 && dataset && <UploadStep dataset={dataset} images={images ?? []} onBusy={active => {setUploading(active);}} onSaved={image => setDetail(current => current && !current.images.some(item => item.id === image.id) ? {...current, images: [...current.images, image], dataset: {...current.dataset, image_count: current.dataset.image_count + 1}} : current)} onComplete={async () => {await loadDetail(dataset.id);}} onContinue={() => go(4)} onManage={() => go(2)} />}
        {step === 4 && detail && dataset && <RateStep key={dataset.id} detail={detail} onDetail={updated => {setDetail(updated); setDatasets(current => current.map(item => item.id === updated.dataset.id ? updated.dataset : item));}} reload={() => loadDetail(dataset.id).then(() => undefined)} onUpload={() => go(3)} onBusy={setUploading} />}
      </fieldset>
      <div className="wizard-footer">
        <button type="button" className="button-secondary" disabled={step === 1 || uploading} onClick={() => go((step - 1) as Step)}>{t("Previous")}</button>
        {step < 4 && <button type="button" className="button-primary" disabled={!nextAllowed || uploading} aria-describedby="wizard-next-hint" onClick={() => go((step + 1) as Step)}>{t("Next")}</button>}
        {step < 4 && !nextAllowed && <p id="wizard-next-hint" className="wizard-hint">{t(step === 1 ? "Choose or create a project to continue." : step === 2 ? "Choose or create a dataset to continue." : "Upload at least one photograph to continue.")}</p>}
      </div>
    </div>}
    <p className="mt-10 text-sm wizard-note">{t("Your ratings describe your subjective preferences. Research does not spend Credits. Only upload authorized adult photographs.")} {t("Private images expire after the selected retention period. Deletion blocks access immediately; the research worker removes stored files.")}</p>
  </section>;
}

function ProjectStep({projects, datasets, project, perform, onChoose, onCreated}: {projects: PreferenceProject[]; datasets: PreferenceDataset[]; project: string; perform: Perform; onChoose: (id: string) => void; onCreated: (created: PreferenceProject) => Promise<void>}) {
  const {t} = useI18n();
  return <>
    <p>{t("A project groups datasets around one research question, for example portraits you find calm or striking.")}</p>
    {projects.length > 0 && <fieldset className="choice-list"><legend>{t("Your projects")}</legend>
      {projects.map(item => <label key={item.id} className="choice"><input type="radio" name="project" checked={item.id === project} onChange={() => onChoose(item.id)} /><span><strong>{item.name}</strong><small>{t("{count} datasets", {count: datasets.filter(d => d.project_id === item.id).length})}</small></span></label>)}
    </fieldset>}
    <form className="workspace-panel" onSubmit={event => {event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); void perform(async () => {
      const created = await accountRequest(`${base}/projects`, projectSchema, {name: values.get("name")});
      form.reset(); await onCreated(created);
    });}}>
      <h3 className="text-xl">{t(projects.length ? "Or create a new project" : "Name your first project")}</h3>
      <label className="mt-3 block">{t("Project name")}<input name="name" required maxLength={120} className={field} /></label>
      <button className="button-primary">{t("Create project")}</button>
    </form>
  </>;
}

function DatasetStep({project, datasets, selected, perform, onChoose, onCreated, onChanged, onDeleted}: {project?: PreferenceProject; datasets: PreferenceDataset[]; selected?: PreferenceDataset; perform: Perform; onChoose: (id: string) => void; onCreated: (created: PreferenceDataset) => Promise<void>; onChanged: () => Promise<void>; onDeleted: () => Promise<void>}) {
  const {t, locale} = useI18n();
  return <>
    <p>{t("Project:")} <strong>{project?.name}</strong>. {t("A dataset groups photographs with a common source and rating scale. Set a retention period you can justify; expiry blocks access and schedules file removal.")}</p>
    {datasets.length > 0 && <fieldset className="choice-list"><legend>{t("Datasets in this project")}</legend>
      {datasets.map(item => <label key={item.id} className="choice"><input type="radio" name="dataset" checked={item.id === selected?.id} onChange={() => onChoose(item.id)} /><span><strong>{item.name}{item.archived ? t(" (archived)") : ""}</strong><small>{item.image_count} {t("images ·")} {item.rated_count} {t("rated")}</small></span></label>)}
    </fieldset>}
    {selected && <details className="workspace-panel"><summary>{t("Manage “{name}”", {name: selected.name})}</summary>
      <p className="mt-3 text-sm">{t("Expires:")} {new Date(selected.expires_at).toLocaleDateString(locale)} {t("· Source:")} {selected.source} {t("· License:")} {selected.license}</p>
      <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
        await accountRequest(`${base}/datasets/${selected.id}/edit`, datasetSchema, {name: values.get("name"), archived: selected.archived}); await onChanged();
      });}}>
        <label className="grow">{t("Rename dataset")}<input name="name" defaultValue={selected.name} maxLength={120} required className={field} /></label>
        <button className={`${button} mb-3`}>{t("Rename")}</button>
      </form>
      <div className="flex flex-wrap gap-3">
        <button type="button" className={button} onClick={() => void perform(async () => {await accountRequest(`${base}/datasets/${selected.id}/edit`, datasetSchema, {name: selected.name, archived: !selected.archived}); await onChanged();})}>{selected.archived ? t("Restore dataset") : t("Archive dataset")}</button>
        <button type="button" className={button} onClick={() => {if (window.confirm(t("Delete this dataset, its images and all annotations?"))) void perform(async () => {await accountRequest(`${base}/datasets/${selected.id}/delete`, z.object({deleted: z.boolean()}), {}); await onDeleted();});}}>{t("Delete dataset")}</button>
      </div>
      <p className="mt-3 text-sm">{t("Archive keeps saved images and annotations until expiry and pauses editing. Delete blocks access and removes images, annotations and derived model checkpoints.")}</p>
    </details>}
    <details className="workspace-panel" open={datasets.length === 0}><summary>{t("Create a dataset")}</summary>
      <form className="mt-4" onSubmit={event => {event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); void perform(async () => {
        const created = await accountRequest(`${base}/datasets`, datasetSchema, {project_id: project?.id, name: values.get("name"), source: values.get("source"), source_url: values.get("source_url"), license: values.get("license"), adult_authorized_consent: values.get("consent") === "on", retention_days: Number(values.get("retention")), rating_min: Number(values.get("min")), rating_max: Number(values.get("max"))});
        form.reset(); await onCreated(created);
      });}}>
        <label>{t("Dataset name")}<input name="name" required maxLength={120} className={field} /></label>
        <label>{t("Source")}<input name="source" required maxLength={500} className={field} /></label>
        <label>{t("Source URL (optional)")}<input name="source_url" type="url" maxLength={500} className={field} /></label>
        <label>{t("License and restrictions")}<input name="license" required maxLength={500} className={field} /></label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label>{t("Retention days")}<input name="retention" type="number" min={1} max={90} defaultValue={30} required className={field} /></label>
          <label>{t("Minimum rating")}<input name="min" type="number" min={0} max={99} defaultValue={1} required className={field} /></label>
          <label>{t("Maximum rating")}<input name="max" type="number" min={1} max={100} defaultValue={10} required className={field} /></label>
        </div>
        <label className="block mb-4"><input name="consent" type="checkbox" required /> {t(consentText)}</label>
        <button className="button-primary">{t("Save dataset")}</button>
      </form>
    </details>
  </>;
}

function UploadStep({dataset, images, onBusy, onSaved, onComplete, onContinue, onManage}: {dataset: PreferenceDataset; images: PreferenceImage[]; onBusy: (active: boolean) => void; onSaved: (image: PreferenceImage) => void; onComplete: () => Promise<void>; onContinue: () => void; onManage: () => void}) {
  const {t} = useI18n();
  const annotation = annotationImages(images);
  const summary = ratingSummary(images);
  return <>
    <p>{t("Dataset:")} <strong>{dataset.name}</strong> · {t("{count} photographs saved · {awaiting} awaiting rating", {count: annotation.length, awaiting: summary.awaiting})}</p>
    {dataset.archived ? <p role="status">{t("This dataset is archived. Restore it before uploading.")} <button type="button" className="underline" onClick={onManage}>{t("Manage dataset")}</button></p>
      : <PhotoUpload path={`${base}/datasets/${dataset.id}`} onSaved={onSaved} onComplete={onComplete} onBusy={onBusy} />}
    {annotation.length > 0 && <div className="thumbnail-grid" aria-label={t("Saved photographs")}>{annotation.map(image => <PrivatePhoto key={image.id} image={image} thumbnail />)}</div>}
    {summary.awaiting > 0 && <div className="wizard-callout"><p>{t("{count} photographs are ready to rate.", {count: summary.awaiting})}</p><button type="button" className="button-primary" onClick={onContinue}>{t("Continue to rating")}</button></div>}
  </>;
}

function RateStep({detail, onDetail, reload, onUpload, onBusy}: {detail: PreferenceDetail; onDetail: (detail: PreferenceDetail) => void; reload: () => Promise<void>; onUpload: () => void; onBusy: (active: boolean) => void}) {
  const {t} = useI18n();
  const {dataset, pairs} = detail;
  const images = useMemo(() => annotationImages(detail.images), [detail.images]);
  const summary = ratingSummary(detail.images);
  const [index, setIndex] = useState(() => Math.max(0, firstPending(images)));
  const [reviewing, setReviewing] = useState(false);
  const [mode, setMode] = useState<"rating" | "pairs">("rating");
  const [reviewPair, setReviewPair] = useState<PreferencePair | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [readiness, setReadiness] = useState<TrainingReadiness | null>(null);
  const [config, setConfig] = useState({seed: 42, fraction: 0.2});
  const path = `${base}/datasets/${dataset.id}`;
  const complete = summary.total > 0 && summary.awaiting === 0 && !reviewing;
  const selected = images[Math.min(index, images.length - 1)];
  const next = useMemo(() => reviewPair ? [images.find(i => i.id === reviewPair.left_id), images.find(i => i.id === reviewPair.right_id)] : nextPair(images, pairs), [images, pairs, reviewPair]);
  const pair = next?.[0] && next?.[1] ? [next[0], next[1]] : null;
  const [revision, setRevision] = useState(0);
  // Ask the server only when eligibility can have changed: below eight valid ratings it cannot
  // become eligible, so ordinary saves stay at two requests (CSRF + save).
  const phase = complete ? `complete:${summary.valid}` : summary.valid >= 8 ? `valid:${summary.valid}` : "collecting";
  useEffect(() => {
    let active = true;
    accountRequest(`${path}/readiness?seed=${config.seed}&validation_fraction=${config.fraction}`, readinessSchema)
      .then(value => {if (active) setReadiness(value);})
      .catch(e => {if (active) setError(e instanceof Error ? e.message : "Eligibility check failed.");});
    return () => {active = false;};
  }, [path, config.seed, config.fraction, phase, revision]);
  function store(image: PreferenceImage) {
    const updated = detail.images.map(item => item.id === image.id ? image : item);
    onDetail({...detail, images: updated, dataset: {...dataset, rated_count: annotationImages(updated).filter(item => item.rating_recorded && item.score !== null).length}});
    return annotationImages(updated);
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : "Request failed.");}
    finally {setBusy(false);}
  }
  function advance(updated: PreferenceImage[], from: number) {
    const following = nextPending(updated, from);
    if (following === -1) {setReviewing(false); setIndex(from);} else setIndex(following);
  }
  async function rate(score: number | null) {
    // A failed save keeps the user on the same photograph with their entry intact.
    const saved = await accountRequest(`${path}/images/${selected.id}/rating`, imageSchema, {score});
    const updated = store(saved);
    setMessage(score === null ? "Photograph skipped." : "Rating saved.");
    advance(updated, index);
  }
  function review(position: number) {setIndex(position); setReviewing(true); setMode("rating"); setMessage("");}

  return <>
    <p className="rating-progress">{t("{valid} valid ratings · {skipped} skipped · {excluded} excluded · {awaiting} awaiting rating", summary)}</p>
    <progress max={Math.max(summary.total, 1)} value={summary.total - summary.awaiting} aria-label={t("Photographs processed")} />
    {error && <p role="alert">{t(error)}</p>}{message && <p role="status">{t(message)}</p>}
    <div className="annotation-toolbar"><button type="button" className={button} aria-pressed={mode === "rating"} onClick={() => setMode("rating")}>{t("Rate photographs")}</button><button type="button" className={button} aria-pressed={mode === "pairs"} onClick={() => setMode("pairs")}>{t("Compare pairs")}</button></div>
    <fieldset disabled={busy} className="space-y-5">
      {mode === "rating" && complete && <Completion summary={summary} readiness={readiness} onReviewSkipped={() => {const skipped = images.findIndex(i => !i.excluded && i.rating_recorded && i.score === null); if (skipped >= 0) review(skipped);}} onUpload={onUpload} />}
      {mode === "rating" && !complete && selected && <>
        <p>{t("Image")} {index + 1} {t("of")} {images.length}{selected.excluded ? t(" · Excluded") : ""}{reviewing && summary.awaiting === 0 ? ` · ${t("Revising a saved rating")}` : ""}</p>
        <PrivatePhoto image={selected} />
        <form key={`${selected.id}-${selected.score}`} onSubmit={event => {event.preventDefault(); const score = Number(new FormData(event.currentTarget).get("score")); void perform(() => rate(score));}}>
          <label>{t("Your rating (")}{dataset.rating_min}–{dataset.rating_max})<input name="score" type="number" min={dataset.rating_min} max={dataset.rating_max} step="0.1" defaultValue={selected.score ?? ""} required disabled={selected.excluded || dataset.archived} className={field} /></label>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={button} disabled={index === 0} onClick={() => review(index - 1)}>{t("Previous photograph")}</button>
            <button className="button-primary" disabled={selected.excluded || dataset.archived}>{t(summary.awaiting === 0 || (summary.awaiting === 1 && !selected.rating_recorded && !selected.excluded) ? "Save rating" : "Save and next")}</button>
            <button type="button" className={button} disabled={selected.excluded || dataset.archived} onClick={() => void perform(() => rate(null))}>{t("Skip rating")}</button>
            <button type="button" className={button} disabled={index >= images.length - 1} onClick={() => review(index + 1)}>{t("Next photograph")}</button>
            {reviewing && summary.awaiting === 0 && <button type="button" className={button} onClick={() => setReviewing(false)}>{t("Back to summary")}</button>}
          </div>
        </form>
        <details className="workspace-panel"><summary>{t("Photograph settings")}</summary>
          <form key={selected.id} className="mt-3" onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
            await accountRequest(`${path}/images/${selected.id}/edit`, imageSchema, {subject_group: String(values.get("group") || "").trim() || null, excluded: values.get("excluded") === "on"}); await reload(); setRevision(value => value + 1);
          });}}>
            <label>{t("Image person/group identifier")}<input name="group" maxLength={120} defaultValue={selected.subject_group ?? ""} className={field} /></label>
            <label><input name="excluded" type="checkbox" defaultChecked={selected.excluded} /> {t("Exclude from annotation and future training")}</label>
            <button className={`${button} ml-3`}>{t("Save image settings")}</button>
          </form>
          <button type="button" className={`${button} mt-3`} onClick={() => {if (window.confirm(t("Delete this image and its annotations?"))) void perform(async () => {await accountRequest(`${path}/images/${selected.id}/delete`, z.object({deleted: z.boolean()}), {}); setIndex(0); setReviewing(false); await reload(); setRevision(value => value + 1);});}}>{t("Delete image")}</button>
        </details>
      </>}
      {mode === "pairs" && <>
        {pair ? <><div className="grid grid-cols-2 gap-3"><div><p>{t("Left")}</p><PrivatePhoto image={pair[0]} /></div><div><p>{t("Right")}</p><PrivatePhoto image={pair[1]} /></div></div>
          {reviewPair && <p>{t("Editing saved comparison:")} {t(reviewPair.choice)}</p>}
          <div className="flex flex-wrap gap-2">{(["left", "right", "equal", "skip"] as const).map(choice => <button type="button" key={choice} className={button} onClick={() => void perform(async () => {const saved = await accountRequest(`${path}/pairs`, pairSchema, {left_id: pair[0].id, right_id: pair[1].id, choice}); const updated = [...pairs.filter(item => item.id !== saved.id), saved]; onDetail({...detail, pairs: updated, dataset: {...dataset, compared_count: updated.length}}); setReviewPair(null); setMessage("Comparison saved.");})}>{t(({left: "Left preferred", right: "Right preferred", equal: "Equal preference", skip: "Skip pair"})[choice])}</button>)}</div>
        </> : <p>{t("No unseen pairs remain. Upload more images or edit a saved comparison below.")}</p>}
        <details><summary>{t("Review saved comparisons (")}{pairs.length})</summary><ul>{pairs.map((item, position) => <li key={item.id}><button type="button" className="underline" onClick={() => setReviewPair(item)}>{t("Comparison")} {position + 1}: {t(item.choice)}</button></li>)}</ul></details>
      </>}
      <div className="thumbnail-grid">{images.map((image, position) => <button type="button" key={image.id} aria-pressed={!complete && mode === "rating" && index === position} className="rounded border p-1" aria-label={t("Select image {value0}", {value0: position + 1})} onClick={() => review(position)}><PrivatePhoto image={image} thumbnail /><span>{image.excluded ? t("Excluded") : image.score ?? (image.rating_recorded ? t("Skipped") : t("Unrated"))}</span></button>)}</div>
    </fieldset>
    <PersonalModels dataset={dataset} images={detail.images} readiness={readiness} valid={summary.valid} prominent={complete && !!readiness?.eligible} config={config} onConfig={setConfig} onBusy={onBusy}
      onPredictionUpload={image => {if (!detail.images.some(item => item.id === image.id)) onDetail({...detail, images: [...detail.images, image], dataset: {...dataset, image_count: dataset.image_count + 1}});}}
      onPredictionDeleted={id => onDetail({...detail, images: detail.images.filter(item => item.id !== id), dataset: {...dataset, image_count: Math.max(0, dataset.image_count - 1)}})} />
  </>;
}

const reasonText: Record<string, string> = {
  archived: "Restore this archived dataset before training.",
  too_few_groups: "Use at least {groups} different person/group identifiers; photographs of one person count once.",
  insufficient_split: "The validation split leaves too few training photographs. Add ratings for more people.",
  no_score_variation: "Training ratings need at least two different scores.",
  too_many_ratings: "A version supports at most 500 rated photographs. Exclude some photographs.",
};
function Completion({summary, readiness, onReviewSkipped, onUpload}: {summary: ReturnType<typeof ratingSummary>; readiness: TrainingReadiness | null; onReviewSkipped: () => void; onUpload: () => void}) {
  const {t} = useI18n();
  const needed = readiness ? Math.max(0, readiness.required_ratings - readiness.rated) : 0;
  return <section className="completion" aria-labelledby="completion-title">
    <p className="eyebrow">{t("Rating complete")}</p>
    <h3 id="completion-title">{t("Every photograph has been processed.")}</h3>
    <dl className="completion-stats">
      <div><dt>{t("Valid ratings")}</dt><dd>{summary.valid}</dd></div>
      <div><dt>{t("Skipped")}</dt><dd>{summary.skipped}</dd></div>
      <div><dt>{t("Excluded")}</dt><dd>{summary.excluded}</dd></div>
    </dl>
    {!readiness ? <p role="status">{t("Checking training eligibility…")}</p> : readiness.eligible
      ? <p>{t("Your ratings meet every training requirement. Train a personal model below.")}</p>
      : <div><p>{t("Processing every photograph is not the same as having enough valid ratings. Before training:")}</p><ul className="list-disc pl-5 mt-2 space-y-1">
        {needed > 0 && <li>{t("Add {count} more valid ratings ({rated} of {required}). Skipped and excluded photographs do not count.", {count: needed, rated: readiness.rated, required: readiness.required_ratings})}</li>}
        {readiness.reasons.filter(reason => reason !== "too_few_ratings").map(reason => <li key={reason}>{t(reasonText[reason], {groups: readiness.required_groups})}</li>)}
      </ul></div>}
    <div className="mt-5 flex flex-wrap gap-3">
      {(!readiness?.eligible) && <button type="button" className="button-primary" onClick={onUpload}>{t("Upload more photographs")}</button>}
      {summary.skipped > 0 && <button type="button" className="button-secondary" onClick={onReviewSkipped}>{t("Review skipped photographs")}</button>}
    </div>
  </section>;
}

export function PrivatePhoto({image, thumbnail = false}: {image: PreferenceImage; thumbnail?: boolean}) {
  const {t} = useI18n();
  // Authenticated endpoint only. Next's public image optimizer must not cache private photographs.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={imageUrl(image.dataset_id, image.id, thumbnail)} alt={t("Private photograph for your subjective annotation")} loading="lazy" referrerPolicy="no-referrer" className={thumbnail ? "w-full h-24 object-contain" : "rating-photo"} />;
}
