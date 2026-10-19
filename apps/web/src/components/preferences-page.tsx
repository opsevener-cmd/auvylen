"use client";
import {useI18n} from "@/components/i18n/provider";

import Link from "next/link";
import {PhotoUpload, consentText} from "@/components/photo-upload";
import {PersonalModels} from "@/components/personal-models";
import {useEffect, useMemo, useState} from "react";
import {z} from "zod";
import type {PreferenceDataset, PreferenceDetail, PreferenceImage, PreferencePair, PreferenceProject} from "@auvylen/contracts";
import {accountRequest} from "@/lib/account-api";
import {datasetSchema, detailSchema, imageSchema, imageUrl, nextPair, pairSchema, preferencePath as base, projectSchema} from "@/lib/preferences-api";

const button = "rounded border border-black/20 px-3 py-2 disabled:opacity-40";
const field = "block w-full rounded border border-black/20 p-2 mt-1 mb-3";


export function PreferencesPage() {
  const {t} = useI18n();
  const [projects, setProjects] = useState<PreferenceProject[]>([]);
  const [datasets, setDatasets] = useState<PreferenceDataset[]>([]);
  const [project, setProject] = useState("");
  const [detail, setDetail] = useState<PreferenceDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    const [p, d] = await Promise.all([accountRequest(`${base}/projects`, z.array(projectSchema)), accountRequest(`${base}/datasets`, z.array(datasetSchema))]);
    setProjects(p); setDatasets(d); setProject(current => current || p[0]?.id || "");
  }
  useEffect(() => {
    let active = true;
    Promise.all([accountRequest(`${base}/projects`, z.array(projectSchema)), accountRequest(`${base}/datasets`, z.array(datasetSchema))])
      .then(([p, d]) => {if (active) {setProjects(p); setDatasets(d); setProject(p[0]?.id ?? "");}})
      .catch(e => {if (active) setError(e instanceof Error ? e.message : "Research unavailable.");});
    return () => {active = false;};
  }, []);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError("");
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : "Request failed.");}
    finally {setBusy(false);}
  }
  return <section className="max-w-4xl space-y-6">
    <Link className="underline" href="/research">{t("Research workspace")}</Link>
    <header className="research-heading"><p className="eyebrow">{t("Your private research studio")}</p><h1 className="text-3xl font-medium">{t("Personal preference datasets")}</h1><p>{t("Create a project, collect authorized photographs and explore patterns in your own ratings.")}</p><ol className="workflow-checklist"><li className={projects.length ? "done" : ""}>{t("1 · Create project")}</li><li className={datasets.length ? "done" : ""}>{t("2 · Create dataset")}</li><li className={datasets.some(d => d.image_count > 0) ? "done" : ""}>{t("3 · Upload photographs")}</li><li className={datasets.some(d => d.rated_count >= 8) ? "done" : ""}>{t("4 · Collect 8 ratings")}</li></ol></header>
    <p>{t("Your ratings describe your subjective preferences. Research does not spend Credits. Only upload authorized adult photographs.")}</p>
    <p>{t("Private images expire after the selected retention period. Deletion blocks access immediately; the research worker removes stored files. Train a personal model from your numerical ratings and score new uploads below.")}</p>
    {error && <p role="alert">{t(error)} <Link className="underline" href="/login">{t("Sign in")}</Link></p>}
    <fieldset disabled={busy} className="space-y-5">
      <form className="workspace-panel" onSubmit={event => {event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); void perform(async () => {
        const created = await accountRequest(`${base}/projects`, projectSchema, {name: values.get("name")});
        await refresh(); setProject(created.id); form.reset();
      });}}>
        <label>{t("Project name")}<input name="name" required maxLength={120} className={field} /></label>
        <button className={button}>{t("Create project")}</button>
      </form>
      {projects.length > 0 && <>
        <label>{t("Project")}<select value={project} onChange={event => {setProject(event.target.value); setDetail(null);}} className={field}>
          {projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <details className="rounded border p-4"><summary>{t("Create a dataset")}</summary><p className="mt-3 text-sm">{t("A dataset groups photographs with a common source and rating scale. Set a retention period you can justify; expiry blocks access and schedules file removal.")}</p>
          <form className="mt-4" onSubmit={event => {event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); void perform(async () => {
            const created = await accountRequest(`${base}/datasets`, datasetSchema, {project_id: project, name: values.get("name"), source: values.get("source"), source_url: values.get("source_url"), license: values.get("license"), adult_authorized_consent: values.get("consent") === "on", retention_days: Number(values.get("retention")), rating_min: Number(values.get("min")), rating_max: Number(values.get("max"))});
            await refresh(); setDetail(await accountRequest(`${base}/datasets/${created.id}`, detailSchema)); form.reset();
          });}}>
            <label>{t("Dataset name")}<input name="name" required maxLength={120} className={field} /></label>
            <label>{t("Source")}<input name="source" required maxLength={500} className={field} /></label>
            <label>{t("Source URL (optional)")}<input name="source_url" type="url" maxLength={500} className={field} /></label>
            <label>{t("License and restrictions")}<input name="license" required maxLength={500} className={field} /></label>
            <div className="grid grid-cols-3 gap-3">
              <label>{t("Retention days")}<input name="retention" type="number" min={1} max={90} defaultValue={30} required className={field} /></label>
              <label>{t("Minimum rating")}<input name="min" type="number" min={0} max={99} defaultValue={1} required className={field} /></label>
              <label>{t("Maximum rating")}<input name="max" type="number" min={1} max={100} defaultValue={10} required className={field} /></label>
            </div>
            <label className="block mb-4"><input name="consent" type="checkbox" required /> {t(consentText)}</label>
            <button className={button}>{t("Save dataset")}</button>
          </form>
        </details>
        <ul className="space-y-2">{datasets.filter(d => d.project_id === project).map(dataset => <li key={dataset.id}>
          <button className={button} onClick={() => void perform(async () => setDetail(await accountRequest(`${base}/datasets/${dataset.id}`, detailSchema)))}>{dataset.name}{dataset.archived ? t(" (archived)") : ""} · {dataset.image_count} {t("images ·")} {dataset.rated_count} {t("rated")}</button>
        </li>)}</ul>
      </>}
    </fieldset>
    {detail && <DatasetEditor key={detail.dataset.id} initial={detail} onUpdate={updated => setDatasets(current => current.map(item => item.id === updated.id ? updated : item))} onBusy={setBusy} onChange={refresh} onDelete={() => {setDetail(null); void refresh();}} />}
  </section>;
}

function DatasetEditor({initial, onChange, onDelete, onBusy, onUpdate}: {onUpdate: (dataset: PreferenceDataset) => void; onBusy: (active: boolean) => void; initial: PreferenceDetail; onChange: () => Promise<void>; onDelete: () => void}) {
  const {t, locale} = useI18n();
  const [detail, setDetail] = useState(initial);
  const [index, setIndex] = useState(() => Math.max(0, initial.images.findIndex(i => !i.rating_recorded && !i.excluded)));
  const [mode, setMode] = useState<"rating" | "pairs">("rating");
  const [reviewPair, setReviewPair] = useState<PreferencePair | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const {dataset, images, pairs} = detail;
  const path = `${base}/datasets/${dataset.id}`;
  const selected = images[index];
  const next = useMemo(() => reviewPair ? [images.find(i => i.id === reviewPair.left_id), images.find(i => i.id === reviewPair.right_id)] : nextPair(images, pairs), [images, pairs, reviewPair]);
  const pair = next?.[0] && next?.[1] ? [next[0], next[1]] : null;
  async function reload() {setDetail(await accountRequest(path, detailSchema)); await onChange();}
  function saveImage(image: PreferenceImage) {
    const updated = images.map(item => item.id === image.id ? image : item);
    const updatedDataset = {...dataset, rated_count: updated.filter(item => item.rating_recorded && item.score !== null).length};
    setDetail({...detail, images: updated, dataset: updatedDataset}); onUpdate(updatedDataset);
    setMessage("Rating saved.");
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : "Request failed.");}
    finally {setBusy(false);}
  }
  return <section className="space-y-5 workspace-panel">
    <h2 className="text-2xl">{dataset.name}</h2>
    <p>{dataset.image_count} {t("images ·")} {dataset.rated_count} {t("rated ·")} {dataset.compared_count} {t("comparisons ·")} {images.filter(i => !i.excluded && !i.rating_recorded).length} {t("awaiting rating")}</p>
    <p>{t("Expires:")} {new Date(dataset.expires_at).toLocaleDateString(locale)} {t("· Source:")} {dataset.source} {t("· License:")} {dataset.license}</p>
    {error && <p role="alert">{t(error)}</p>}{message && <p role="status">{t(message)}</p>}
    <fieldset disabled={busy} className="space-y-5">
      <fieldset disabled={uploading}>
      <form onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
        await accountRequest(`${path}/edit`, datasetSchema, {name: values.get("name"), archived: dataset.archived}); await reload();
      });}} className="flex gap-2">
        <input aria-label={t("Rename dataset")} name="name" defaultValue={dataset.name} maxLength={120} required className={field} />
        <button className={button}>{t("Rename")}</button>
      </form>
      <div className="flex flex-wrap gap-3">
        <button className={button} onClick={() => void perform(async () => {await accountRequest(`${path}/edit`, datasetSchema, {name: dataset.name, archived: !dataset.archived}); await reload();})}>{dataset.archived ? t("Restore dataset") : t("Archive dataset")}</button>
        <button className={button} onClick={() => {if (window.confirm(t("Delete this dataset, its images and all annotations?"))) void perform(async () => {await accountRequest(`${path}/delete`, z.object({deleted: z.boolean()}), {}); onDelete();});}}>{t("Delete dataset")}</button>
      </div>
      <p className="text-sm">{t("Archive keeps saved images and annotations until expiry and pauses editing. Delete blocks access and removes images, annotations and derived model checkpoints.")}</p>
      </fieldset>
      {!dataset.archived && <>
        <PhotoUpload path={path} onSaved={image => setDetail(current => ({...current, images: current.images.some(i => i.id === image.id) ? current.images : [...current.images, image], dataset: {...current.dataset, image_count: current.images.some(i => i.id === image.id) ? current.dataset.image_count : current.dataset.image_count + 1}}))} onComplete={reload} onBusy={active => {setUploading(active); onBusy(active);}} />
        <fieldset disabled={uploading} className="space-y-5"><div className="annotation-toolbar"><button className={button} aria-pressed={mode === "rating"} onClick={() => setMode("rating")}>{t("Rate photographs")}</button><button className={button} aria-pressed={mode === "pairs"} onClick={() => setMode("pairs")}>{t("Compare pairs")}</button></div>
        {mode === "rating" && selected && <>
          <p>{t("Image")} {index + 1} {t("of")} {images.length}{selected.excluded ? t(" · Excluded") : ""}</p>
          <PrivatePhoto image={selected} />
          <form key={`${selected.id}-${selected.score}`} onSubmit={event => {event.preventDefault(); const score = Number(new FormData(event.currentTarget).get("score")); void perform(async () => {
            saveImage(await accountRequest(`${path}/images/${selected.id}/rating`, imageSchema, {score})); setIndex(Math.min(index + 1, images.length - 1));
          });}}>
            <label>{t("Your rating (")}{dataset.rating_min}–{dataset.rating_max})<input name="score" type="number" min={dataset.rating_min} max={dataset.rating_max} step="0.1" defaultValue={selected.score ?? ""} required disabled={selected.excluded} className={field} /></label>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={button} disabled={index === 0} onClick={() => setIndex(index - 1)}>{t("Previous")}</button>
              <button className={button} disabled={selected.excluded}>{t("Save and next")}</button>
              <button type="button" className={button} disabled={selected.excluded} onClick={() => void perform(async () => {saveImage(await accountRequest(`${path}/images/${selected.id}/rating`, imageSchema, {score: null})); setIndex(Math.min(index + 1, images.length - 1));})}>{t("Skip rating")}</button>
              <button type="button" className={button} disabled={index >= images.length - 1} onClick={() => setIndex(index + 1)}>{t("Next")}</button>
            </div>
          </form>
          <form key={selected.id} onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
            await accountRequest(`${path}/images/${selected.id}/edit`, imageSchema, {subject_group: String(values.get("group") || "").trim() || null, excluded: values.get("excluded") === "on"}); await reload();
          });}}>
            <label>{t("Image person/group identifier")}<input name="group" maxLength={120} defaultValue={selected.subject_group ?? ""} className={field} /></label>
            <label><input name="excluded" type="checkbox" defaultChecked={selected.excluded} /> {t("Exclude from annotation and future training")}</label>
            <button className={`${button} ml-3`}>{t("Save image settings")}</button>
          </form>
          <button className={button} onClick={() => {if (window.confirm(t("Delete this image and its annotations?"))) void perform(async () => {await accountRequest(`${path}/images/${selected.id}/delete`, z.object({deleted: z.boolean()}), {}); setIndex(0); await reload();});}}>{t("Delete image")}</button>
        </>}
        {mode === "pairs" && <>
          {pair ? <><div className="grid grid-cols-2 gap-3"><div><p>{t("Left")}</p><PrivatePhoto image={pair[0]} /></div><div><p>{t("Right")}</p><PrivatePhoto image={pair[1]} /></div></div>
            {reviewPair && <p>{t("Editing saved comparison:")} {t(reviewPair.choice)}</p>}
            <div className="flex flex-wrap gap-2">{(["left", "right", "equal", "skip"] as const).map(choice => <button key={choice} className={button} onClick={() => void perform(async () => {const saved = await accountRequest(`${path}/pairs`, pairSchema, {left_id: pair[0].id, right_id: pair[1].id, choice}); const updated = [...pairs.filter(item => item.id !== saved.id), saved]; const updatedDataset = {...dataset, compared_count: updated.length}; setDetail({...detail, pairs: updated, dataset: updatedDataset}); onUpdate(updatedDataset); setReviewPair(null); setMessage("Comparison saved.");})}>{t(({left: "Left preferred", right: "Right preferred", equal: "Equal preference", skip: "Skip pair"})[choice])}</button>)}</div>
          </> : <p>{t("No unseen pairs remain. Upload more images or edit a saved comparison below.")}</p>}
          <details><summary>{t("Review saved comparisons (")}{pairs.length})</summary><ul>{pairs.map((item, position) => <li key={item.id}><button className="underline" onClick={() => setReviewPair(item)}>{t("Comparison")} {position + 1}: {t(item.choice)}</button></li>)}</ul></details>
        </>}
        </fieldset>
      </>}
      <div className="thumbnail-grid">{images.map((image, position) => <button key={image.id} disabled={uploading} aria-pressed={index === position} className="rounded border p-1" aria-label={t("Select image {value0}", {value0: position + 1})} onClick={() => {setIndex(position); setMode("rating");}}><PrivatePhoto image={image} thumbnail /><span>{image.excluded ? t("Excluded") : image.score ?? (image.rating_recorded ? t("Skipped") : t("Unrated"))}</span></button>)}</div>
    </fieldset>
    <fieldset disabled={uploading}><PersonalModels dataset={dataset} images={images} /></fieldset>
  </section>;
}

function PrivatePhoto({image, thumbnail = false}: {image: PreferenceImage; thumbnail?: boolean}) {
  const {t} = useI18n();
  // Authenticated endpoint only. Next's public image optimizer must not cache private photographs.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={imageUrl(image.dataset_id, image.id, thumbnail)} alt={t("Private photograph for your subjective annotation")} loading="lazy" referrerPolicy="no-referrer" className={thumbnail ? "w-full h-24 object-contain" : "rating-photo"} />;
}
