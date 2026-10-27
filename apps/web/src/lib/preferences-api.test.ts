import {describe, expect, it} from "vitest";
import type {PreferenceImage, PreferencePair} from "@auvylen/contracts";
import {allowedApiPath} from "./api-proxy-policy";
import {imageUrl, nextPair} from "./preferences-api";

const ids = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002", "00000000-0000-0000-0000-000000000003"];
const images: PreferenceImage[] = ids.map(id => ({id, dataset_id: ids[0], width: 100, height: 100, subject_group: null, excluded: false, created_at: "2026-10-12", score: null, rating_recorded: false, purpose: "annotation" as const}));
describe("private preferences", () => {
  it("selects unseen canonical pairs and preserves skipped pairs on resume", () => {
    expect(nextPair(images, [])?.map(i => i.id)).toEqual(ids.slice(0, 2));
    const pairs: PreferencePair[] = [{id: ids[0], left_id: ids[1], right_id: ids[0], choice: "skip", updated_at: "2026-10-12"}];
    expect(nextPair(images, pairs)?.map(i => i.id)).toEqual([ids[0], ids[2]]);
    const withPrediction = images.map((image, index) => index === 2 ? {...image, purpose: "prediction" as const} : image);
    expect(nextPair(withPrediction, pairs)).toBeNull(); // Prediction photographs are never compared.
    expect(nextPair(images.slice(0, 2), pairs)).toBeNull();
    expect(nextPair(images.map((image, i) => ({...image, excluded: i !== 0})), [])).toBeNull();
  });
  it("only permits explicit research and account routes through the same-origin proxy", () => {
    const root = `v1/research/preferences/datasets/${ids[0]}`;
    for (const path of ["v1/auth/me", "v1/research/status", "v1/research/jobs", "v1/research/preferences/projects", root, `${root}/edit`, `${root}/pairs`, `${root}/images`, `${root}/images/${ids[1]}/content`, `${root}/images/${ids[1]}/delete`]) expect(allowedApiPath(path), path).toBe(true);
    for (const path of ["v1/research/operator", "v1/research/preferences/../../auth/me", `${root}/weights`, `${root}/images/${ids[1]}/unknown`, "https://evil.test/", "v1/research/preferences/datasets/not-a-uuid", "v1/research/status/extra"]) expect(allowedApiPath(path), path).toBe(false);
  });
  it("addresses private content without using the image optimizer", () => {
    expect(imageUrl(ids[0], ids[1], true)).toBe(`/api/v1/research/preferences/datasets/${ids[0]}/images/${ids[1]}/content?thumbnail=true`);
  });
});
