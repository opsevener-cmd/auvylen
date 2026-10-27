# Independent premium refinement review — 2026-10-27

Claude's original `862089796c985e5286ab808614c4cc7703010027` is preserved as an
ancestor, directly after PR #6's `8466176fa9d41a617382a3da90ddf232fb3d91ec`.
The supplied bundle and patch both matched SHA-256 checksums; `git bundle verify`
passed. The bundle was imported without applying the fallback patch. All 25 files
in Claude's commit remain; there were no deleted files or unrelated backend changes.
His [report and original before/after evidence](../premium-refinement.md) are preserved.

## Review findings and resulting design

The paper/ink/moss palette, Cormorant display typography, architectural split hero,
ruled chapters and spacious guide form a coherent editorial system. Copy stays on
solid backgrounds; disclosures sit below photographs. Signed-in account, research
and result screens inherit the same system. These choices were retained.

The independent review corrected four concrete issues:

- Brass used for small labels had 3.11:1 contrast on paper. A separate brass text
  token now gives 5.04:1; the original lighter brass remains for decoration.
- Input outlines had only 2.04:1 contrast against their surface. Control borders
  now give 3.48:1, and keyboard focus has an explicit 2px moss outline.
- The native file control supplied browser-dependent English text in Chinese.
  A localized label now presents the native, keyboard-focusable file input, visible
  focus and the selected filename. Switching languages preserves the file.
- Image `sizes` still described the old, wider PR #6 layout. They now match the
  refined columns. The italic font is separate and not preloaded: Chinese pages
  use upright accents and request only the normal subset. Serif fallback metrics
  also replace the default Arial metrics. Reduced motion removes hover zoom.

These are presentation changes. Upload transport, consent, validation, scoring,
authentication, authorization, private image delivery and deletion logic are unchanged.

## Image decisions

Both hero compositions were generated/rendered in the same imported layout before
choosing. The single adult in a colonnade is elegant, but reads more like a fashion
campaign. The existing four-person scene communicates a broader range of adult
appearances and a shared study of personal aesthetics. **Keep the four-person hero.**
Its mobile crop keeps all four faces. The unused single-subject source is not shipped.

| Composition | Desktop | Chinese mobile |
| --- | --- | --- |
| Four-person hero, retained | [Compare](comparison-group-desktop.webp) | [Compare](comparison-group-mobile.webp) |
| Generated single-subject candidate | [Compare](comparison-single-desktop.webp) | [Compare](comparison-single-mobile.webp) |

Claude's other image recommendations were assessed individually:

| Section | Result | Reason |
| --- | --- | --- |
| Homepage hero `/` | Original four fictional adults retained | Inclusive group composition fits the product and the architecture. |
| Introduction `/#guide` | New original still life: architectural prints, brass loupe, pencil, linen and olive | A quiet visual pause that suggests observation without repeating another group portrait. |
| Analysis `/research/aesthetic` | Re-generated lighting/composition using only the existing generated pair as reference | Plainer wall, controlled directional light, portrait framing and proper headroom; dedicated landscape mobile crop. |
| Privacy band | Existing CSS treatment retained | Another texture image added little visual value or information. |

All people depicted are fictional adults. There are no private photographs, real-person
references, nationality labels, scores or facial landmarks. Captions and image
descriptions are localized. The imagery is public UI decoration, never model evidence,
training data or a scored example. The still life contains newly generated architecture
prints, not copies of third-party photographs. No third-party image licence is required.
Generation does not imply exclusive rights to generic visual styles.

Generation direction followed the report's architectural, natural-skin, linen/stone
editorial palette. The still life was generated as 1448×1086; the revised pair as
1122×1402. Sources remain outside the repository. Only metadata-stripped 480/960px
AVIF and WebP variants are shipped. [Asset inventory](assets.json) records source
hashes, output hashes, dimensions, crop coordinates and encoder settings.

Cormorant Garamond is self-hosted under SIL OFL 1.1. The original copyright and full
licence remain in `src/app/fonts/OFL.txt`; an identical copy ships at
`/fonts/cormorant-OFL.txt`. The browser makes no font or image CDN requests. Chinese
uses installed system fonts; rendering varies by operating system. No package was added.

## Performance measurements

Production build, headless Chromium, DPR 1, fresh contexts, 1440px English and 390px
Chinese. Compared imported `8620897` with the reviewed implementation. Homepage
measurement scrolls to load the guide. Counts below are **image and font encoded
response bodies**, not total page transfer, LCP, server memory or live Codespace timing.

| Route / viewport | Imported bytes | Reviewed bytes | Change |
| --- | ---: | ---: | ---: |
| Home, 1440px English | 143,868 | 111,205 | −22.7% |
| Home, 390px Chinese | 97,874 | 69,497 | −29.0% |
| Analysis, 1440px English | 94,490 | 100,196 | +6.0% (+5.6 KiB) |
| Analysis, 390px Chinese | 73,572 | 45,371 | −38.3% |

Desktop hero selects the 35,352-byte 960px image rather than the 63,562-byte 1440px
image. Chinese avoids 23,924 bytes of unused italic font. The new 480px guide is
14,289 bytes in AVIF; the mobile analysis image is 7,731 bytes. Desktop analysis
uses a larger, more deliberate portrait (38,632 bytes versus 32,926).
Higher DPR screens may select larger images; WebP fallback can cost more. These
reductions are measured cases, not a universal promise. Modern `picture` chooses
one format/size per image. Guide art is lazy; intrinsic sizes reserve space. There
is no runtime encoder, third-party image request or new private-response caching.

Homepage CLS was 0 in both captures; Chinese mobile analysis was approximately
0.0106 in both (asynchronous status content). [Raw browser evidence](browser-evidence.json)
includes selected variants, response sizes, route checks and accessibility checks.

## Final screenshots

| Page | English desktop | Chinese mobile |
| --- | --- | --- |
| Homepage | [Full page](final-home-desktop-en.webp) · [Hero](final-hero-desktop-en.webp) · [Tablet](final-home-tablet-en.webp) | [Full page](final-home-mobile-zh.webp) |
| Analysis, disabled model | [View](final-analysis-desktop-en.webp) | [View](final-analysis-mobile-zh.webp) |
| Result, synthetic test checkpoint | [View](final-result-desktop-en.webp) | [View](final-result-mobile-zh.webp) |
| Account | [View](final-account-desktop-en.webp) | Checked at mobile widths |
| Personal research | [View](final-research-desktop-en.webp) | Checked at mobile widths |

Landing/account captures mock public status/empty account responses using fixtures.
Result captures exercise the actual isolated test API and worker with the explicitly
synthetic checkpoint and a generated grayscale fixture. Their numbers do not validate
human aesthetic scoring. Full-page result captures temporarily make the sticky header
static so it appears once; the application retains its sticky header.

## Verification and limitations

- 133 frontend tests pass; ESLint, TypeScript and production build pass.
- Default Chromium suite: 7 passed, 1 synthetic-checkpoint-only case skipped.
- Complementary synthetic checkpoint suite: 1 passed, 1 unavailable-model case skipped.
  Covers localized file selection/focus, persistent filename, upload, worker result,
  distribution, Chinese/English switching and deletion.
- Responsive browser audit: home, analysis, login, account and personal research at
  320, 390, 820, 900, 1024 and 1440px. No page errors, horizontal overflow or controls
  extending past viewport bounds. Images decoded and local source selection was checked.
- Keyboard skip link, mobile menu navigation, visible input focus and reduced-motion
  hover behavior pass. AVIF removal confirms the WebP fallback decodes. Public font
  licence returns HTTP 200. Contrast figures were calculated from the CSS colors.
- This is Chromium coverage, not a manual VoiceOver/NVDA or Safari certification.
  Baseline evidence and final images were visually inspected, including both hero
  candidates and result screens. No automated aesthetic-quality score is claimed.
- Full backend, migration, commercial-browser, deployment and cloud-research regression
  results are recorded in the PR's GitHub Actions checks. No backend source is changed.

## Review and rollout order

This is a **stacked PR targeting `codex/visual-editorial-portraits`**, the still-open
PR #6 branch. That keeps its diff focused on Claude's refinement and this review,
without duplicating PR #6. Do not merge either automatically. Review/merge PR #6
first, then retarget this PR to `codex/phase4b-custom-preferences` and let its checks
run against the resulting base. If PR #6 is squashed, resolve its duplicated ancestry
explicitly before merging this follow-up.

No live Codespace, database, private data, Owner account or backend was modified.
No migration, model enablement, payment enablement or secret change is needed. After
approval, use the established private Codespace update/build/restart procedure with
the verified external encrypted backup preserved and forwarding still private.
