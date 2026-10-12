# AUVYLEN — MASTER DEVELOPMENT INSTRUCTION V2
## Cloud-First Development, Phase 4A Preservation, and Phase 4B Custom AI Scoring System

You are the principal software engineer, AI/ML engineer, and infrastructure engineer responsible for continuing the existing **Auvylen (formerly Aevyra)** project.

Your objective is to transform the existing application into a cloud-native, modular facial attractiveness research platform with a permanent custom preference-learning system and independently removable third-party scoring models.

**This is an existing software project. DO NOT rebuild it from scratch.**

---

# 1. CRITICAL CHANGE: CLOUD-FIRST DEVELOPMENT

The user does not want their personal Windows computer to operate as an application server, database server, AI inference server, or model training machine.

The user's computer should only be used for:

- Accessing Codex
- Reviewing and editing code when necessary
- Accessing the website through a browser
- Light project management

All resource-intensive operations should run remotely wherever the development environment supports it.

## Mandatory requirements

1. Prefer Codex cloud development environments for implementation, dependency installation, Docker builds, integration tests, and AI training experiments.
2. Do not start persistent Docker containers, databases, model servers, or background training processes on the user's Windows computer.
3. Do not download large facial datasets or model weights to the user's personal computer.
4. Avoid unnecessary CPU, RAM, disk, and GPU consumption on the local machine.
5. Do not require the user's computer to remain powered on for any eventual production functionality.
6. Do not use the user's computer as a public-facing server or reverse-proxy tunnel endpoint.
7. Do not purchase or provision paid services without explicit user authorization.
8. Do not assume an existing VPS, domain, GPU instance, or persistent cloud database.

### Important distinction

A Codex cloud development environment is NOT a permanent production server.

Use cloud development infrastructure for development and testing. Prepare the application for future deployment on a dedicated Linux VPS, with optional separate GPU computing resources.

If the current Codex session is running locally rather than in the cloud, do not perform resource-intensive work on the user's machine.

Instead:

- Identify the current execution environment.
- Explain whether the repository can be transferred to a Codex cloud environment.
- Prepare the necessary repository configuration.
- Give the user the exact steps required to continue in the cloud.
- Resume implementation only when the appropriate execution environment is available.

Do not silently fall back to heavy local execution.

---

# 2. RECOVER THE EXISTING PHASE 4A PROJECT

Existing project path:

`C:\Users\ChenC\Documents\ChatGPT\aevyra`

Previously reported branch:

`codex/phase4a-cloud-ready`

Important project documents:

- `docs/phase4a-report.md`
- `docs/phase4a.md`
- `docs/cloud-backups.md`

Previous Phase 4A implementation reportedly includes:

- Next.js frontend
- FastAPI backend
- PostgreSQL
- Redis
- Caddy
- Docker Compose
- Authentication and session management
- Credits and redemption codes
- Mock Analysis
- Durable asynchronous research jobs
- Research authorization
- Private artifact storage
- CPU worker infrastructure
- Modular AI provider interfaces
- Cloud deployment configuration

Migration `0004_research` reportedly exists.

Previous verification reported:

- 117 backend and infrastructure tests passed
- 27 frontend tests passed
- 2 browser regression tests passed
- 1 cloud integration flow passed
- Production builds and static analysis passed

These are historical reports, not evidence of the current execution state.

## Your first responsibility

Inspect the actual repository and verify its current state.

Identify:

- Git branch and working tree status
- Existing commits
- Untracked files
- Existing database migrations
- Existing Docker configuration
- Application architecture
- Existing tests
- Incomplete features
- Existing research subsystem contracts

Do not overwrite previous work.

## Version control and cloud migration

The earlier Phase 4A report indicated that Git initially had no commits.

Verify whether a valid baseline commit exists now.

If necessary:

1. Review all source files.
2. Verify `.gitignore` rules.
3. Exclude environment secrets, credentials, local database files, facial images, datasets, model checkpoints, logs, and generated artifacts.
4. Create a clean reviewed baseline commit.
5. Create a dedicated Phase 4B development branch.
6. Prepare the repository for a private remote Git repository.

Prefer a private repository for cloud development.

Do not push secrets or private research data.

Do not make the repository public.

If a new remote repository or external connection requires user authorization, explain the required action and ask before proceeding.

Preserve `.env.cloud.local` and existing local Docker volumes. Do not transfer secrets into the cloud development environment without an approved secure configuration mechanism.

---

# 3. INSPECT AND SAFELY STOP UNNECESSARY LOCAL SERVICES

The Phase 4A report mentioned six healthy Docker services in the local development environment.

Check whether any project-specific services are still running on the user's computer.

If they are:

- Identify the containers and project.
- Report their approximate RAM, CPU, and disk usage if measurable.
- Distinguish running resource consumption from persistent storage.
- Safely stop Auvylen-specific services when appropriate.
- Preserve all databases, Docker volumes, checkpoints, and project files.
- Do not affect unrelated Docker projects.

Never execute destructive cleanup commands such as `docker compose down -v`, Docker volume pruning, or deletion of persistent data without explicit user approval.

Do not uninstall Docker, Python, WSL, or other shared development tools.

The goal is to release unnecessary resources, not erase previous development progress.

If these checks cannot be performed safely from the available environment, provide exact non-destructive instructions instead.

---

# 4. PHASE 4B — MAIN PRODUCT OBJECTIVE

Implement a functional **Custom Facial Preference Learning System** inside the existing Auvylen website.

The user must be able to:

1. Create a custom scoring project.
2. Import authorized photographs of adult faces.
3. Organize photographs into datasets.
4. View photographs in the browser.
5. Assign personal attractiveness ratings.
6. Compare two faces and indicate a preference.
7. Save, review, and modify annotations.
8. Train a personal AI model using these annotations.
9. Save multiple versions of trained models.
10. Use a trained model to score new photographs.
11. Continue adding labels and retrain the model.
12. Compare custom-model predictions with available GitHub scoring models.

This workflow must work within the existing Auvylen website.

**Do not create a separate Auvylen Lab application.**

The user must not need to operate Python scripts or local model servers to perform ordinary website tasks.

---

# 5. PERMANENT CUSTOM SCORING SUBSYSTEM

The custom scoring subsystem is a permanent first-party feature of Auvylen.

It must NOT depend on third-party attractiveness scoring models.

In particular:

- Do not use ComboLoss predictions as ground-truth labels.
- Do not use FPEM predictions as personal preference labels.
- Do not require FACLIP or SwinGFVQA-ca to train custom models.
- Do not import third-party attractiveness models into the permanent custom-model core.
- Do not merge unrelated models into one tightly coupled implementation.

Custom models must learn from the user's own ratings or comparisons.

They may use a general-purpose pretrained image feature extractor with a verified compatible license.

Provide independent training, inference, model storage, and version management.

Deleting any external model plugin must never damage:

- Custom scoring projects
- User annotations
- Training datasets
- Trained custom models
- Model checkpoints
- Version history
- Custom inference APIs

Individual custom models may be archived or deleted by their owner, but the subsystem itself must remain available.

---

# 6. DATASET MANAGEMENT

Implement a website-based dataset manager.

Required functionality:

### Dataset creation

- Create datasets
- Rename datasets
- Organize datasets by project
- Record source and license metadata
- Display image counts and annotation progress
- Archive or delete datasets

### Image handling

- Multiple-image upload
- Thumbnail previews
- Image selection and exclusion
- Duplicate detection using cryptographic hashes
- Safe decoding and validation
- Image-size limits
- Private persistent storage
- Ownership-based authorization
- Explicit deletion and retention controls

### Dataset provenance

Store relevant metadata:

- Dataset name
- Source
- Source URL
- License and restrictions
- Import date
- Image identifier
- Person/group identifier when provided
- Annotation eligibility

Do not automatically download entire third-party datasets.

Prepare a modular dataset importer, but require license and access checks before actual downloads.

Prioritize research datasets suitable for adult facial attractiveness annotation, such as the Face Research Lab London Set and Chicago Face Database, subject to their actual permissions.

No real facial photographs should be committed to Git.

Do not send private facial images to external inference APIs without explicit authorization.

---

# 7. PERSONAL PREFERENCE ANNOTATION

Create a user-friendly annotation interface with two modes.

## Mode A — Absolute rating

Allow the user to rate each image on a configurable numerical scale.

Default:

1–10

Features:

- One image at a time
- Numerical rating slider or equivalent control
- Save and next
- Skip
- Previous image
- Edit previous rating
- Remaining-image counter
- Annotation progress
- Resume interrupted sessions

The score represents the user's subjective facial attractiveness judgment, not objective beauty.

## Mode B — Pairwise comparison

Display two photographs simultaneously.

Available choices:

- Left preferred
- Right preferred
- Equal preference
- Skip

Persist comparisons and avoid unnecessary duplicate pairs.

Do not treat selecting or uploading a photograph as an attractiveness label.

Support both rating and pairwise annotation records without incorrectly assuming they share the same numerical scale.

---

# 8. REAL AI TRAINING

Implement genuine machine-learning functionality.

The minimum required workflow is:

**Annotated images → visual feature extraction → preference model training → model checkpoint → unseen-image prediction**

## Preferred initial architecture

Use:

- A frozen general-purpose visual feature extractor
- Cached image embeddings
- A regularized regression model for numerical scores
- A separate pairwise ranking model for relative preferences

Avoid training a large neural network from scratch with only a few hundred labeled photographs.

The feature extractor must be technically compatible and independently licensed.

Verify the license of both source code and pretrained weights.

Do not select an extractor solely because a GitHub repository is publicly accessible.

If an appropriate extractor cannot be installed in the cloud environment, report the blocker.

A simple reproducible baseline may be implemented, but it must be identified accurately and must not produce fabricated predictions.

## Training functionality

Implement:

- Asynchronous training jobs
- Training status and progress
- Safe job cancellation
- Retry handling
- Worker lease renewal for long jobs
- Training logs
- Checkpoint persistence
- Training configuration
- Random seeds
- Model version history

Do not block FastAPI request handling during model training.

Do not make GPU hardware mandatory for the initial implementation.

Ensure the model-training code can later run in a separate GPU worker container.

---

# 9. MODEL ACCURACY AND VALIDATION

Use reproducible training and validation splits.

If multiple images belong to the same person, keep them grouped to prevent identity leakage across training and validation sets.

Report:

- Number of labeled photographs
- Number of unique people when known
- Training set size
- Validation set size
- Numerical validation MAE where applicable
- Pairwise validation accuracy where applicable
- Model version
- Training parameters
- Training duration
- Inference latency

Do not claim reliable accuracy when the dataset is insufficient.

Do not generate population percentiles without an appropriately validated reference population.

Do not interpret the numerical difference between independently trained scoring models as meaningful without calibration.

Preserve the user's original annotations independently of the trained models.

---

# 10. GITHUB SCORING PLUGINS

Prepare independent providers for:

- ComboLoss
- FPEM
- FACLIP
- SwinGFVQA-ca

Each provider must have:

- Independent adapter
- Isolated dependencies where necessary
- Model configuration
- Checkpoint manifest
- Explicit availability status
- Stable inference contract
- Enable/disable control
- Safe removal procedure

Keep third-party model weights out of the main source repository.

Do not download large checkpoints to the user's Windows computer.

Install and validate third-party models only in an appropriate remote environment.

If a model cannot be installed or its weight license cannot be verified, mark it unavailable.

Do not substitute mocked outputs for unavailable models.

The custom-model system must function even when all third-party providers are removed.

---

# 11. UNIFIED SCORING INTERFACE

Design a shared inference contract that can return:

- Model ID
- Model version
- Provider
- Input image ID
- Prediction score
- Score scale
- Prediction type
- Processing status
- Processing duration
- Applicable metadata
- Error information when appropriate

The frontend should allow a user to select available models and compare their outputs independently.

Do not automatically average incompatible predictions.

The user should be able to select:

- A custom model
- Multiple custom model versions
- One or more available GitHub models

Unavailable providers must display an accurate status.

---

# 12. CLOUD STORAGE AND SERVER PORTABILITY

Keep the existing Next.js, FastAPI, PostgreSQL, Redis, Caddy, and Docker architecture wherever appropriate.

Separate these components:

1. Web frontend
2. API backend
3. PostgreSQL database
4. Redis and job coordination
5. Private image storage
6. Model checkpoint storage
7. CPU training/inference worker
8. Optional future GPU worker
9. External scoring provider containers

All persistent data must survive application restarts and container recreation.

Prepare environment-based configuration and future migration to an S3-compatible object storage system if needed.

Do not use hardcoded Windows paths for production components.

Do not depend on the continued existence of a temporary Codex workspace for production data persistence.

Document how application code, database state, image storage, annotations, and trained model artifacts would be backed up and migrated separately.

---

# 13. CURRENT EXECUTION AND COST RESTRICTIONS

There is no purchased VPS and no approved paid GPU service.

Therefore:

- Do not purchase infrastructure.
- Do not create paid cloud resources.
- Do not make public production deployments.
- Do not require a domain name.
- Do not store essential private data exclusively in ephemeral development environments.
- Do not rely on the user's computer as a fallback server.
- Do not run unnecessary large-scale model training.

Use small synthetic or appropriately licensed test datasets for integration testing.

If the available cloud development environment has resource limitations, identify them explicitly.

Document what requires a persistent server later.

---

# 14. RESEARCH MODE AND LEGACY FUNCTIONALITY

Preserve:

- Authentication
- Sessions
- Credits
- Redemption codes
- Existing database migrations
- Existing payment-related architecture
- Previous Phase 4A research infrastructure

The current priority is non-commercial research.

Authorized research operations should not deduct Credits.

Do not implement new payment gateways, billing flows, or monetization features.

Preserve existing Credits data and accounting invariants.

Research mode must not bypass access control, upload limits, resource quotas, or ownership checks.

---

# 15. IMPLEMENTATION SEQUENCE

Execute development in the following order.

## Step 1 — Recovery and cloud transition

- Inspect Phase 4A
- Confirm Git state
- Secure existing files and secrets
- Prepare a private remote repository workflow
- Establish a cloud-compatible development workflow
- Avoid heavy local execution

## Step 2 — Dataset and annotation features

- Add database migrations
- Implement dataset APIs
- Implement private image storage
- Build image upload UI
- Implement numerical ratings
- Implement pairwise comparisons
- Verify persistence and authorization

## Step 3 — First functional custom model

- Select and verify a suitable feature extractor
- Implement embedding extraction
- Implement genuine rating-based training
- Save checkpoint and metadata
- Implement inference
- Display predictions in the existing website

## Step 4 — Model management

- Custom model registry
- Model versions
- Active model selection
- Retraining
- Training status
- Model deletion/archive functionality

## Step 5 — Third-party model integration foundation

- Validate provider isolation
- Retain independent GitHub plugin slots
- Ensure external plugin removal cannot affect personal models
- Document actual dependencies and weight requirements

## Step 6 — Cloud deployment preparation

- Validate deployment portability
- Prepare Ubuntu deployment documentation
- Describe backup and restoration
- Estimate memory, disk and CPU requirements
- Document optional GPU deployment
- Identify actual infrastructure requirements

Do not wait for a VPS purchase before implementing features that can safely be developed and tested in the cloud environment.

Do not claim completion for any unimplemented step.

If execution must stop because cloud access or credentials are unavailable, provide the exact blocker and next user action.

---

# 16. REQUIRED TESTS

Run tests in the available remote development environment.

At minimum, verify:

1. Existing Phase 4A features remain functional.
2. Existing Credits and redemption behavior is preserved.
3. Dataset creation works.
4. Image import works.
5. Annotations persist.
6. A real training job can finish.
7. A valid model artifact is generated.
8. A new image can be scored by the trained model.
9. Model artifacts survive supported restart/redeployment scenarios.
10. Dataset isolation and authorization work.
11. Unavailable GitHub providers return errors rather than fabricated results.
12. Disabling external providers does not affect the custom scoring subsystem.
13. No research scoring operation accidentally deducts Credits.
14. Private image files cannot be accessed through public static paths.

Use synthetic test images where possible.

Run existing backend/frontend regressions, linting, type checking and production builds when supported.

Clearly distinguish tests actually executed from tests only documented.

---

# 17. FINAL DELIVERABLES

Provide a detailed implementation report containing:

### A. Project recovery

- Actual repository state
- Current Git branch and commits
- Confirmed Phase 4A functionality
- Changes made
- Preservation of previous data

### B. Cloud development transition

- Current execution environment
- Whether development is running locally or remotely
- Any remaining dependency on the user's computer
- Resource usage and limitations
- Remote repository status
- Any user action required to enable cloud development

### C. Implemented features

- Database migrations
- API routes
- Frontend pages
- Dataset management
- Annotation functionality
- Custom training algorithm
- Checkpoint persistence
- Model registry
- Prediction functionality
- External model provider status

### D. Testing

- Actual test commands
- Pass/fail counts
- End-to-end workflow results
- Any unresolved errors

### E. Cloud deployment readiness

- Recommended minimum CPU/RAM/storage
- Expected AI training resource requirements
- Potential GPU requirements
- Estimated persistent storage needs
- Backup and restoration procedure
- Pending cloud deployment requirements

### F. Outstanding work

Distinguish clearly between:

- Implemented and tested
- Implemented but unverified
- Partially implemented
- Not implemented
- Blocked by unavailable infrastructure or credentials

---

# 18. FINAL INSTRUCTION

The primary goal is to deliver a functional custom AI scoring capability inside the EXISTING Auvylen website while minimizing resource consumption on the user's personal computer.

Do not rebuild the project.

Do not create another standalone local application.

Do not prioritize commercial features.

Do not purchase cloud infrastructure.

Do not claim cloud hosting is complete when only a temporary development environment exists.

**Preserve Phase 4A, transition development toward the cloud, and implement the Phase 4B custom AI preference-learning workflow.**

Begin by auditing the actual repository and current execution environment.

If cloud development access is not yet available, complete only the safe preparation steps and clearly explain how to continue remotely before performing resource-intensive implementation or testing.

Otherwise, proceed with implementation, run the available tests, and provide the final engineering report.