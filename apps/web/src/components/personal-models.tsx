"use client";
import {useI18n} from "@/components/i18n/provider";

import {pollWhileVisible} from "@/lib/polling";
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
  const {t, locale} = useI18n();
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
    const stop = pollWhileVisible(async () => {
      const updated = await accountRequest(`/research/jobs/${jobId}`, researchJobSchema);
      if (!active) return false;
      if (!["QUEUED", "RUNNING"].includes(updated.status)) {
        const all = await accountRequest(`${base}/models`, z.array(modelSchema));
        if (active) {
          const versions = all.filter(m => m.dataset_id === datasetId);
          setModels(versions); setSelected(current => updated.kind === "TRAIN" && typeof updated.result?.model_id === "string" ? updated.result.model_id : current || versions.find(m => m.state === "READY")?.id || "");
        }
        if (active) setJob(updated);
        return false;
      }
      setJob(updated);
      return true;
    }, e => {if (active) setError(e instanceof Error ? e.message : "Cannot check the saved job. Reload to resume.");});
    return () => {active = false; stop();};
  }, [running, jobId, datasetId]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError("");
    try {await action();} catch (e) {setError(e instanceof Error ? e.message : "Model request failed.");}
    finally {setBusy(false);}
  }
  const prediction = predictionSchema.safeParse(job?.result);
  const current = models.find(m => m.id === selected);
  const eligible = images.filter(image => !image.excluded && image.score !== null);
  const rated = eligible.length;
  const groups = new Set(eligible.map(image => image.subject_group ? `subject:${image.subject_group}` : `image:${image.id}`)).size;
  return <section className="mt-8 space-y-4 border-t pt-6">
    <h2 className="text-2xl">{t("Your preference models")}</h2>
    <p>{t("Models learn from your numerical ratings using handcrafted features or frozen pretrained MobileNetV3-Small features. MobileNet was trained on general ImageNet objects, not facial preferences. Small personal datasets may generalize poorly; these scores express your preference, not objective beauty.")}</p>
    <p>{t("At least 8 rated images and 5 independent groups are required. Give photographs of the same person a shared group identifier before training. Each version keeps an immutable annotation snapshot and a separate validation split.")}</p>
    {error && <p role="alert">{t(error)}</p>}
    <fieldset disabled={busy || running} className="space-y-4">
      <form onSubmit={event => {event.preventDefault(); const values = new FormData(event.currentTarget); void perform(async () => {
        const queued = await accountRequest(`${base}/train`, researchJobSchema, {dataset_id: datasetId, idempotency_key: crypto.randomUUID(), extractor: String(values.get("extractor")), alpha: Number(values.get("alpha")), seed: Number(values.get("seed")), validation_fraction: Number(values.get("fraction"))}); await refresh(); setJob(queued);
      });}}>
        <label>{t("Visual feature extractor")}<select className={input} name="extractor" defaultValue="rgb-grid-texture-v1">
          <option value="rgb-grid-texture-v1">{t("Handcrafted color and texture baseline")}</option>
          <option value="mobilenetv3-small-imagenet-onnx-v1" disabled={!extractors.some(e => e.id === "mobilenetv3-small-imagenet-onnx-v1" && e.available)}>{t("Pretrained MobileNetV3-Small · ImageNet · CPU")}</option>
        </select></label>
        {extractors.filter(e => !e.available).map(e => <p key={e.id}>{e.id}: {t(e.reason)}</p>)}
        <p>{t("MobileNet training also evaluates the handcrafted and mean-rating baselines on exactly the same held-out groups. Lower error on your holdout alone does not establish facial prediction accuracy.")}</p>
        <details className="rounded border p-4"><summary>{t("Training settings explained")}</summary><p className="mt-3">{t("Regularization limits how strongly a small dataset can influence the model. A value of 10 is a sensible starting point.")}</p><p className="mt-2">{t("The random seed makes the group split reproducible. The validation fraction reserves a share of people for evaluation instead of learning.")}</p><p className="mt-2">{t("Handcrafted features describe colors and textures cheaply. MobileNet provides a richer general image representation, requires installed weights and uses more CPU. Neither is a validated facial attractiveness model.")}</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label>{t("Regularization strength")}<input className={input} name="alpha" type="number" defaultValue={10} min={0.001} max={1000} step="0.001" required /></label>
          <label>{t("Random seed")}<input className={input} name="seed" type="number" defaultValue={42} min={0} max={2147483647} required /></label>
          <label>{t("Validation group fraction")}<input className={input} name="fraction" type="number" defaultValue={0.2} min={0.1} max={0.4} step="0.05" required /></label>
        </div>
        </details>
        <button className={button} aria-describedby="training-readiness" disabled={dataset.archived || rated < 8 || groups < 5}>{t("Train new version")}</button>
        <p id="training-readiness" className="mt-3">{dataset.archived ? t("Restore this dataset before training.") : rated < 8 || groups < 5 ? t("Training needs at least 8 ratings and 5 independent groups. Add ratings and check person identifiers.") : t("Ready to train. The server also checks score variety and the validation split.")}</p>
        <p>{groups} {t("independent groups ·")} {rated} {t("numerical ratings")}</p>
        <p className="mt-2">{rated} {t("eligible numerical ratings. Add/edit ratings, then train another version to retrain. Validation photographs are held out from fitting and preprocessing.")}</p>
      </form>
      <label>{t("Model version")}<select className={input} value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">{t("Select a ready model")}</option>{models.filter(m => m.state === "READY").map(m => <option key={m.id} value={m.id}>{t("Version")} {m.version} · {m.extractor} · {new Date(m.created_at).toLocaleString(locale)}</option>)}
      </select></label>
      <label>{t("Photograph to predict")}<select className={input} value={imageId} onChange={event => setImageId(event.target.value)}>
        <option value="">{t("Upload/select a new photograph")}</option>{images.filter(i => !i.excluded).map((image, index) => <option key={image.id} value={image.id}>{t("Image")} {index + 1}{image.score === null ? t(" · unrated") : t(" · rated")}</option>)}
      </select></label>
      <button className={button} disabled={!selected || !imageId} onClick={() => void perform(async () => {
        setJob(await accountRequest(`${base}/predict`, researchJobSchema, {model_id: selected, dataset_id: datasetId, image_id: imageId, idempotency_key: crypto.randomUUID()}));
      })}>{t("Predict personal rating")}</button>
    </fieldset>
    {job && <div className="rounded border p-4" aria-live="polite">
      <progress max={100} value={job.progress} aria-label={t("Server-reported job progress")}/><p>{t("Custom job:")} {t(job.status)} · {t(job.phase)} · {job.progress}%</p>
      {running && <button className={button} disabled={busy} onClick={() => void perform(async () => {setJob(await accountRequest(`/research/jobs/${job.id}/cancel`, researchJobSchema, {})); await refresh();})}>{t("Cancel custom job")}</button>}
      {job.failure_reason && <p>{t(job.failure_reason)}</p>}
      {prediction.success && <>
        <p className="text-2xl mt-3">{t("Predicted personal rating:")} {prediction.data.display_score.toFixed(2)} / {prediction.data.score_max}</p>
        <p>{t("Raw prediction:")} {prediction.data.raw_score.toFixed(3)} {t("· Version")} {prediction.data.model_version} · {prediction.data.processing_duration_ms.toFixed(1)} {t("ms")}</p>
        <p>{prediction.data.seen_in_training_snapshot ? t("This photograph was included in the saved annotation snapshot.") : t("This photograph was unseen in the model's annotation snapshot.")}</p>
      </>}
    </div>}
    {current?.metrics && <div className="rounded border p-4">
      <h3 className="text-xl">{t("Validation for version")} {current.version}</h3>
      <p>{String(current.metrics.training_images)} {t("training images ·")} {String(current.metrics.validation_images)} {t("validation images")}</p>
      <p>{String(current.metrics.known_subject_groups)} {t("known subject groups ·")} {String(current.metrics.unknown_subject_images)} {t("images with unknown subject identity")}</p>
      <p>{t("MAE is the average distance between predicted and saved ratings; RMSE gives larger errors more weight. Lower values are better on the same held-out people, but a small validation set cannot establish broad accuracy.")}</p>
      <p>{t("Validation MAE:")} {t(metric(current.metrics.validation_mae))} {t("· RMSE:")} {t(metric(current.metrics.validation_rmse))} {t("· Mean-rating baseline MAE:")} {t(metric(current.metrics.mean_baseline_mae))}</p>
      <p>{t("Extractor:")} {current.extractor}</p>
      <table className="w-full text-left"><caption>{t("Identical grouped holdout comparison")}</caption><thead><tr><th>{t("Predictor")}</th><th>{t("MAE")}</th><th>{t("RMSE")}</th></tr></thead><tbody>
        <tr><td>{t("Selected model")}</td><td>{t(metric(current.metrics.validation_mae))}</td><td>{t(metric(current.metrics.validation_rmse))}</td></tr>
        <tr><td>{t("Handcrafted baseline")}</td><td>{t(metric(current.metrics.handcrafted_baseline_mae))}</td><td>{t(metric(current.metrics.handcrafted_baseline_rmse))}</td></tr>
        <tr><td>{t("Training-mean predictor")}</td><td>{t(metric(current.metrics.mean_baseline_mae))}</td><td>{t(metric(current.metrics.mean_baseline_rmse))}</td></tr>
      </tbody></table>
      <p>{t("Unavailable comparison metrics on older versions were not measured when those versions were trained.")}</p>
      <p>{t("Training duration:")} {t(metric(current.metrics.training_duration_seconds))} {t("seconds · Extraction:")} {t(metric(current.metrics.extraction_duration_seconds))} {t("seconds · Cached embeddings reused:")} {String(current.metrics.embedding_cache_hits ?? t("Unavailable"))}</p>
      <ul className="list-disc pl-5 mt-3">{current.limitations.map(text => <li key={text}>{t(text)}</li>)}</ul>
    </div>}
    <h3 className="text-xl">{t("Saved model versions")}</h3>{models.length === 0 && <p>{t("No model versions yet. Rate your photographs, then train your first version above.")}</p>}
    <ul className="space-y-3">{models.map(model => <li key={model.id} className="rounded border p-3">
      <p>{t("Version")} {model.version} · {t(model.state)} · {model.extractor}</p>
      {["READY", "ARCHIVED"].includes(model.state) && <button className={button} disabled={busy} onClick={() => void perform(async () => {await accountRequest(`${base}/models/${model.id}/edit`, modelSchema, {archived: model.state !== "ARCHIVED"}); await refresh();})}>{model.state === "ARCHIVED" ? t("Restore model") : t("Archive model")}</button>}
      {model.state !== "DELETED" && <button className={`${button} ml-2`} disabled={busy} onClick={() => {if (window.confirm(t("Delete this model version and its checkpoint? Your annotations remain."))) void perform(async () => {await accountRequest(`${base}/models/${model.id}/delete`, z.object({deleted: z.boolean()}), {}); await refresh();});}}>{t("Delete model version")}</button>}
    </li>)}</ul>
    <p>{t("Models expire with their source dataset. Deleting a source image invalidates derived versions; the worker removes their checkpoints. Original annotations stay independent of model archive/delete.")}</p>
  </section>;
}
