import type {ImageUploadMetadata, PreferenceImage} from "@auvylen/contracts";
import type {z} from "zod";
import {imageSchema} from "./preferences-api";
import {requestError} from "./account-api";
export type UploadStage = "waiting" | "preparing" | "uploading" | "processing" | "saved" | "failed";
export type UploadProgress = {stage: UploadStage; percent?: number};
export const maxUploadBytes = 4 * 1024 * 1024;
export function validateUpload(file: File): void {
  if (file.size === 0 || file.size > maxUploadBytes) throw new Error("Each image must be between 1 byte and 4 MiB.");
  if (!["image/jpeg", "image/png"].includes(file.type)) throw new Error("Choose a JPEG or PNG image.");
}
/** XHR supplies real browser-to-proxy byte progress. 100% is not a saved image. */
export function uploadImage(path: string, file: File, metadata: ImageUploadMetadata, token: string, progress: (value: UploadProgress) => void, signal?: AbortSignal): Promise<PreferenceImage> {
  return sendImage(path, file, metadata, imageSchema, token, progress, signal);
}
/** Binary JPEG/PNG body with percent-encoded JSON metadata; resolves only on a schema-verified response. */
export function sendImage<T>(path: string, file: File, metadata: object, schema: z.ZodType<T>, token: string, progress: (value: UploadProgress) => void, signal?: AbortSignal): Promise<T> {
  validateUpload(file);
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const abort = () => request.abort();
    const finish = (error?: Error, image?: T) => {
      signal?.removeEventListener("abort", abort);
      if (error) reject(error); else resolve(image!);
    };
    request.open("POST", `/api/v1${path}`);
    request.timeout = 120_000;
    request.setRequestHeader("Content-Type", file.type);
    request.setRequestHeader("X-CSRF-Token", token);
    request.setRequestHeader("X-Upload-Metadata", encodeURIComponent(JSON.stringify(metadata)));
    request.upload.onprogress = event => progress({stage: "uploading", percent: event.lengthComputable ? Math.floor(event.loaded / event.total * 100) : undefined});
    request.upload.onload = () => progress({stage: "processing"});
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {finish(requestError(path, request.status, request.responseText)); return;}
      try {const image = schema.parse(JSON.parse(request.responseText)); progress({stage: "saved"}); finish(undefined, image);}
      catch {finish(new Error("The save response could not be verified. Retry safely; identical images are reused."));}
    };
    request.onerror = () => finish(new Error("Connection interrupted. Retry safely; identical images are reused."));
    request.ontimeout = () => finish(new Error("Upload timed out. The image may have been saved. Retry safely to check."));
    request.onabort = () => finish(new Error("Upload cancelled. Retry safely to check whether it was saved."));
    if (signal?.aborted) {finish(new Error("Upload cancelled. Retry safely to check whether it was saved.")); return;}
    signal?.addEventListener("abort", abort, {once: true});
    progress({stage: "uploading", percent: 0});
    request.send(file);
  });
}
