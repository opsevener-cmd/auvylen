# Auvylen documentation index

Start with the [repository README](../README.md) and the engineering rules in
[AGENTS.md](../AGENTS.md). Documents are grouped below by purpose. **Current reference**
documents describe how the system works today. **Historical records** are kept unchanged
as evidence of what was decided, measured or verified at the time; read their dates and
prefer a current reference when they disagree.

## Current reference

**System and boundaries**
- [Architecture](architecture.md): service boundaries (Phase 4A baseline, still in force)
- [Production and research security boundary](production-security.md)
- [Brand rename compatibility](brand-rename.md): identifiers that must not be renamed

**Accounts, Credits and commerce**
- [Accounts](accounts.md) · [Owner account and administration](owner-account.md)
- [Credit ledger](credits.md) · [Redemption codes](redemption-codes.md)
- [Payments](payments.md) · [Order lifecycle](order-lifecycle.md)

**Personal preference research**
- [Personal rating models](custom-preference-models.md)
- [Pretrained representation and licences](pretrained-representation.md) ([licence files](licenses/))
- [Research wizard UX](research-wizard-ux.md) and its [release checklist](release/research-wizard-release.md)

**Population aesthetic models** (all consumer scoring disabled)
- [Phase 6 rating-distribution model](aesthetic-scoring.md)
- [Native 1–7 model overview](native-aesthetic/README.md)
  - [Scoring milestone, model research and release roadmap](native-aesthetic/scoring-milestone/README.md) (latest)
  - [Independent evaluation plan and Owner preview](native-aesthetic/independent-cohort/README.md)
  - [London pilot](native-aesthetic/london-pilot/README.md) and its [protocol](native-aesthetic/london-pilot/protocol.md)
  - Aggregate development results: [model-research/](native-aesthetic/model-research/),
    [dev-selection-study/](native-aesthetic/dev-selection-study/)
- [ComboLoss feasibility assessment](comboloss-assessment.md) (provider remains unavailable)

**Operations**
- [Deployment](deployment.md) · [Cloud backups and restoration](cloud-backups.md)
- [Cloud-first development](cloud-development.md)
- [Private Codespaces preview](codespaces-private-preview.md) ·
  [Codespaces login Origin compatibility](codespaces-login-origin.md)
- [Face evaluation workflow](evaluation/adult-face-workflow.md) and its
  [example plan](evaluation/adult-face-plan.example.json)

## Historical records (kept unchanged as evidence)

| Date | Record |
| --- | --- |
| 2026-10-06 → 10-17 | [Verification history](verification.md) (Phase 0–3 test evidence) |
| 2026-10-12 | [Phase 3 report](phase3-report.md) |
| 2026-10-11/12 | [Phase 4A plan](phase4a.md) · [Phase 4A completion report](phase4a-report.md) |
| 2026-10-12 | [Recovery and cloud transition](recovery-cloud-transition.md) |
| 2026-10-12 | [Phase 4B master instruction](phase4b-master-instruction.md) (authorizing brief, referenced by AGENTS.md) |
| 2026-10-12 | [Phase 4B core training report](phase4b-training-report.md) |
| 2026-10-14 | [Phase 4B pretrained representation report](phase4b-representation-report.md) |
| 2026-10-14 | [Codespaces preview verification](codespaces-preview-report.md) |
| 2026-10-17 | [Phase 4B progress](phase4b-progress.md) · [Owner verification](owner-verification.md) |
| 2026-10-19 | [Phase 5 report](phase5-report.md) ([measurements and screenshots](phase5/)) |
| 2026-10-26/27 | [Phase 6 report](phase6-report.md) · [Phase 6 independent review](phase6-codex-review.md) ([benchmarks](phase6/)) |
| 2026-10-27 | Visual refresh: [overview](visual-refresh/README.md) · [premium refinement](visual-refresh/premium-refinement.md) · [final review](visual-refresh/premium-review/README.md) |
| 2026-11-01 | [Native model improvement audit](native-aesthetic/improvement-audit-2026-11-01.md) · [PR #13 independent review](native-aesthetic/pr13-independent-review.md) |
| 2026-11-11 | [Repository audit and clean-up](maintenance/2026-11-11-repository-audit.md) |

Earlier evaluation outputs on generated data live in [evaluation/](evaluation/). They are
synthetic benchmarks, never human-rating evidence.

## Conventions

- Screenshots are committed only through narrowly scoped `.gitignore` exceptions and must
  show generated fixtures, never real participants or real predictions.
- Never commit private photographs, ratings, model weights, exports or credentials. The
  repository is public.
- New phase reports belong in this index, under the matching section, with their date.
