---
name: builder/product-svg-artist
description: Draw a product's own icons, handwritten-style annotations, spot illustrations and logo marks as code-made SVG React components with draw-on animation, for videos and UIs.
agents: [builder, design-critic]
domains: [icons, illustration, video]
triggers: [icon set, custom icons, svg icon, svg icons, hand-drawn, handwritten, illustration, spot illustration, logo mark, product mark, annotation, doodle]
dependencies: [builder/design-taste]
conflicts: []
priority: 6
version: 1.0.0
---

# Product SVG artist

How to draw a product's own visual vocabulary in code. That covers clean icons, hand-drawn annotations (circles, arrows, underlines, strike-throughs), small spot illustrations and a simple product mark. Each is an SVG React component, consistent with the product's design system and ready to animate (draw-on, pop, morph) in a UI or a Remotion video.

## When it applies

- The product or video needs icons the app does not have (new features, VO nouns).
- A video or page wants warmth: hand-drawn emphasis, handwritten notes, small illustrations.
- A generic or new product needs a mark and wordmark.

## When it does not

- The app already has an icon for the concept: reuse it.
- Photography, 3D renders or raster art.
- Copying or imitating another brand's logo, icon set, mascot or a known character. This is never done; draw an original take on the generic subject instead.

## How to use it

1. **List what's needed** from the script or UI: nouns become icons, claims become a spot illustration or an annotation.
2. **Fix a style sheet before the second piece:**
   | Property | Product icons | Hand-drawn |
   |---|---|---|
   | Grid | 16 or 24 units, 1.5–2 padding | 64–120 units, loose |
   | Stroke | 1.5 (16) or 2 (24), round caps/joins | 2.5–4 px, variable width |
   | Fill | none, or one accent at 12–18% | offset accent blob behind the line |
   | Colour | `currentColor` | ink plus one accent |
   | Detail | 1–3 inner strokes | 2–5 gestural marks |
   Match the app's existing grid and stroke when it has an icon set.
3. **Draw product icons:** one silhouette plus at most two details. A meter is a circle with a needle and two ticks; a route is two dots and an S-curve; a receipt is a rectangle with a zigzag bottom and two lines. Start from primitives, convert to paths for draw-on, put stroke ends on half-units, and make circles about 10% larger than squares for optical balance. Export into one map:
   ```tsx
   const PATHS = { route: <><circle cx="4" cy="12" r="1.75"/><circle cx="12" cy="4" r="1.75"/>
     <path d="M5.75 12H10a2 2 0 0 0 0-4H6a2 2 0 0 1 0-4h4.25"/></> };
   export const Icon = ({ name, size = 16 }) => <svg viewBox="0 0 16 16" width={size} height={size}
     fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">{PATHS[name]}</svg>;
   ```
4. **Draw the hand-drawn style.** Pick one technique per product:
   - **Wobble:** sample the clean shape, offset points with *seeded* noise (`random(seed+i)` in Remotion), and rebuild with a Catmull-Rom → cubic Bézier conversion.
   - **Pressure strokes:** `perfect-freehand` (size 6–10, thinning .5–.7) gives a marker feel. Reveal it by slicing the point list.
   - **Sketchy shapes:** `roughjs` generator with roughness .8–1.5 and a fixed seed.
   - **Pencil:** a double stroke at 70% with two seeds.
   - **Print feel:** an offset fill blob 3–6 px down-right.
5. **Annotation set:**
   - **Circle:** an ellipse whose loop overshoots its start by 15–25°.
   - **Arrow:** a curved shaft, then a two-stroke head.
   - **Underline:** rising, thick start, tapered end.
   - **Strike-through:** one or two quick strokes.
   - **Bracket plus label.**
   - **Handwriting:** only 1–4 words. Use an open-licence handwriting font revealed by a clip wipe that follows a pen dot.
6. **Spot illustrations:** 3–7 simple shapes in the style sheet, one accent fill, a soft ground shadow. Animate them as parts: base draws on, details pop in 3–4 frames apart, fill fades in last, with optional micro-motion (a needle wiggle of ±4°).
7. **Product mark:**
   - A rounded tile (radius 28%) with a 160° gradient of the brand blues, an inset top highlight and a soft shadow.
   - A white glyph from 1–2 paths at 60% of the tile, readable at 24 px.
   - Wordmark in the product font, weight 700, −0.03em tracking. A long name goes on two lines (ink, then accent at about 55% size).
8. **Animate:**
   - `pathLength={1} strokeDasharray="1 1" strokeDashoffset={1-p}`, or `evolvePath` from `@remotion/paths`, with an optional pen dot riding the tip via `getPointAtLength`.
   - Order: outline, then details, then fill. For arrows, the shaft draws before the head.
   - Durations: icons 10–16 frames, annotations 8–16, illustrations 24–45 in total.
   - In zoomed scenes use `vectorEffect="non-scaling-stroke"`.

Files: `src/icons.tsx`, `src/art/annotate.tsx`, `src/art/spots.tsx`, `src/art/mark.tsx`, `src/art/hand.ts`.

## Common mistakes

- Re-randomising the wobble every frame, which makes jitter (keep seeds fixed; a deliberate "boil" swaps 2–3 seeds every 6–8 frames, playful films only).
- Mixed stroke widths or corner styles across one set; icons that turn to mush at 16 px.
- Too much detail; more than one accent per piece.
- A mark that resembles an existing organisation's seal or logo.
- Drawing an icon the app already ships.

## Verification

- Render a contact sheet of the whole set at 16, 24, 48 and 96 px on the real backdrop (Remotion still, or `cairosvg`/`resvg`). Check equal visual weight, stroke consistency and legibility at the smallest size.
- Watch a Full HD clip of each draw-on: order, timing and no jitter.
- Confirm originality: nothing traces or resembles a known brand or character.

## Example

The Water Billing & Monitoring System mark: a deep-blue rounded tile, glyph-size 60%, holding a white water drop with a small blue meter-tick arc inside, plus a two-line wordmark ("Water Billing" in ink, "& Monitoring System" in accent). New feature icons on the app's 16-unit, 1.5-stroke grid: sparkle (assistant), send, mail, message, route, flag, file, peso. For a problem scene, a wobble-style strike-through draws across "paperwork" in 10 frames before the fix line rises.
