"use client";
import {useEffect, useRef, useState} from "react";
import type {PreferenceImage} from "@auvylen/contracts";
import {csrfToken} from "@/lib/account-api";
import {uploadImage, validateUpload, type UploadProgress} from "@/lib/upload";
import {useI18n} from "./i18n/provider";
export const consentText = "I confirm every subject is an adult (18+), I have permission and the necessary rights to upload and annotate these photographs, and the recorded license permits this use.";
type Item = UploadProgress & {file: File; url: string; error?: string};
export function PhotoUpload({path, onSaved, onComplete, onBusy}: {path: string; onSaved: (image: PreferenceImage) => void; onComplete: () => Promise<void>; onBusy: (busy: boolean) => void}) {
  const {t} = useI18n();
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const locked = useRef(false);
  const urls = useRef<string[]>([]);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => {controller.current?.abort(); urls.current.forEach(url => URL.revokeObjectURL(url));}, []);
  const saved = items.filter(item => item.stage === "saved").length;
  function update(index: number, value: Partial<Item>) {setItems(current => current.map((item, i) => i === index ? {...item, ...value} : item));}
  return <section className="upload-zone" aria-busy={busy}>
    <h3 className="text-xl">{t("Add photographs")}</h3>
    <p className="mt-2 text-sm">{t("JPEG or PNG · 4 MiB per file · 4096px per side · 16 megapixels · Up to 20 files per batch.")}</p>
    <p className="mt-2 text-sm">{t("Standard accounts allow 500 private images; Owner capacity is shown in the Owner dashboard. Each training version supports up to 500 rated images. Stored copies have metadata removed.")}</p>
    <form className="mt-4" onSubmit={async event => {
      event.preventDefault();
      if (locked.current) return;
      const values = new FormData(event.currentTarget);
      if (!items.length) {setError("Choose at least one photograph."); return;}
      locked.current = true; setBusy(true); onBusy(true); setError("");
      const abort = new AbortController(); controller.current = abort;
      const metadata = {adult_authorized_consent: true as const, subject_group: String(values.get("group") || "").trim() || null};
      try {
        const token = await csrfToken();
        for (let index = 0; index < items.length; index++) {
          if (abort.signal.aborted) break;
          if (items[index].stage === "saved") continue;
          update(index, {stage: "preparing", error: undefined, percent: undefined});
          // Yield to the browser before validation and transport; retain only File references.
          await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
          try {
            const image = await uploadImage(`${path}/images`, items[index].file, metadata, token, value => update(index, value), abort.signal);
            onSaved(image);
          } catch (e) {update(index, {stage: "failed", error: e instanceof Error ? e.message : "Upload failed."});}
        }
        if (!abort.signal.aborted) await onComplete();
      } catch (e) {if (!abort.signal.aborted) setError(e instanceof Error ? e.message : "Upload failed.");}
      finally {locked.current = false; setBusy(false); onBusy(false);}
    }}>
      <fieldset disabled={busy}>
        <label className="button-secondary upload-picker mb-4">{t("Adult photographs")}<input className="sr-only" name="photos" type="file" accept="image/jpeg,image/png" multiple onChange={event => {
          if (locked.current) return;
          const files = Array.from(event.target.files ?? []);
          if (files.length > 20) {setError("Select at most 20 images per batch."); event.target.value = ""; return;}
          urls.current.forEach(url => URL.revokeObjectURL(url)); urls.current = [];
          setItems(files.map(file => {
            try {validateUpload(file); const url = URL.createObjectURL(file); urls.current.push(url); return {file, url, stage: "waiting"};}
            catch (e) {return {file, url: "", stage: "failed", error: e instanceof Error ? e.message : "Upload failed."};}
          })); setError("");
        }}/></label>
        <label>{t("Person/group identifier (optional; same person must use the same identifier)")}<input name="group" maxLength={120} className="block w-full rounded border p-2 mt-1 mb-3" /></label>
        <p className="text-sm">{t("For example, use person-01 for every photo of the same adult. A batch shares this identifier; use separate batches for different people or edit each image before training.")}</p>
        <label className="block my-4 text-sm"><input name="consent" type="checkbox" required />{t(consentText)}</label>
        <button className="button-primary" disabled={!items.length || saved === items.length}>{t(busy ? "Uploading photographs…" : items.some(item => item.stage === "failed") ? "Retry unsaved photographs" : "Upload photographs")}</button>
      </fieldset>
    </form>
    {error && <p role="alert" className="mt-3">{t(error)}</p>}
    {items.length > 0 && <><p role="status" className="mt-4" aria-live="polite">{t("{saved} of {total} photographs confirmed saved (duplicates are reused).", {saved, total: items.length})}{busy && ` ${t("Keep this page open while uploading.")}`}</p><ul className="upload-queue">{items.map((item, index) => <li className="upload-item" key={index}>
      {item.url && <Preview url={item.url} />}
      <div><strong>{item.file.name}</strong><p>{t(({waiting: "Ready to upload", preparing: "Preparing image", uploading: "Uploading", processing: "Processing image · Waiting for server confirmation", saved: "Saved successfully", failed: "Upload failed"})[item.stage])}{item.stage === "uploading" && item.percent !== undefined ? ` ${item.percent}%` : ""}</p>
        {item.stage === "uploading" && <progress aria-label={t("Network upload progress")} max={100} value={item.percent}/>}
        {item.error && <p className="text-[#7b3529]">{t(item.error)}</p>}
      </div></li>)}</ul></>}
  </section>;
}
function Preview({url}: {url: string}) {
  const {t} = useI18n();
  // Local object URLs never leave this browser and are revoked on replacement/unmount.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={t("Local preview of a selected photograph")} />;
}
