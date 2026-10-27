import {afterEach, describe, expect, it, vi} from "vitest";
import {uploadImage, validateUpload, type UploadProgress} from "./upload";
const id = "00000000-0000-4000-8000-000000000001";
const saved = {id, dataset_id: id, width: 100, height: 80, subject_group: null, excluded: false, score: null, rating_recorded: false, created_at: "2026-10-18", purpose: "annotation"};
class Transport {
  static latest: Transport;
  headers: Record<string, string> = {};
  upload: {onprogress?: (event: {loaded: number; total: number; lengthComputable: boolean}) => void; onload?: () => void} = {};
  status = 200;
  responseText = JSON.stringify(saved);
  timeout = 0;
  sent?: File;
  onload?: () => void;
  onerror?: () => void;
  ontimeout?: () => void;
  onabort?: () => void;
  constructor() {Transport.latest = this;}
  open = vi.fn();
  setRequestHeader(name: string, value: string) {this.headers[name] = value;}
  send(file: File) {this.sent = file;}
  abort() {this.onabort?.();}
}
function begin() {
  vi.stubGlobal("XMLHttpRequest", Transport);
  const file = new File(["synthetic test fixture"], "fixture.png", {type: "image/png"});
  const progress: UploadProgress[] = [];
  const promise = uploadImage(`/research/preferences/datasets/${id}/images`, file, {adult_authorized_consent: true, subject_group: "人物-01"}, "test-csrf", value => progress.push(value));
  return {promise, progress, file, request: Transport.latest};
}
afterEach(() => vi.unstubAllGlobals());
describe("binary private uploads", () => {
  it("sends the File with CSRF and Unicode metadata and waits for a verified save", async () => {
    const {promise, progress, file, request} = begin();
    expect(request.sent).toBe(file);
    expect(request.headers["X-CSRF-Token"]).toBe("test-csrf");
    expect(JSON.parse(decodeURIComponent(request.headers["X-Upload-Metadata"]))).toEqual({adult_authorized_consent: true, subject_group: "人物-01"});
    request.upload.onprogress?.({loaded: 45, total: 100, lengthComputable: true});
    expect(progress.at(-1)).toEqual({stage: "uploading", percent: 45});
    request.upload.onprogress?.({loaded: 100, total: 100, lengthComputable: true});
    request.upload.onload?.();
    expect(progress.at(-1)).toEqual({stage: "processing"});
    expect(progress.some(p => p.stage === "saved")).toBe(false);
    request.onload?.();
    expect(await promise).toEqual(saved);
    expect(progress.at(-1)).toEqual({stage: "saved"});
  });
  it.each(["network", "timeout", "server", "invalid-response"])("rejects %s without a false saved event", async failure => {
    const {promise, progress, request} = begin();
    const result = expect(promise).rejects.toBeInstanceOf(Error);
    if (failure === "network") request.onerror?.();
    else if (failure === "timeout") request.ontimeout?.();
    else {if (failure === "server") request.status = 503; else request.responseText = "{}"; request.onload?.();}
    await result;
    expect(progress.some(p => p.stage === "saved")).toBe(false);
  });
  it("does not invent progress when the transport cannot measure it", async () => {
    const {promise, progress, request} = begin();
    request.upload.onprogress?.({loaded: 0, total: 0, lengthComputable: false});
    expect(progress.at(-1)).toEqual({stage: "uploading", percent: undefined});
    request.onload?.(); await promise;
  });
  it("rejects empty, oversized and unsupported files before transmission", () => {
    for (const file of [new File([], "empty.png", {type: "image/png"}), new File([new Uint8Array(4 * 1024 * 1024 + 1)], "large.png", {type: "image/png"}), new File(["gif"], "photo.gif", {type: "image/gif"})]) expect(() => validateUpload(file)).toThrow();
  });
});
