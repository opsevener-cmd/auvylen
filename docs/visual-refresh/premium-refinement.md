# Premium UI refinement — "quiet gallery" (2026-10-27)

Builds on Codex's editorial portraits (PR #6, `8466176`). The change is presentation
only: one stylesheet, a self-hosted display typeface, two small homepage markup
additions and documentation. No API, data, privacy, scoring or i18n behaviour changes.
Real aesthetic scoring stays disabled.

## Critique of the starting point

The new photography is strong. The interface around it still read as a competent
template rather than a premium product:

1. **Typography had no voice.** Arial body text with Georgia headlines, many 10–13px grey
   labels, and negative letter-spacing applied to Chinese. The hierarchy was flat, and the
   bilingual rhythm felt cramped.
2. **The hero was a boxed card.** A rounded rectangle with a white gradient washing over the
   photograph, and a white caption pill sitting on the people. It looked like a banner, not
   a frontispiece.
3. **Every section had the same weight.** A purpose strip, four identical bordered cards,
   a list and a pale green banner, each with the same scale, radius and colour. Nothing
   built to a climax.
4. **The craft details were generic.** Rounded radii of 8/12/16/22px, pill chips, Bootstrap-
   like green status boxes, default form controls, and almost no considered states.
5. **Signed-in pages fell outside the design.** Account, research and analysis pages used
   raw utility boxes, so quality dropped as soon as someone signed in.

## Five improvements implemented (priority order)

1. **Bilingual editorial typography.** Cormorant Garamond for display, self-hosted with
   `next/font/local`: Latin subset only, 62 KB, SIL OFL licence in `src/app/fonts/OFL.txt`.
   Chinese falls back to Songti/Noto Serif CJK, so no CJK font is shipped. A humanist sans
   with PingFang/Noto CJK sets body text at 16–17px. Chinese gets upright accents (never
   faux italic), wider tracking, heavier display weight and 1.85 leading. Small caps-style
   labels use a brass rule. Lining figures prevent "5.1" reading as "5.I" in Cormorant.
2. **Architectural frontispiece.** The hero is now a 11/13 split. A solid ivory text column
   sits beside a photograph that bleeds to the viewport edge, with no overlay on faces.
   Image credits become museum labels under the image. On tablet and mobile the art-directed
   crop goes edge to edge below the headline.
3. **A paced narrative.** Two chapters headed by roman numerals I and II. The four cards
   become hairline-ruled columns with large numerals. The nine-step guide uses an exact grid
   with display numerals. The page ends in one dark, full-bleed ink band with ivory type,
   then a monumental wordmark footer.
4. **One craft system.** Tokens for paper, stone, ink, moss, brass and lines, plus a 2–4%
   paper grain. Square 1px-radius buttons with letter-spaced labels and an arrow that
   moves on hover. A nav underline that draws in brass. Brass-ruled status notices and
   clay-ruled alerts. 48px inputs with moss focus rings. Refined tables, uploads and
   progress bars. Motion is limited to a 12px rise on hero copy and a clip-path reveal on
   the hero image. Neither starts transparent (which protects the largest-contentful-paint
   timing), and both are disabled under `prefers-reduced-motion`.
5. **Consistency on every page and size.** All headings inside the page body use the display
   system, so account, research, analysis and results inherit it without markup changes.
   Breakpoints at 1100, 860 and 600px. Mobile has a ruled full-width menu, buttons that stack
   on phones only, and edge-to-edge photographs. No horizontal scroll at 390, 820 or 1440px.

## Evidence

Production build, Chromium, the same fixture accounts and capture script before and after.
Full-page captures temporarily un-stick the header so it appears once.

| View | Before | After |
| --- | --- | --- |
| Home, English desktop | [before](premium/before-home-desktop-en.webp) | [after](premium/after-home-desktop-en.webp) · [first view](premium/after-hero-desktop-en.webp) |
| Home, Chinese mobile | [before](premium/before-home-mobile-zh.webp) | [after](premium/after-home-mobile-zh.webp) · [first view](premium/after-hero-mobile-zh.webp) |
| Home, Chinese tablet | — | [after](premium/after-hero-tablet-zh.webp) |
| Analysis (disabled model) | [desktop](premium/before-analysis-desktop-en.webp) · [mobile](premium/before-analysis-mobile-zh.webp) | [desktop](premium/after-analysis-desktop-en.webp) · [mobile](premium/after-analysis-mobile-zh.webp) |
| Research workspace | [before](premium/before-research-desktop-en.webp) | [after](premium/after-research-desktop-en.webp) |
| Account | [before](premium/before-account-desktop-en.webp) | [after](premium/after-account-desktop-en.webp) |
| Result typography (synthetic test checkpoint, dev only) | — | [desktop](premium/after-result-desktop-en.webp) · [mobile](premium/after-result-mobile-zh.webp) |

The result screenshots use the generated-data checkpoint from
`scripts/create-test-aesthetic-checkpoint.py`. They are labelled synthetic in the UI and
are not real predictions.

Verification: `npm test` (133 passed), `npm run lint`, `npm run typecheck`, `npm run build`.
Playwright: 7 passed / 1 skipped by default, and the synthetic-checkpoint aesthetic flow
passed. No page errors; scroll width equals viewport width at every captured size.

## Image direction — recommendations for Codex

The current images are warm, diverse and dignified. To move from "lifestyle stock" to
"luxury editorial", prioritise light, architecture and stillness over group smiles:

1. **Hero (replace).** One or two subjects, not four. A grand architectural plane with
   generous negative space on the left third, which the layout now reserves for type.
2. **Analysis (keep, re-light).** The pair works. A cooler, more directional light and a
   plainer wall would make the score page feel calmer and more scientific.
3. **Guide (replace).** Replace the table discussion with a still life of tools of looking:
   prints, a loupe, paper and stone. It explains "study and annotate" without adding more
   faces, and gives the page a quiet beat.
4. **New: ink-band texture (optional).** A near-black stone or linen macro behind the dark
   privacy band, at 8–12% opacity.

All prompts: fictional adults only, no real identities, no text, no logos, no scores, no
face landmarks. Export 2400px wide and keep the existing WebP pipeline.

**Hero, 3:2, plus a 1:1 mobile crop with the subject centred:**
> Editorial fine-art photograph, a single adult woman in her forties standing in a vast
> limestone colonnade, late-afternoon raking sunlight casting long architectural shadows,
> she wears an undyed linen coat, calm three-quarter gaze away from camera, subject placed
> in the right third, left third quiet warm stone with soft light gradient, muted palette of
> ivory, sand, olive and deep moss, medium-format film look, fine grain, shallow depth,
> natural skin texture, no retouching gloss, no text, no logo.

**Analysis, 4:5:**
> Quiet studio portrait of two adults seated on a low plaster bench, north-window light from
> left, plain warm-grey plaster wall, soft shadow edge, relaxed natural expressions, linen
> and wool in oatmeal and olive tones, composed with headroom, editorial magazine style,
> fine grain, no text.

**Guide, 4:3, still life:**
> Overhead still life on travertine: three small black-and-white fine-art prints of
> architecture, a brass loupe, a pencil, a folded linen cloth and a sprig of olive, soft
> diffused daylight, long gentle shadows, ivory, stone, brass and moss palette, minimal and
> precise arrangement, editorial product photography, no people, no text.

**Ink band texture, 3:1, seamless:**
> Macro photograph of dark green-black honed stone with subtle mineral veining, extremely
> soft even light, low contrast, seamless tileable texture, no objects, no text.
