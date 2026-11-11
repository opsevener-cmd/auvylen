# Repository audit and clean-up — 2026-11-11

Scope: every branch and full history of `opsevener-cmd/auvylen`, with the development branch
`codex/phase4b-custom-preferences` at `8017651`. No history was rewritten, no remote branch
was deleted and no repository setting was changed; those need Owner approval (§4).

## 1. Findings

| Area | Result |
| --- | --- |
| Secrets in history (all branches) | **None found.** Scanned for GitHub/OpenAI/AWS/Slack/Google key formats and private-key headers. `.env.*.example` files contain placeholders and documented local/CI-only values. |
| Private data | None tracked. Committed images are reviewed generated fixtures or artwork with per-file `.gitignore` exceptions. The `dump.rdb` incident (2026-10-31) is documented in `release/research-wizard-release.md`; its contents were non-sensitive. |
| Size | 473 tracked files on the development branch; packed history 2.5 MiB; largest file 312 KB (a screenshot). **No size problem.** |
| Junk/temporary files | None: no backup, swap, log, notebook-checkpoint or OS files tracked. The three empty `py.typed` files are intentional PEP 561 markers. |
| Tracked-but-ignored files | None. |
| Broken relative Markdown links | None across 53 Markdown files. |
| Unreferenced code | None that is dead. `scripts/benchmark-aesthetic.py` has no inbound reference but is the documented generator of `docs/phase6/cpu-benchmark.json`; kept. |
| Documentation | About 40 Markdown files flat in `docs/` with no index, mixing current references with superseded phase reports. Main clarity problem. |
| `.gitignore` | No duplicates. Missing two common editor/notebook patterns. |
| Default branch | `codex/phase4a-cloud-ready`: 68 commits behind development, plus a stray commit `f16b484` adding a one-line file `u`. Public visitors see stale code. |
| Unrelated branch | `public-cf-node-diagnostics-20261110`: Cloudflare Workers VLESS proxy diagnostics, unrelated to Auvylen. Credentials are placeholders; no secret committed. |

## 2. Changes in this clean-up

- Added [`docs/README.md`](../README.md): a categorized index separating current reference
  from historical records. **No document was moved or rewritten.** Moving them would break
  inbound links (`AGENTS.md`, `README.md`, CI comments, `.env` templates, other documents)
  and external links, for little benefit.
- `README.md`: the structure block now points to the docs index and lists `scripts/`. One
  paragraph now notes the merged native 1–7 Owner research preview, linking existing docs.
- `.gitignore`: added `.ipynb_checkpoints/` and editor swap files (`*.swp`, `*.swo`).
- This audit record.

Not changed: application code, algorithms, model behaviour, migrations, tests, CI,
deployment files, `AGENTS.md`.

## 3. Branch inventory (2026-11-11)

**Fully merged into the development branch** (safe to delete after approval; history is
retained in the development branch):
`codex/owner-god-provisioning`, `codex/codespaces-ingress-headers`,
`codex/codespaces-login-origin`, `codex/phase5-bilingual-ux-performance`,
`codex/phase6-aesthetic-scoring`, `codex/premium-ui-refinement`, `codex/research-wizard-ux`,
`codex/visual-editorial-portraits`, `codex/fix-research-upload-model-deletion`,
`codex/research-wizard-release`, `claude/native-preview-hardening`,
`codex/auvylen-native-aesthetic-v1`, `claude/native-scoring-milestone`.

**Open work (keep):**

| Branch | State |
| --- | --- |
| `codex/phase7a-consented-studies` | PR #14; 7 commits ahead of development, 0 behind; includes merged PR #16 |
| `codex/scoring-phase7a-integration` | Codex integration verification branch; superseded by `e3a6d2a` on the Phase 7A branch once reviewed |
| `claude/phase7a-codesign` | Merged into the Phase 7A branch (PR #16); deletable after PR #14 merges |
| `claude/phase7b-gpu-pipeline` | Paused Phase 7B pipeline, 1 commit ahead |
| `codex/pretrained-comboloss` | PR #11, unmerged draft, kept by explicit instruction |

## 4. Recommendations needing Owner approval

1. **Change the default branch** to `codex/phase4b-custom-preferences` (GitHub Settings →
   Branches). This also hides the stray `u` file from the default view; delete
   `codex/phase4a-cloud-ready` afterwards or keep it as an archive.
2. **Move or delete `public-cf-node-diagnostics-20261110`**: it is unrelated to Auvylen and is
   publicly visible under the project.
3. **Delete the 13 merged branches** listed above.
4. **Resolve repository visibility** before any real participant data (currently public).
5. **Update `AGENTS.md` scope wording**: it still says "Current scope is Phase 4B". It is the
   governing rules file, so its owners should edit it rather than a clean-up PR.
