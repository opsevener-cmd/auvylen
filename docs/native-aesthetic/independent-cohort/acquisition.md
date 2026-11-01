# Independent cohort acquisition decision — 2026-11-01

Continues PR #12 from ba59e842. **Decision: prepare a commissioned opt-in adult
collection; do not download a restricted collection or start recruitment.** No
new independent portraits or ratings have been acquired. No participant, vendor
or author has been contacted, no form submitted, no agreement accepted, no money
spent, and no account dataset reused. The existing London 20-person test is closed
for development: no refitting, candidate selection or augmentation tuning used it
in this iteration. A future independent holdout is not yet populated or frozen.

## Primary-source rights audit

Terms checked 2026-11-01. Numbers count independent subjects, not file variants.
An article's open-access licence is not a subject release or dataset contract.

| Candidate / primary evidence | Images and annotations | Subject / cloud / derived weights / service | Decision |
| --- | --- | --- | --- |
| [Chicago Face Database](https://www.chicagofaces.org/) | 597 main + 88 multiracial + 142 India; genuine attractiveness norms. Materials are explicitly non-commercial scientific research only. | Terms prohibit redistribution including file hosting/cloud AI services. Ages include 17, so not wholly adult. No service/derived-weight clearance supplied. | Do not ingest into this cloud project without a separate written agreement. |
| [Toronto Ethnically Diverse](https://doi.org/10.3389/fpsyg.2025.1541546), [official article](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1541546/full) | 271 models, real pose/gaze/expression variation. Validation labels concern expression recognition, intensity and genuineness; the introduction mentioning attractiveness does not establish attractiveness supervision. | Published written consent/ethics approval; dataset described as free to academic researchers. Article CC BY does not establish cloud training, weights or intended-service grants. | Useful request-for-permission lead, not usable supervised data today. Would need new genuine rating collection as well. |
| [American Multiracial Faces Database](https://jacquelinemchen.wixsite.com/sciplab/face-database) | 110 faces, neutral/smile and real observer ratings. Official page says both CC BY 4.0 and free academic research use. Access form requires agreement. | Participants were told photographs would be shared for research without identifying details. No verified service consent or cloud/weight agreement; cannot silently resolve ambiguous scope. | Potential small independent research validation lead after clarification. No form submitted; not an adequate larger collection by itself. |
| [MR2](https://ninastrohminger.com/the-mr2) | 74 images, CC BY-NC-SA 4.0. Separate image/annotation scope must be checked after approved access. | NC condition; consent for cloud ML, learned-weight licensing and service use not established by the landing page. | Not sufficiently large or cleared. |
| [London Set](../london-pilot/README.md) | Already audited CC BY images and genuine 1–7 ratings for the 100-person pilot. | Published adult lab/web-study consent supports the closed pilot, not blanket intended-service clearance. | Keep as feasibility evidence only. Alternate photos of these people cannot be independent external subjects. |

MEBeauty and SCUT remain restricted as documented in the preceding pilot audit.
A vendor's generic “commercial AI” claim is insufficient without the specific
portrait contract, source releases and annotation rights. No candidate reviewed
here currently establishes **all** required permissions plus substantially larger
independent human-rated coverage. This is a scoped finding, not a claim that no
such dataset exists anywhere.

## Acquisition route and concrete delivery specification

Prepare a statement of work for a collection partner, subject to the user's
separate approval of recruitment, budget, jurisdictions, processors and agreements.
Prefer a new consented collection over attempting to broaden older study consent.
Request **600 independently enrolled adults**, four real capture conditions each:
frontal diffuse light, modest left/right yaw (counterbalanced), and real side-lit
frontal. No generated relighting/pose substitutes. Preserve camera, session,
lighting, approximate yaw/pitch and crop provenance. Optional self-described age
band, gender and background support coverage review; never infer those from faces.
Recruit across multiple sites and ordinary appearances; no attractiveness filtering.
Use a separate recruitment site/operator for **200 external-holdout subjects**;
400 development subjects give 320 training and 80 validation. Total 2,400 images
fits the existing 3,000-image CPU pilot limit. These are targets, not achieved counts.
Start with a **60-subject development-only logistics tranche**, included in those
400, to check consent, file quality and rater burden without touching any holdout.

Request 30 independent adult human ratings per image (72,000 ratings at target),
with the original native 1–7 relative-to-average question and anchors. Randomized
presentation, repeat reliability items and attention checks must be specified
before collecting outcomes. Allow skipping; do not coerce extreme responses or
exclude a rater for disagreeing with the model. Exclude self/acquaintance ratings.
Use independent holdout raters; record their population and recruitment process.
Report rater counts, exclusions and disagreement. No machine labels or rating
inference from demographic categories. This remains subjective photographic
preference research; model validity does not establish a person's worth.

## Contract / consent acceptance checklist (separate evidence for every item)

Before accepting any delivery, require dated evidence and a named reviewer for:

1. Photograph copyright grant, allowed processors/regions/cloud training and
   transformations; subject releases confirming adults without retaining ID scans
   in the training store. A photographer licence is not a subject's consent.
2. Annotation/database licence, rater consent, paid-work terms where applicable,
   permission to aggregate and train; separate opt-in demographic data processing.
3. Permission to retain and use derived weights, research inference, and separately
   the precise intended service/commercial use. Do not imply that research consent
   grants consumer scoring. Resolve encoder-weight rights independently.
4. Retention periods, deletion/revocation channel, incident handling, processors,
   transfer locations and signed version references. No public image or individual
   score publication; any later public weight release needs its own review.
5. Adult voluntary participation; no consequential employment, credit, healthcare
   or identity decisions. Participants may refuse demographic questions or withdraw.

The draft [participant and rater procedure](participant-procedure.md) is ready for
legal/ethics and operational review, not an executed agreement. The next authorized
step is approval of that scope and budget, then operator-led recruitment or a
written vendor proposal. Do not send this document automatically.

## Freeze before any model experimentation

[protocol.json](protocol.json) is a **prospective protocol**, not a data seal.
An independent custodian must keep holdout photos, labels and the subject registry
out of developer accounts. Before fitting on the new cohort, verify consent,
adult status, genuine ratings, and no participant overlap with London, development
or other Auvylen experiments. Use consent-linked pseudonymous identity records,
not facial recognition; exact/pixel hashes alone cannot establish subject independence.

At delivery the custodian records an immutable manifest with protocol SHA-256,
collection/version, every subject/capture ID, image hashes, label-file hash,
rights/consent-version hashes, partition/site/rater-panel assignments and timestamp.
They sign or externally timestamp its digest and retain an encrypted external copy.
No holdout files or aggregate outcomes are disclosed during development. A
research-only preview must never receive external-holdout photos before final
model lock. The operator attestation alone cannot enforce that data firewall.

Select models exclusively with development/validation data; lock model, weights,
preprocessing, baselines and analysis code before the custodian opens the holdout
once. Every real capture of a person stays in the same partition. After access,
that holdout is spent for subsequent selection and must not be recycled. Record
withdrawal/exclusion versions without silently replacing a frozen test set.

## Evaluation and release decision

Pre-register train-mean/median, handcrafted ridge and MobileNet ridge candidates;
existing alpha grid .01, 1, 100; validation MAE selects one candidate. Report the
locked candidate even if a baseline wins on holdout. Report native-scale MAE,
RMSE, Spearman, paired baseline differences and 95% subject-cluster bootstrap CIs
(2,000 draws), capture-condition metrics and optional self-reported subgroup counts.
For repeated photos weight subjects equally and bootstrap subjects with all their
photos. Label sensitivity tests are not real-pose validation. Report sparse groups
as underpowered rather than claiming demographic fairness. Record rater-population
uncertainty separately from the conditional subject bootstrap.

Consumer release requires sufficient intended-use rights and an independent,
pre-registered review: both constant baselines beaten in paired MAE with the
95% upper bound below zero, positive rank association with lower CI above zero,
adequate declared subgroup/capture counts and reviewed robustness. Existing code
release checks are a minimum, not automatic scientific or legal approval. Do not
weaken them to pass a small study. **Current decision: NO-GO consumer scoring;
GO only for explicitly authorized, private Owner feasibility inspection.**
