"use client";

import Link from "next/link";
import {PersonalModels} from "@/components/personal-models";
import {useEffect, useState} from "react";
import {z} from "zod";
import type {PreferenceDataset, PreferenceDetail, PreferenceImage, PreferencePair, PreferenceProject} from "@auvylen/contracts";
import {accountRequest} from "@/lib/account-api";
import {datasetSchema, detailSchema, encodeUpload, imageSchema, imageUrl, nextPair, pairSchema, preferencePath as base, projectSchema} from "@/lib/preferences-api";

const button = "rounded border border-black/20 px-3 py-2 disabled:opacity-40";
const field = "block w-full rounded border border-black/20 p-2 mt-1 mb-3";
const consentText = "I confirm every subject is an adult (18+), I have permission and the necessary rights to upload and annotate these photographs, and the recorded license permits this use.";

export function PreferencesPage() {
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
    <Link className="underline" href="/research">Research workspace</Link>
    <h1 className="text-3xl font-medium">Personal preference datasets</h1>
    <p>Your ratings describe your subjective preferences. Research does not spend Credits. Only upload authorized adult photographs.</p>
    <p>Private images expire after the selected retention period. Deletion blocks access immediately; the research worker removes stored files. Train a personal model from your numerical ratings and score new uploads below.</p>
    {error && <p role="alert">{error} <Link className="underline" href="/login">Sign in</Link></p>}
    <fieldset disabled={busy} className="space-y-5">
      <form className="rounded border p-4" onSubmit={event => {event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); void perform(async () => {
        const created = await accountRequest(`${base}/projects`, projectSchema, {name: values.get("name")});
        await refresh(); setProject(created.id); form.reset();
      });}}>
        <label>Project name<input name="name" required maxLength={120} className={field} /></label>
        <button className={button}>Create project</button>
      </form>
      {projects.length > 0 && <>
        <label>Project<select value={project} onChange={event => {setProject(event.target.value); setDetail(null);}} className={field}>
          {projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <details className="rounded border p-4"><summary>Create a dataset</summary>
          <form className="mt-4" onSubmit={event => {event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); void perform(async () => {
            const created = await accountRequest(`${base}/datasets`, datasetSchema, {project_id: project, name: values.get("name"), source: values.get("source"), source_url: values.get("source_url"), license: values.get("license"), adult_authorized_consent: values.get("consent") === "on", retention_days: Number(values.get("retention")), rating_min: Number(values.get("min")), rating_max: Number(values.get("max"))});
            await refresh(); setDetail(await accountRequest(`${base}/datasets/${created.id}`, detailSchema)); form.reset();
          });}}>
            <label>Dataset name<input name="name" required maxLength={120} className={field} /></label>
            <label>Source<input name="source" required maxLength={500} className={field} /></label>
            <label>Source URL (optional)<input name="source_url" type="url" maxLength={500} className={field} /></label>
            <label>License and restrictions<input name="license" required maxLength={500} className={field} /></label>
            <div className="grid grid-cols-3 gap-3">
              <label>Retention days<input name="retention" type="number" min={1} max={90} defaultValue={30} required className={field} /></label>
              <label>Minimum rating<input name="min" type="number" min={0} max={99} defaultValue={1} required className={field} /></label>
              <label>Maximum rating<input name="max" type="number" min={1} max={100} defaultValue={10} required className={field} /></label>
            </div>
            <label className="block mb-4"><input name="consent" type="checkbox" required /> {consentText}</label>
            <button className={button}>Save dataset</button>
          </form>
        </details>
        <ul className="space-y-2">{datasets.filter(d => d.project_id === project).map(dataset => <li key={dataset.id}>
          <button className={button} onClick={() => void perform(async () => setDetail(await accountRequest(`${base}/datasets/${dataset.id}`, detailSchema)))}>{dataset.name}{dataset.archived ? " (archived)" : ""} · {dataset.image_count} images · {dataset.rated_count} rated</button>
        </li>)}</ul>
      </>}
    </fieldset>
    {detail && <DatasetEditor key={detail.dataset.id} initial={detail} onChange={refresh} onDelete={() => {setDetail(null); void refresh();}} />}
  </section>;
}

function DatasetEditor({initial, onChange, onDelete}: {initial: PreferenceDetail; onChange: () => Promise<void>; onDelete: () => void}) {
  const [detail, setDetail] = useState(initial);
  const [index, setIndex] = useState(() => Math.max(0, initial.images.findIndex(i => !i.rating_recorded && !i.excluded)));
  const [mode, setMode] = useState<"rating" | "pairs">("rating");
  const [reviewPair, setReviewPair] = useState<PreferencePair | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const {dataset, images, pairs} = detail;
  const path = `${base}/datasets/${dataset.id}`;
  const selected = images[index];
  const next = reviewPair ? [images.find(i => i.id === reviewPair.left_id), images.find(i => i.id === reviewPair.right_id)] : nextPair(images, pairs);
  const pair = next?.[0] && next?.[1] ? [next[0], next[1]] : null;
  async function reload() {setDetail(await accountRequest(path, detailSchema)); await onChange();}
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : "Request failed.");}
    finally {setBusy(false);}
  }
  return <section className="space-y-5 rounded border p-5">
    <h2 className="text-2xl">{dataset.name}</h2>
    <p>{dataset.image_count} images · {dataset.rated_count} rated · {dataset.compared_count} comparisons · {images.filter(i => !i.excluded && !i.rating_recorded).length} awaiting rating</p>
    <p>Expires: {new Date(dataset.expires_at).toLocaleDateString()} · Source: {dataset.source} · License: {dataset.license}</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <fieldset disabled={busy} className="space-y-5">
      <form onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
        await accountRequest(`${path}/edit`, datasetSchema, {name: values.get("name"), archived: dataset.archived}); await reload();
      });}} className="flex gap-2">
        <input aria-label="Rename dataset" name="name" defaultValue={dataset.name} maxLength={120} required className={field} />
        <button className={button}>Rename</button>
      </form>
      <div className="flex flex-wrap gap-3">
        <button className={button} onClick={() => void perform(async () => {await accountRequest(`${path}/edit`, datasetSchema, {name: dataset.name, archived: !dataset.archived}); await reload();})}>{dataset.archived ? "Restore dataset" : "Archive dataset"}</button>
        <button className={button} onClick={() => {if (window.confirm("Delete this dataset, its images and all annotations?")) void perform(async () => {await accountRequest(`${path}/delete`, z.object({deleted: z.boolean()}), {}); onDelete();});}}>Delete dataset</button>
      </div>
      {!dataset.archived && <>
        <form onSubmit={event => {event.preventDefault(); const form = event.currentTarget; const values = new FormData(form); void perform(async () => {
          const files = values.getAll("photos").filter((f): f is File => f instanceof File && f.size > 0);
          if (files.length > 20) throw new Error("Select at most 20 images per batch.");
          let completed = 0;
          try {
            for (const file of files) {
              await accountRequest(`${path}/images`, imageSchema, {content_base64: await encodeUpload(file), adult_authorized_consent: values.get("consent") === "on", subject_group: String(values.get("group") || "").trim() || null});
              completed++; setMessage(`${completed} of ${files.length} images processed (duplicates are reused).`);
            }
            form.reset();
          } finally {await reload();}
        });}}>
          <label>Adult photographs<input name="photos" type="file" accept="image/jpeg,image/png" multiple required className={field} /></label>
          <p>JPEG or PNG, up to 4 MiB each, 4096px per side and 16 megapixels. Up to 500 private images per account. Originals are replaced by metadata-free JPEG copies.</p>
          <label>Person/group identifier (optional; same person must use the same identifier)<input name="group" maxLength={120} className={field} /></label>
          <label className="block my-3"><input name="consent" type="checkbox" required /> {consentText}</label>
          <button className={button}>Upload photographs</button>
        </form>
        <div className="flex gap-3"><button className={button} aria-pressed={mode === "rating"} onClick={() => setMode("rating")}>Rate photographs</button><button className={button} aria-pressed={mode === "pairs"} onClick={() => setMode("pairs")}>Compare pairs</button></div>
        {mode === "rating" && selected && <>
          <p>Image {index + 1} of {images.length}{selected.excluded ? " · Excluded" : ""}</p>
          <PrivatePhoto image={selected} />
          <form key={`${selected.id}-${selected.score}`} onSubmit={event => {event.preventDefault(); const score = Number(new FormData(event.currentTarget).get("score")); void perform(async () => {
            await accountRequest(`${path}/images/${selected.id}/rating`, imageSchema, {score}); await reload(); setIndex(Math.min(index + 1, images.length - 1));
          });}}>
            <label>Your rating ({dataset.rating_min}–{dataset.rating_max})<input name="score" type="number" min={dataset.rating_min} max={dataset.rating_max} step="0.1" defaultValue={selected.score ?? ""} required disabled={selected.excluded} className={field} /></label>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={button} disabled={index === 0} onClick={() => setIndex(index - 1)}>Previous</button>
              <button className={button} disabled={selected.excluded}>Save and next</button>
              <button type="button" className={button} disabled={selected.excluded} onClick={() => void perform(async () => {await accountRequest(`${path}/images/${selected.id}/rating`, imageSchema, {score: null}); await reload(); setIndex(Math.min(index + 1, images.length - 1));})}>Skip rating</button>
              <button type="button" className={button} disabled={index >= images.length - 1} onClick={() => setIndex(index + 1)}>Next</button>
            </div>
          </form>
          <form key={selected.id} onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
            await accountRequest(`${path}/images/${selected.id}/edit`, imageSchema, {subject_group: String(values.get("group") || "").trim() || null, excluded: values.get("excluded") === "on"}); await reload();
          });}}>
            <label>Image person/group identifier<input name="group" maxLength={120} defaultValue={selected.subject_group ?? ""} className={field} /></label>
            <label><input name="excluded" type="checkbox" defaultChecked={selected.excluded} /> Exclude from annotation and future training</label>
            <button className={`${button} ml-3`}>Save image settings</button>
          </form>
          <button className={button} onClick={() => {if (window.confirm("Delete this image and its annotations?")) void perform(async () => {await accountRequest(`${path}/images/${selected.id}/delete`, z.object({deleted: z.boolean()}), {}); setIndex(0); await reload();});}}>Delete image</button>
        </>}
        {mode === "pairs" && <>
          {pair ? <><div className="grid grid-cols-2 gap-3"><div><p>Left</p><PrivatePhoto image={pair[0]} /></div><div><p>Right</p><PrivatePhoto image={pair[1]} /></div></div>
            {reviewPair && <p>Editing saved comparison: {reviewPair.choice}</p>}
            <div className="flex flex-wrap gap-2">{(["left", "right", "equal", "skip"] as const).map(choice => <button key={choice} className={button} onClick={() => void perform(async () => {await accountRequest(`${path}/pairs`, pairSchema, {left_id: pair[0].id, right_id: pair[1].id, choice}); setReviewPair(null); await reload();})}>{({left: "Left preferred", right: "Right preferred", equal: "Equal preference", skip: "Skip pair"})[choice]}</button>)}</div>
          </> : <p>No unseen pairs remain. Upload more images or edit a saved comparison below.</p>}
          <details><summary>Review saved comparisons ({pairs.length})</summary><ul>{pairs.map((item, position) => <li key={item.id}><button className="underline" onClick={() => setReviewPair(item)}>Comparison {position + 1}: {item.choice}</button></li>)}</ul></details>
        </>}
      </>}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">{images.map((image, position) => <button key={image.id} className="rounded border p-1" aria-label={`Select image ${position + 1}`} onClick={() => {setIndex(position); setMode("rating");}}><PrivatePhoto image={image} thumbnail /><span>{image.excluded ? "Excluded" : image.score ?? (image.rating_recorded ? "Skipped" : "Unrated")}</span></button>)}</div>
    </fieldset>
    <PersonalModels dataset={dataset} images={images} />
  </section>;
}

function PrivatePhoto({image, thumbnail = false}: {image: PreferenceImage; thumbnail?: boolean}) {
  // Authenticated endpoint only. Next's public image optimizer must not cache private photographs.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={imageUrl(image.dataset_id, image.id, thumbnail)} alt="Private photograph for your subjective annotation" loading="lazy" referrerPolicy="no-referrer" className={thumbnail ? "w-full h-24 object-contain" : "w-full max-h-96 object-contain"} />;
}
