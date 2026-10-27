# Personal research wizard, rating completion and prediction input

Implemented on 2026-10-27 from `279afee`. It preserves the existing accounts, datasets,
ratings, models, Credits and security controls. The aesthetic scoring model is untouched
and stays disabled.

## 1. Four-step workflow

`/research/preferences` is now a wizard that shows **one active step at a time**:

1. Create project
2. Create dataset
3. Upload photographs
4. Rate photographs

- **Navigation:** a numbered step rail shows the current, completed and locked steps, with
  `aria-current="step"` on the active one. Previous and Next buttons sit at the foot of
  each step, and focus moves to the new step's heading.
- **Automatic progression:** creating a project opens step 2, and creating a dataset opens
  step 3. Uploading deliberately does *not* auto-advance, because each batch shares one
  person identifier and people often upload several batches. A prominent "Continue to
  rating" appears instead.
- **Restoration:** the chosen project, dataset and step are kept in the URL
  (`?project=&dataset=&step=`). Every value is re-validated against saved server data.
  Unknown or invalid IDs fall back to the newest saved work, and a requested step is never
  allowed beyond what the data supports. Refreshing therefore lands on the same step, or on
  the first unfinished one.
- **Revisiting:** earlier steps are always reachable and never lose data. Selecting an
  existing project or dataset is a radio choice. Dataset rename, archive, restore and
  delete live under "Manage …" in step 2.

## 2. Rating completion

- The rating view walks only through unprocessed photographs. After a save or skip it
  moves to the next unprocessed photo, wrapping round. The button reads **"Save rating"**
  on the final unrated photograph, and the next view is a **completion screen** instead of
  another "Save and next".
- **Processed is not the same as valid.** The completion screen counts valid ratings,
  skipped and excluded photographs separately. The progress line always shows
  "valid · skipped · excluded · awaiting".
- **Training eligibility comes from the server.** `GET …/datasets/{id}/readiness` runs
  exactly the checks the training request enforces: at least 8 valid ratings, 5 independent
  groups, a viable grouped split, score variation within the training split, at most 500
  ratings, and a non-archived dataset. When it reports eligible, a prominent training card
  appears. Otherwise the screen lists what remains, for example "Add 6 more valid ratings
  (2 of 8)", and offers "Upload more photographs" and "Review skipped photographs". The
  server is consulted only when eligibility can change, so a rating save remains two
  requests (CSRF token plus save).
- **Edge cases:**
  - Failed saves keep the photograph and the typed value.
  - Revising any thumbnail returns to the summary after saving.
  - Newly uploaded photos reopen the rating queue.
  - Excluding a photo or editing its group refreshes eligibility.
  - Skipped and excluded photos never count as valid.

## 3. Prediction input

The prediction card offers **Upload a new photograph** or **Choose from this dataset**.

- **New uploads** reuse the existing secure binary upload: the same session, CSRF, consent,
  decoding limits, metadata removal, quotas, retention and deletion. They are tagged
  `purpose = "prediction"` and selected automatically after the server confirms the save.
- **Prediction photographs are never rated, compared or included in any training
  snapshot.** The server enforces this in rating, pairwise comparison and snapshot
  construction, not only in the interface. A prediction photograph can be deleted directly
  from the card.
- **Duplicates:** re-uploading a photo that is already an annotation photo selects that
  existing photo and says so. Uploading a prediction-only photo again as annotation is
  refused (409), so nothing changes purpose silently.
- The dataset picker separates "Prediction photographs (never used for training)" from
  "Dataset photographs", and notes that dataset photographs may already be part of a
  model's training snapshot. The existing `seen_in_training_snapshot` result flag is
  unchanged.

## Data, migration and compatibility

- Migration `0010_image_purpose` adds `preference_images.purpose` (`annotation` or
  `prediction`) with a check constraint. It is NOT NULL with a server default of
  `annotation`, so every existing image keeps its meaning. The incremental-upgrade test
  asserts this.
- Downgrade refuses while prediction photographs exist, rather than turning them into
  training data. Back up before migrating, as usual.
- Upload metadata gains an optional `purpose` (default `annotation`); older clients keep
  working. `ImageView` gains `purpose`, and the TypeScript contracts and schemas are
  updated.

## Verification

| Check | Result |
| --- | --- |
| `uv run pytest` | 191 passed, 29 skipped (opt-in) |
| `uv run pytest --integration` (PostgreSQL + Redis) | 215 passed, 5 skipped (MobileNet weights not installed) |
| Ruff lint/format, strict mypy | Clean |
| Alembic upgrade → downgrade → upgrade on a fresh database, `alembic check` | Clean |
| `npm test` / lint / typecheck / build | 137 passed / clean / clean / built |
| Playwright default suite | 7 passed, 1 skipped (synthetic-checkpoint test) |
| Playwright synthetic aesthetic checkpoint | Passed |

New tests:
- **Backend (`test_research_workflow.py`):**
  - prediction photos cannot be rated or compared and are absent from training snapshots;
  - predictions on them report "unseen";
  - the duplicate-purpose rules;
  - readiness agrees with what the training endpoint accepts or rejects;
  - the archived dataset reason;
  - owner-only access.
- **Frontend (`workflow.test.ts`):** the valid/processed distinction, the next-pending
  order and completion, reachable and resume steps, and URL restoration.
- **Browser:**
  - `preferences.spec.ts`: the full wizard, completion, refresh restoration, revision,
    Previous navigation, archive and delete.
  - `training.spec.ts`: completion leads to a prominent training action, then prediction
    from a new upload, then upload, rate and retrain.
  - `bilingual.spec.ts`: Chinese/English, slow and partial uploads, and the two-request
    save.
  - The Docker `cloud-tests` and Codespaces `preview-tests` specs are updated to the same
    flow. The cloud specs run in CI; the preview specs were not run here.

Screenshots use generated colour fixtures and synthetic accounts only:
- Before (old page): [desktop](research-wizard/before-research-desktop-en.webp)
- Steps 1–4, English desktop: [1](research-wizard/1-project-1440-en.webp) ·
  [2](research-wizard/2-dataset-1440-en.webp) · [3](research-wizard/3-upload-1440-en.webp) ·
  [4](research-wizard/4-rating-1440-en.webp)
- Completion: [desktop](research-wizard/5-complete-1440-en.webp) ·
  [Chinese mobile](research-wizard/5-complete-390-zh-CN.webp)
- Prediction from a new upload: [desktop](research-wizard/6-predict-1440-en.webp) ·
  [Chinese mobile](research-wizard/6-predict-390-zh-CN.webp)
- Other Chinese mobile steps: [1](research-wizard/1-project-390-zh-CN.webp) ·
  [3](research-wizard/3-upload-390-zh-CN.webp) · [4](research-wizard/4-rating-390-zh-CN.webp)

## Known limitations

- Pairwise comparisons remain stored separately and still do not train the rating model.
- Prediction photographs live inside the dataset they were uploaded to and follow its
  retention. They are deleted with it.
- The MobileNet extractor paths were not exercised here because the reviewed weights are
  not installed. CI and the `--pretrained` suites cover them where weights exist.
