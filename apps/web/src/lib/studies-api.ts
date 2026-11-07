import {z} from "zod";
import type {CollectionStudy, StudyAssignment, StudyExport, StudyPhoto} from "@auvylen/contracts";
export const studiesPath = "/research/studies";
const member = z.object({id: z.uuid(), role: z.string(), approved: z.boolean(), active: z.boolean(), verification_reference: z.string().nullable()});
export const studyPhotoSchema: z.ZodType<StudyPhoto> = z.object({id: z.uuid(), review: z.string(), pose: z.string(), lighting: z.string(), rating_count: z.number().int().nonnegative(), created_at: z.string()});
export const studySchema: z.ZodType<CollectionStudy> = z.object({id: z.uuid(), title: z.string(), partition: z.enum(["development", "holdout"]), status: z.string(), fixture_only: z.boolean(), retention_days: z.number().int(), can_manage: z.boolean(), can_administer: z.boolean(), consent: z.object({id: z.uuid(), version: z.number().int(), sha256: z.string(), text_en: z.string(), text_zh: z.string(), contact_en: z.string(), contact_zh: z.string(), rights_reference: z.string(), created_at: z.string()}).nullable(), memberships: z.array(member), members: z.array(member), photos: z.array(studyPhotoSchema), seal_sha256: z.string().nullable(), revision: z.number().int(), photo_count: z.number().int(), rating_count: z.number().int()});
export const studyAssignmentSchema: z.ZodType<StudyAssignment> = z.object({id: z.uuid(), expires_at: z.string(), not_before: z.string()});
export const studyExportSchema: z.ZodType<StudyExport> = z.object({id: z.uuid(), status: z.string(), sha256: z.string(), images: z.number().int(), subjects: z.number().int(), expires_at: z.string()});
export const studyStatusSchema = z.object({enabled: z.boolean(), real_collection_enabled: z.boolean(), owner: z.boolean(), consumer_scoring_enabled: z.literal(false)});
export const studyErrors: Record<string, string> = {
  study_disabled: "Research collection is disabled. No participant data can be collected.",
  study_fixture_only: "This environment accepts authorized test fixtures only. Do not submit a real participant portrait.",
  study_real_paused: "Real collection is paused. Withdrawal is still available.",
  study_not_found: "This study item is unavailable or you do not have access.",
  study_custody_required: "This action requires the study's independent custodian. Owner privileges do not unlock holdout data.",
  study_custodian_required: "Choose an independent custodian account and ask them to accept the study consent before opening.",
  study_partition_locked: "This account already belongs to the other research partition. People cannot move between development and holdout studies.",
  study_member_approval_required: "Staff must verify your study participation before you can upload or rate.",
  study_consent_required: "Publish and read a consent version before opening this study.",
  study_consent_changed: "The consent version changed. Read the latest version and consent again before continuing.",
  study_closed: "This study is not collecting now. Your withdrawal controls remain available.",
  study_sealed: "This holdout is frozen. Collection cannot resume or be silently redefined.",
  study_seal_requires_closed_holdout: "Only the independent custodian can seal a closed holdout study.",
  study_invite_invalid: "This private invitation is invalid, rotated or no longer accepting participants.",
  study_invite_already_issued: "That invitation was already issued. Rotate it to create a new code.",
  study_withdrawn: "You have withdrawn from this study. Your images and ratings cannot be reactivated.",
  study_fresh_signin: "A recent sign-in is required for study administration. Sign in again and retry.",
  study_request_conflict: "This request conflicts with a previous action. Refresh the study and try again.",
  study_duplicate_image: "This photograph is already present. Duplicate pictures cannot add independent evidence.",
  study_duplicate_person: "The verification reference is already linked to another person or differs from this person's existing reference.",
  study_image_format: "Choose a JPEG or PNG image.",
  study_image_size: "Use a JPEG or PNG up to 4 MiB and 4096 pixels, with a shorter side of at least 224 pixels.",
  study_upload_attestation: "Confirm that this is your own authorized adult portrait and complete the capture details.",
  study_image_integrity: "The private image failed integrity verification. Contact the study operator.",
  study_assignment_expired: "This assignment expired or is no longer eligible. Request the next portrait.",
  study_rating_required: "Choose one rating from 1 to 7, or skip the portrait.",
  study_too_fast: "View the portrait for at least two seconds before saving your rating.",
  study_busy: "Image processing is busy. Wait a moment and retry the same request.",
  study_limit: "The study resource limit has been reached. Contact the operator.",
  study_holdout_not_exportable: "Independent holdout images and labels cannot enter a development export.",
  study_export_close_first: "Close the development study before creating a stable export.",
  study_no_eligible_data: "No approved portraits have three independent eligible ratings yet.",
  study_export_revoked: "This export expired or was revoked. Downloaded copies must not be used.",
  study_export_integrity: "The export failed integrity verification.",
  study_export_limit: "The export exceeds the 64 MiB safety limit. Use a smaller approved study.",
};
