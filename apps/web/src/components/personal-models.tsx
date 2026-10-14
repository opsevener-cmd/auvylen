"use client";

import {useEffect, useState} from "react";
import {z} from "zod";
import type {FeatureExtractor, PersonalModel, PreferenceDataset, PreferenceImage, ResearchJob} from "@auvylen/contracts";
import {accountRequest} from "@/lib/account-api";
import {extractorSchema, metric, modelSchema, predictionSchema} from "@/lib/model-api";
import {preferencePath as base} from "@/lib/preferences-api";
import {researchJobSchema} from "@/lib/research-api";

const button = "rounded border border-black/20 px-3 py-2 disabled:opacity-40";
const input = "block rounded border border-black/20 p-2 mt-1 mb-3 w-full";
export function PersonalModels({dataset, images}: {dataset: PreferenceDataset; images: PreferenceImage[]}) {
  const [extractors, setExtractors] = useState<FeatureExtractor[]>([]);
  const [models, setModels] = useState<PersonalModel[]>([]);
  const [selected, setSelected] = useState("");
  const [imageId, setImageId] = useState("");
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = job?.status === "QUEUED" || job?.status === "RUNNING";
  const jobId = job?.id;
  const datasetId = dataset.id;
  async function refresh() {
    const all = await accountRequest(`${base}/models`, z.array(modelSchema));
    const versions = all.filter(model => model.dataset_id === datasetId);
    setModels(versions);
    setSelected(current => versions.some(m => m.id === current && m.state === "READY") ? current : versions.find(m => m.state === "READY")?.id ?? "");
  }
  useEffect(() => {
    let active = true;
    Promise.all([accountRequest(`${base}/models`, z.array(modelSchema)), accountRequest("/research/jobs", z.array(researchJobSchema)), accountRequest(`${base}/extractors`, z.array(extractorSchema))])
      .then(([all, jobs, representations]) => {
        if (!active) return;
        setExtractors(representations);
        const versions = all.filter(m => m.dataset_id === datasetId);
        setModels(versions); setSelected(versions.find(m => m.state === "READY")?.id ?? "");
        const saved = jobs.filter(j => j.provider === "custom" && j.payload?.dataset_id === datasetId);
        setJob(saved.find(j => ["QUEUED", "RUNNING"].includes(j.status)) ?? saved[0] ?? null);
      }).catch(e => {if (active) setError(e instanceof Error ? e.message : "Model service unavailable.");});
    return () => {active = false;};
  }, [datasetId]);
  useEffect(() => {
    if (!running || !jobId) return;
    let active = true;
    const timer = setInterval(() => {
      accountRequest(`/research/jobs/${jobId}`, researchJobSchema).then(async updated => {
        if (!active) return;
        if (!["QUEUED", "RUNNING"].includes(updated.status)) {
          clearInterval(timer);
          const all = await accountRequest(`${base}/models`, z.array(modelSchema));
          if (active) {
            const versions = all.filter(m => m.dataset_id === datasetId);
            setModels(versions); setSelected(current => updated.kind === "TRAIN" && typeof updated.result?.model_id === "string" ? updated.result.model_id : current || versions.find(m => m.state === "READY")?.id || "");
            setJob(updated);
          }
        } else {setJob(updated);}
      }).catch(e => {if (active) {clearInterval(timer); setError(e instanceof Error ? e.message : "Cannot check the saved job. Reload to resume.");}});
    }, 1000);
    return () => {active = false; clearInterval(timer);};
  }, [running, jobId, datasetId]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError("");
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : "Model request failed.");}
    finally {setBusy(false);}
  }
  const prediction = predictionSchema.safeParse(job?.result);
  const current = models.find(m => m.id === selected);
  const rated = images.filter(image => !image.excluded && image.score !== null).length;
  return <section className="mt-8 space-y-4 border-t pt-6">
    <h2 className="text-2xl">Your preference models</h2>
    <p>Models learn from your numerical ratings using handcrafted features or frozen pretrained MobileNetV3-Small features. MobileNet was trained on general ImageNet objects, not facial preferences. Small personal datasets may generalize poorly; these scores express your preference, not objective beauty.</p>
    <p>At least 8 rated images and 5 independent groups are required. Give photographs of the same person a shared group identifier before training. Each version keeps an immutable annotation snapshot and a separate validation split.</p>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy || running} className="space-y-4">
      <form onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
        const queued = await accountRequest(`${base}/train`, researchJobSchema, {dataset_id: datasetId, idempotency_key: crypto.randomUUID(), extractor: String(values.get("extractor")), alpha: Number(values.get("alpha")), seed: Number(values.get("seed")), validation_fraction: Number(values.get("fraction"))}); await refresh(); setJob(queued);
      });}}>
        <label>Visual feature extractor<select className={input} name="extractor" defaultValue="rgb-grid-texture-v1">
          <option value="rgb-grid-texture-v1">Handcrafted color and texture baseline</option>
          <option value="mobilenetv3-small-imagenet-onnx-v1" disabled={!extractors.some(e => e.id === "mobilenetv3-small-imagenet-onnx-v1" && e.available)}>Pretrained MobileNetV3-Small · ImageNet · CPU</option>
        </select></label>
        {extractors.filter(e => !e.available).map(e => <p key={e.id}>{e.id}: {e.reason}</p>)}
        <p>MobileNet training also evaluates the handcrafted and mean-rating baselines on exactly the same held-out groups. Lower error on your holdout alone does not establish facial prediction accuracy.</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label>Regularization strength<input className={input} name="alpha" type="number" defaultValue={10} min={0.001} max={1000} step="0.001" required /></label>
          <label>Random seed<input className={input} name="seed" type="number" defaultValue={42} min={0} max={2147483647} required /></label>
          <label>Validation group fraction<input className={input} name="fraction" type="number" defaultValue={0.2} min={0.1} max={0.4} step="0.05" required /></label>
        </div>
        <button className={button} disabled={dataset.archived || rated < 8}>Train new version</button>
        <p className="mt-2">{rated} eligible numerical ratings. Add/edit ratings, then train another version to retrain. Validation photographs are held out from fitting and preprocessing.</p>
      </form>
      <label>Model version<select className={input} value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">Select a ready model</option>{models.filter(m => m.state === "READY").map(m => <option key={m.id} value={m.id}>Version {m.version} · {m.extractor} · {new Date(m.created_at).toLocaleString()}</option>)}
      </select></label>
      <label>Photograph to predict<select className={input} value={imageId} onChange={event => setImageId(event.target.value)}>
        <option value="">Upload/select a new photograph</option>{images.filter(i => !i.excluded).map((image, index) => <option key={image.id} value={image.id}>Image {index + 1}{image.score === null ? " · unrated" : " · rated"}</option>)}
      </select></label>
      <button className={button} disabled={!selected || !imageId} onClick={() => void perform(async () => {
        setJob(await accountRequest(`${base}/predict`, researchJobSchema, {model_id: selected, dataset_id: datasetId, image_id: imageId, idempotency_key: crypto.randomUUID()}));
      })}>Predict personal rating</button>
    </fieldset>
    {job && <div className="rounded border p-4" aria-live="polite">
      <p>Custom job: {job.status} · {job.phase} · {job.progress}%</p>
      {running && <button className={button} disabled={busy} onClick={() => void perform(async () => {setJob(await accountRequest(`/research/jobs/${job.id}/cancel`, researchJobSchema, {})); await refresh();})}>Cancel custom job</button>}
      {job.failure_reason && <p>{job.failure_reason}</p>}
      {prediction.success && <>
        <p className="text-2xl mt-3">Predicted personal rating: {prediction.data.display_score.toFixed(2)} / {prediction.data.score_max}</p>
        <p>Raw prediction: {prediction.data.raw_score.toFixed(3)} · Version {prediction.data.model_version} · {prediction.data.processing_duration_ms.toFixed(1)} ms</p>
        <p>{prediction.data.seen_in_training_snapshot ? "This photograph was included in the saved annotation snapshot." : "This photograph was unseen in the model's annotation snapshot."}</p>
      </>}
    </div>}
    {current?.metrics && <div className="rounded border p-4">
      <h3 className="text-xl">Validation for version {current.version}</h3>
      <p>{String(current.metrics.training_images)} training images · {String(current.metrics.validation_images)} validation images</p>
      <p>{String(current.metrics.known_subject_groups)} known subject groups · {String(current.metrics.unknown_subject_images)} images with unknown subject identity</p>
      <p>Validation MAE: {metric(current.metrics.validation_mae)} · RMSE: {metric(current.metrics.validation_rmse)} · Mean-rating baseline MAE: {metric(current.metrics.mean_baseline_mae)}</p>
      <p>Extractor: {current.extractor}</p>
      <table className="w-full text-left"><caption>Identical grouped holdout comparison</caption><thead><tr><th>Predictor</th><th>MAE</th><th>RMSE</th></tr></thead><tbody>
        <tr><td>Selected model</td><td>{metric(current.metrics.validation_mae)}</td><td>{metric(current.metrics.validation_rmse)}</td></tr>
        <tr><td>Handcrafted baseline</td><td>{metric(current.metrics.handcrafted_baseline_mae)}</td><td>{metric(current.metrics.handcrafted_baseline_rmse)}</td></tr>
        <tr><td>Training-mean predictor</td><td>{metric(current.metrics.mean_baseline_mae)}</td><td>{metric(current.metrics.mean_baseline_rmse)}</td></tr>
      </tbody></table>
      <p>Unavailable comparison metrics on older versions were not measured when those versions were trained.</p>
      <p>Training duration: {metric(current.metrics.training_duration_seconds)} seconds · Extraction: {metric(current.metrics.extraction_duration_seconds)} seconds · Cached embeddings reused: {String(current.metrics.embedding_cache_hits ?? "Unavailable")}</p>
      <ul className="list-disc pl-5 mt-3">{current.limitations.map(text => <li key={text}>{text}</li>)}</ul>
    </div>}
    <h3 className="text-xl">Saved model versions</h3>
    <ul className="space-y-3">{models.map(model => <li key={model.id} className="rounded border p-3">
      <p>Version {model.version} · {model.state} · {model.extractor}</p>
      {["READY", "ARCHIVED"].includes(model.state) && <button className={button} disabled={busy} onClick={() => void perform(async () => {await accountRequest(`${base}/models/${model.id}/edit`, modelSchema, {archived: model.state !== "ARCHIVED"}); await refresh();})}>{model.state === "ARCHIVED" ? "Restore model" : "Archive model"}</button>}
      {model.state !== "DELETED" && <button className={`${button} ml-2`} disabled={busy} onClick={() => {if (window.confirm("Delete this model version and its checkpoint? Your annotations remain.")) void perform(async () => {await accountRequest(`${base}/models/${model.id}/delete`, z.object({deleted: z.boolean()}), {}); await refresh();});}}>Delete model version</button>}
    </li>)}</ul>
    <p>Models expire with their source dataset. Deleting a source image invalidates derived versions; the worker removes their checkpoints. Original annotations stay independent of model archive/delete.</p>
  </section>;
}
