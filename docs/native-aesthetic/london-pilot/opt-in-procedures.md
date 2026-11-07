# Next opt-in pilot: consent, independent rating and removal procedure

Prepared 2026-11-01; **not launched**. No contact, collection, spend or private account
reuse is authorized by this document. Before launch, the user must authorize scope/budget
and approve a completed study-owner/contact/hosting/retention sheet and reviewed forms.
The existing London experiment does not depend on recruiting these participants.

## Small feasibility design

Propose 60 opt-in adults, two separately consented captures each (neutral and controlled
lighting/pose variation), ten independent ratings per photograph: 1,200 real judgments.
Keep each subject's captures in one predeclared 36/12/12 subject split. This is another
feasibility study; 24 held-out pictures do not pass current release minimums. A larger,
independent release study must be separately planned. Do not fill shortfalls with generated
faces, attractiveness pseudo-labels or existing private account images/ratings.

## Contributor information and separate permissions (draft, English)

Study: Auvylen native-rating feasibility. Owner/contact, hosting jurisdiction, review date,
retention deadline and withdrawal contact must be filled before presenting this form.
Participation is voluntary; declining or withdrawing has no account/Credit consequence.
One adult will be visible in each picture. Age eligibility is established through the
approved non-image procedure, not estimated from appearance; do not store identity documents
in Auvylen. Pseudonymous subject codes link sessions; consent/contact records stay separately
protected. Do not submit someone else's portrait or a photograph whose photographer's rights
you cannot grant.

Explain, with separate unchecked acceptance fields:

- I am 18+ and am the person pictured; I understand the subjective rating task and foreseeable
  discomfort from others' opinions. Ratings do not measure objective beauty, health or worth.
- I grant the specifically identified photograph rights for the described private cloud
  research/independent rating/model-training purposes. Photographer rights are documented
  separately if another person owns them.
- I consent to this stated use of my portrait/personality and to display only to authorized
  raters/research operators, not public display, identity recognition or unrelated use.
- I understand that models may retain learned information. A later commercial service or
  public weight distribution is **not** covered by this private-pilot acceptance; those uses
  need their own explicit scope review and permissions.
- I understand the retention and withdrawal process, what will be removed, backup deletion
  timing and the limits of reversing aggregate published findings.

Do not combine contribution acceptance with marketing consent or preselect checkboxes.
Keep signed version, date, image-rights reference, subject-release reference and revocation
status in a private ledger. A checked box alone is not an external legal review.

## 中文说明草案

这是 Auvylen 原生评分模型的小规模研究试验，尚未招募参与者。参与完全自愿；拒绝或退出不会影响
账户或积分。照片仅供获授权的研究人员和独立评分者查看，用于明确说明的私有云研究和模型训练，
不公开展示，也不用于身份识别。评分反映特定评分群体的主观印象，不代表客观美感、健康或个人价值。

参与前须分别确认：本人已满十八岁且为照片中唯一的人；具备摄影作品使用授权；同意规定范围内的
肖像研究使用；了解保存期限和退出方式。研究负责人、联系方式、数据存放地区、删除期限和用途必须
填写完整。商业服务或公开发布模型权重不包含在本次私有试验授权中，不得默认勾选或合并取得同意。
退出后应停止使用相关数据，并退役、删除或重新训练受影响的模型；删除照片不等于自动从模型中遗忘。

## Independent rating workflow

Use a separate rater information/consent sheet: adult eligibility, voluntary participation,
confidential image access, no copying/re-identification/contact, annotation-use permission,
withdrawal procedure and optional demographic questions. Keep contributor/rater identities
separate from images. No rater sees model predictions, source ratings or other raters' answers.
No self-rating of contributed portraits. Randomize image order per rater and present one
portrait at a time; allow skipping without penalty. Never coerce a score or reveal a rank.

Use the predeclared native seven-point relative-to-average anchors: 1 much less attractive,
4 about average, 7 much more attractive; intermediate categories interpolate the written
anchors. The question concerns perceived photographic attractiveness, not personal value.

Authorized operators may receive independently completed CSVs with columns
`image,subject_id,rater_id,rating,rights_id,cohort`; IDs are pseudonymous. Consolidate only
after checking rater eligibility, subject consent and photographer/annotation grants.
`native_data.aggregate_annotations(..., rating_max=7)` rejects repeated rater/image votes;
`python -m aevyra_inference.native_data RAW MEANS --rating-max 7` exports genuine means/counts.
Do not mix scales. Review withheld/skip rates and rater quality without inventing labels.
Any later web delivery must use authenticated private image access, CSRF, no-store, bounded
uploads and ownership/assignment checks; this document is not a deployed collection portal.

## Removal and provenance procedure

1. Accept requests through the approved study contact. Verify the pseudonymous withdrawal
   code through the separate contact ledger; do not identify a person using facial recognition.
2. Immediately suspend affected image/rater records from assignments, exports and training.
   Record a private revocation marker so a cache or old pinned release cannot reintroduce them.
3. Remove the subject's portraits, copies, thumbnails, feature caches, labels/assignments and
   private individual predictions. For a rater request, remove their annotations and recompute
   eligible mean/counts; a picture with too few remaining independent judgments is excluded.
4. Retire all affected checkpoint versions. Deleting an image is not model unlearning:
   delete/quarantine the weights and retrain a fresh, versioned model from remaining authorized
   data before use. Keep production disabled pending re-evaluation and approval.
5. Track replicas, source-repository caches, exports and encrypted backup expiry. Preserve
   only the minimum permitted withdrawal/audit record; acknowledge completion and any lawful
   retention limits. Aggregate reports may remain only when non-identifying and permitted.
6. Never apply this process to unrelated personal datasets, account models or backups. No
   deletion or consent mutation is executed by these draft procedures.
