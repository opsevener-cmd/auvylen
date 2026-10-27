# Auvylen editorial imagery — 2026-10-27

Focused visual work from `5df42f1` on `codex/phase4b-custom-preferences`.
The latest base already contains the merged Phase 6 landing page. This PR changes
presentation and public decorative assets only; it adds no scoring functionality,
dependencies, database changes or configuration that enables scoring.

## Original assets and placement

Three original photographs were generated for this task using the image-generation
tool, without reference images, real-person identities or private photographs.
They depict fictional adults with varied appearances in understated everyday
clothes, natural expressions and warm stone/sage editorial settings. No scores,
face landmarks, nationality labels or attractiveness rankings are attached to them.
The public generation captions and image descriptions work in Chinese and English.
These assets are UI decoration and never serve as model results or training data.

| Image | Where it is used | Delivery |
| --- | --- | --- |
| Four adults in a stone gallery | Homepage `/` hero | 960/1440px WebP, plus a dedicated 480/768/1056px mobile crop |
| Three adults around a studio table | Getting-started introduction at `/#guide` | 480/960px WebP, native lazy loading |
| Two adults in a softly lit studio | `/research/aesthetic` landing header | 480/960px WebP |

Only the optimized WebPs are shipped. The original 1536×1024 PNGs remain in the
isolated generation workspace. Each WebP was encoded with Sharp at quality 76,
effort 6, with metadata stripped. Mobile hero cropping preserves all four faces:
source rectangle x=480, y=0, width=1056, height=920. See [asset inventory](assets.json)
for exact dimensions, byte sizes and SHA-256 checksums. Git and Docker ignore rules
allow only these nine specific public asset paths; private-image bans remain.
The older Phase 5 portrait is retained for compatibility but no longer requested
by this home page.

## Integration and extension

`EditorialPortrait` centralizes the three public variants, responsive `srcset`,
`sizes`, localized alt text and disclosure. Native `picture` supplies the mobile
art direction without a client image library or runtime encoder. It accepts a
closed variant name, not an arbitrary URL or a dataset image. Extend that map and
the scoped `.editorial-portrait` styles for future art direction.

The desktop hero has a restrained light overlay behind dark text. At widths up to
1100px, copy and photography stack to avoid obscuring faces. The onboarding image
sits beside the nine-step guide on desktop, above it on mobile. The analysis
header keeps copy on a solid surface, away from photographs. Intrinsic dimensions,
aspect ratios and minimum hero heights reserve layout space. Existing forms,
status/error messages, research limitations and disabled-model states remain.

## Performance

No dependency, external image/font service, tracking request, animation or runtime
image optimization is added. The hero is high priority; the supporting guide
image is lazy. `srcset` downloads one selected variant per image, not every asset.

| Public image at DPR 1 | Bytes | Approximate KiB |
| --- | ---: | ---: |
| Previous homepage hero | 54,550 | 53.3 |
| New desktop hero (1440px) | 63,562 | 62.1 |
| New mobile hero (480px) | 17,568 | 17.2 |
| Guide companion (480px) | 18,742 | 18.3 |
| Analysis desktop (960px) | 32,926 | 32.2 |
| Analysis mobile (480px) | 12,008 | 11.7 |

At 1440px/DPR 1 the home page selects the desktop hero and small guide variant:
82,304 bytes total, roughly 27 KiB more than the former hero alone. At 390px/DPR 1
the home page selects 36,310 bytes total, less than the previous single hero.
High-density screens can select the larger guide and mobile variants. These are
image-body comparisons, not claims about full page weight, LCP or live Codespaces
performance. No private-response cache headers or API behavior were changed.

## Verification and screenshots

Frontend unit tests (133), lint, type checking and production build passed.
Existing Chromium workflows passed: 7 passed / 1 synthetic-checkpoint-only test
skipped in the default configuration. This includes language persistence, mobile
navigation, partial uploads, private datasets, training/prediction, Credits and
synthetic checkout. All five PR CI job results are recorded in the PR description.

Screenshots use the production build at 1440px and 390px. The analysis screenshots
supply a fixture *disabled* model status to show the real landing UI without live
accounts, private images or model outputs. Tablet (820px), mobile and desktop
checks (plus 320/1024px and Chinese desktop boundary checks) inspect image decoding, same-origin asset selection, horizontal overflow
and browser errors. No user credentials or private data appear in evidence.

- [Hero close-up — English desktop](hero-desktop.webp)
- [Homepage — English desktop](home-desktop.webp)
- [Homepage — Chinese mobile](home-mobile.webp)
- [Getting started — English desktop](guide-desktop.webp)
- [Getting started — Chinese mobile](guide-mobile.webp)
- [Analysis landing — English desktop](analysis-desktop.webp)
- [Analysis landing — Chinese mobile](analysis-mobile.webp)

No automatic merge or deployment. After review, this is a normal frontend build
and restart using the established private Codespace procedure. No migration or
account initialization is needed. Preserve the existing backup and private ports.
