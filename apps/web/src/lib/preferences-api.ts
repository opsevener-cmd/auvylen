import {z} from "zod";
import type {PreferenceDataset, PreferenceDetail, PreferenceImage, PreferencePair, PreferenceProject} from "@auvylen/contracts";
export const projectSchema: z.ZodType<PreferenceProject> = z.object({id: z.uuid(), name: z.string(), created_at: z.string()});
export const datasetSchema: z.ZodType<PreferenceDataset> = z.object({
  id: z.uuid(), name: z.string(), created_at: z.string(), project_id: z.uuid(),
  source: z.string(), source_url: z.string(), license: z.string(),
  rating_min: z.number().int(), rating_max: z.number().int(), archived: z.boolean(), expires_at: z.string(),
  image_count: z.number().int().nonnegative(), rated_count: z.number().int().nonnegative(), compared_count: z.number().int().nonnegative(),
});
export const imageSchema: z.ZodType<PreferenceImage> = z.object({
  id: z.uuid(), dataset_id: z.uuid(), width: z.number().int().positive(), height: z.number().int().positive(),
  subject_group: z.string().nullable(), excluded: z.boolean(), created_at: z.string(),
  score: z.number().finite().nullable(), rating_recorded: z.boolean(),
});
export const pairSchema: z.ZodType<PreferencePair> = z.object({
  id: z.uuid(), left_id: z.uuid(), right_id: z.uuid(), choice: z.enum(["left", "right", "equal", "skip"]), updated_at: z.string(),
});
export const detailSchema: z.ZodType<PreferenceDetail> = z.object({dataset: datasetSchema, images: z.array(imageSchema), pairs: z.array(pairSchema)});
export const preferencePath = "/research/preferences";
export function imageUrl(datasetId: string, imageId: string, thumbnail = false): string {
  return `/api/v1${preferencePath}/datasets/${datasetId}/images/${imageId}/content${thumbnail ? "?thumbnail=true" : ""}`;
}
export function nextPair(images: PreferenceImage[], pairs: PreferencePair[]): [PreferenceImage, PreferenceImage] | null {
  const eligible = images.filter(image => !image.excluded);
  const recorded = new Set(pairs.map(pair => [pair.left_id, pair.right_id].sort().join(":")));
  for (let left = 0; left < eligible.length; left++) {
    for (let right = left + 1; right < eligible.length; right++) {
      if (!recorded.has([eligible[left].id, eligible[right].id].sort().join(":"))) return [eligible[left], eligible[right]];
    }
  }
  return null;
}
