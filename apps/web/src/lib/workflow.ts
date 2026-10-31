import type {PreferenceDataset, PreferenceImage, PreferenceProject, ReadinessReason, TrainingReadiness} from "@auvylen/contracts";

/** The four research steps. Progress is always derived from saved server data. */
export type Step = 1 | 2 | 3 | 4;
export const steps: {step: Step; label: string}[] = [
  {step: 1, label: "Create project"},
  {step: 2, label: "Create dataset"},
  {step: 3, label: "Upload photographs"},
  {step: 4, label: "Rate photographs"},
];

export const annotationImages = (images: PreferenceImage[]) => images.filter(image => image.purpose !== "prediction");
export const predictionImages = (images: PreferenceImage[]) => images.filter(image => image.purpose === "prediction");
const pending = (image: PreferenceImage) => image.purpose !== "prediction" && !image.excluded && !image.rating_recorded;

export type RatingSummary = {total: number; valid: number; skipped: number; excluded: number; awaiting: number};
/** "Processed" (rated or skipped) is distinct from "valid" (a numerical rating training can use). */
export function ratingSummary(images: PreferenceImage[]): RatingSummary {
  const annotation = annotationImages(images);
  return {
    total: annotation.length,
    valid: annotation.filter(image => !image.excluded && image.rating_recorded && image.score !== null).length,
    skipped: annotation.filter(image => !image.excluded && image.rating_recorded && image.score === null).length,
    excluded: annotation.filter(image => image.excluded).length,
    awaiting: annotation.filter(pending).length,
  };
}

/** Next unprocessed annotation photograph after `from`, wrapping once; -1 when every photo is processed. */
export function nextPending(images: PreferenceImage[], from: number): number {
  for (let offset = 1; offset <= images.length; offset++) {
    const index = (from + offset) % images.length;
    if (pending(images[index])) return index;
  }
  return -1;
}
export const firstPending = (images: PreferenceImage[]) => nextPending(images, images.length - 1);

export type Selection = {project: string; dataset: string; step: Step | null};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
/** URL parameters only remember choices; every value is re-validated against server data. */
export function readSelection(search: string): Selection {
  const params = new URLSearchParams(search);
  const step = Number(params.get("step"));
  const id = (name: string) => uuid.test(params.get(name) ?? "") ? params.get(name)! : "";
  return {project: id("project"), dataset: id("dataset"), step: Number.isInteger(step) && step >= 1 && step <= 4 ? step as Step : null};
}
export function selectionQuery({project, dataset, step}: Selection): string {
  const params = new URLSearchParams();
  if (project) params.set("project", project);
  if (dataset) params.set("dataset", dataset);
  if (step) params.set("step", String(step));
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** Choose a valid project/dataset: the remembered one if it still exists, else the most recent. */
export function resolveSelection(selection: Selection, projects: PreferenceProject[], datasets: PreferenceDataset[]): {project: string; dataset: string} {
  const byNewest = <T extends {created_at: string}>(items: T[]) => [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const remembered = datasets.find(item => item.id === selection.dataset);
  const project = remembered?.project_id ?? (projects.some(item => item.id === selection.project) ? selection.project : byNewest(datasets)[0]?.project_id ?? byNewest(projects)[0]?.id ?? "");
  const dataset = remembered?.id ?? byNewest(datasets.filter(item => item.project_id === project))[0]?.id ?? "";
  return {project, dataset};
}

/** Highest step the user may open, given saved data. Earlier steps always stay reachable. */
export function reachableStep(project: string, dataset: PreferenceDataset | undefined, images: PreferenceImage[] | null): Step {
  if (!project) return 1;
  if (!dataset) return 2;
  if (!images || annotationImages(images).length === 0) return 3;
  return 4;
}
/** Where a returning user should land: the first step that still needs work. */
export function resumeStep(project: string, dataset: PreferenceDataset | undefined, images: PreferenceImage[] | null, requested: Step | null): Step {
  const reachable = reachableStep(project, dataset, images);
  return requested && requested <= reachable ? requested : reachable;
}

/** Changes whenever any valid score changes, so eligibility (e.g. score variation) is re-checked. */
export function ratingSignature(images: PreferenceImage[]): string {
  return annotationImages(images).filter(image => !image.excluded && image.score !== null).map(image => `${image.id}:${image.score}`).sort().join("|");
}

/** One wording per server reason, shared by the completion screen and the training form. */
export const readinessText: Record<ReadinessReason, string> = {
  archived: "Restore this archived dataset before training.",
  too_few_ratings: "Add {count} more valid ratings ({rated} of {required}). Skipped and excluded photographs do not count.",
  too_few_groups: "Use at least {groups} different person/group identifiers ({current} so far); photographs of one person count once.",
  insufficient_split: "The validation split leaves too few training photographs. Add ratings for more people.",
  no_score_variation: "Training ratings need at least two different scores.",
  too_many_ratings: "A version supports at most 500 rated photographs. Exclude some photographs.",
};
/** `valid` is the locally saved count, which is never older than the last server answer. */
export function readinessMessages(readiness: TrainingReadiness, valid: number): {key: string; values: Record<string, number>}[] {
  return readiness.reasons.map(reason => ({key: readinessText[reason], values: {
    count: Math.max(0, readiness.required_ratings - valid), rated: valid, required: readiness.required_ratings,
    groups: readiness.required_groups, current: readiness.groups,
  }}));
}
