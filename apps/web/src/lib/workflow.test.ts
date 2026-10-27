import {describe, expect, it} from "vitest";
import type {PreferenceDataset, PreferenceImage, PreferenceProject} from "@auvylen/contracts";
import {firstPending, nextPending, ratingSummary, reachableStep, readSelection, resolveSelection, resumeStep, selectionQuery} from "./workflow";

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const image = (n: number, extra: Partial<PreferenceImage> = {}): PreferenceImage => ({id: id(n), dataset_id: id(100), width: 10, height: 10, subject_group: null, excluded: false, created_at: "2026-10-27", score: null, rating_recorded: false, purpose: "annotation", ...extra});
const project = (n: number, created = "2026-10-01"): PreferenceProject => ({id: id(n), name: `P${n}`, created_at: created});
const dataset = (n: number, projectId: string, created = "2026-10-01"): PreferenceDataset => ({id: id(n), name: `D${n}`, created_at: created, project_id: projectId, source: "s", source_url: "", license: "l", rating_min: 1, rating_max: 10, archived: false, expires_at: "2026-12-01", image_count: 0, rated_count: 0, compared_count: 0});

describe("research workflow", () => {
  it("distinguishes valid ratings from processed photographs and ignores prediction photographs", () => {
    const images = [image(1, {rating_recorded: true, score: 7}), image(2, {rating_recorded: true, score: null}), image(3, {excluded: true}), image(4), image(5, {purpose: "prediction"})];
    expect(ratingSummary(images)).toEqual({total: 4, valid: 1, skipped: 1, excluded: 1, awaiting: 1});
  });
  it("moves to the next unprocessed photograph, wrapping, and reports completion", () => {
    const images = [image(1), image(2, {rating_recorded: true, score: 3}), image(3, {excluded: true}), image(4)];
    expect(nextPending(images, 0)).toBe(3);
    expect(nextPending(images, 3)).toBe(0);
    expect(firstPending(images)).toBe(0);
    const done = images.map(item => ({...item, rating_recorded: true}));
    expect(nextPending(done, 0)).toBe(-1);
  });
  it("derives reachable and resume steps from saved data, never trusting the URL beyond it", () => {
    const d = dataset(10, id(1));
    expect(reachableStep("", undefined, null)).toBe(1);
    expect(reachableStep(id(1), undefined, null)).toBe(2);
    expect(reachableStep(id(1), d, [])).toBe(3);
    expect(reachableStep(id(1), d, [image(5, {purpose: "prediction"})])).toBe(3);
    expect(reachableStep(id(1), d, [image(1)])).toBe(4);
    expect(resumeStep(id(1), d, [image(1)], null)).toBe(4);
    expect(resumeStep(id(1), d, [image(1)], 2)).toBe(2);
    expect(resumeStep(id(1), d, [], 4)).toBe(3);
  });
  it("restores the remembered selection when valid, else the newest saved work", () => {
    const projects = [project(1), project(2, "2026-10-05")];
    const datasets = [dataset(10, id(1), "2026-10-09"), dataset(11, id(2), "2026-10-06")];
    expect(resolveSelection(readSelection(`?project=${id(2)}&dataset=${id(11)}&step=3`), projects, datasets)).toEqual({project: id(2), dataset: id(11)});
    expect(resolveSelection(readSelection("?dataset=not-a-uuid&step=9"), projects, datasets)).toEqual({project: id(1), dataset: id(10)});
    expect(resolveSelection(readSelection(""), [], [])).toEqual({project: "", dataset: ""});
    expect(readSelection("?step=9").step).toBeNull();
    expect(selectionQuery({project: id(1), dataset: "", step: 2})).toBe(`?project=${id(1)}&step=2`);
  });
});
