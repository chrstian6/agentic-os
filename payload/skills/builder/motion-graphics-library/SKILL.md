---
name: builder/motion-graphics-library
description: Catalog of kinetic typography styles, motion animations and scene transitions with Remotion code, for picking and building each moment of a code-made motion video.
agents: [builder, design-critic]
domains: [video, typography, remotion]
triggers: [kinetic typography, kinetic type, motion graphics, text animation video, video transition, scene transition, remotion animation, animated title, lower third, wordmark reveal]
dependencies: [builder/motion]
conflicts: []
priority: 6
version: 1.0.0
---

# Motion graphics library (Remotion)

Recipes for the moving parts of a code-made video. Each entry gives when to use it, the numbers (at 30 fps) and the code. Pick from it while writing a beat sheet. Consistency beats variety: a film uses 1–2 primary type styles, one default transition and a small set of animations, plus one or two special moments.

## When it applies

- Building scenes for a Remotion (or other frame-based, code-made) video: titles, statements, UI state changes, charts, maps, transitions.
- Choosing type, animation and transitions for a storyboard row.

## When it does not

- Interactive web UI motion that responds to users (`builder/motion`, `builder/interaction-design`).
- Choosing what a scene should say or where the camera goes (`builder/remotion-product-demo` directs; this library executes).

## How to use it

1. For each beat-sheet row, pick one type style, the animations and the transition out from the tables below.
2. Implement them with the shared helpers. Snap entrances, exits and cuts to the music beat; land word events 0–3 frames before the VO word.
3. Review a Full HD preview clip of the scene.

```ts
export const emil   = Easing.bezier(0.23, 1, 0.32, 1);  // entrances
export const emilIn = Easing.bezier(0.5, 0, 0.75, 0);   // exits
export const glide  = Easing.bezier(0.32, 0.72, 0, 1);  // camera, morphs
export const prog = (f, a, b, e = emil) => interpolate(f, [a, b], [0, 1], { ...clamp, easing: e });
// physics when wanted: spring({ frame: f - at, fps, config: { damping: 200 } }) (no bounce)
```
Global numbers:
- Entrances 14–22 frames, exits 8–12, state changes 10–16.
- Stagger 2–3 frames per word, 0.6–1 per letter, 3–4 per row.
- No overshoot unless the brand is playful (cap it at 1.04).
- Settled means `transform`/`filter` set to `undefined`, so text stays crisp.

## Kinetic typography

Choose one **primary** (statements) and one **title** style per film. The rest are utilities or special moments. Animate per word for anything longer than 3 words. Show a line for at least `0.3 s × words + 0.6 s`.

| Style | Use for | Recipe |
|---|---|---|
| Blur rise (default primary) | statements | per word: opacity, `translateY(.35em→0)`, `blur(8→0)`, 16 frames on `emil`, stagger 2.5; exit −.25em, blur 6, 9 frames |
| Mask slide (default title) | titles, wordmark | word clip `overflow:hidden; padding-bottom:.1em`; inner `translateY(108%→0)`, 18 frames, stagger 3 |
| Line wipe | calm full sentence | `clip-path: inset(0 X% 0 0)` 20–26 frames on `glide` plus a 6 px rise |
| Word swap (slot roll) | "Read. Billed. Paid." | fixed slot; old word −100%, new from +100%, 12 frames; slot width morphs |
| Crossfade replace | correcting a word | old word blurs out over 8 frames, new blurs in on the same baseline |
| Strike-through | problem → fix | hand-drawn line draws across the word over 10 frames; word dims to .45; the fix rises after |
| Highlight sweep | the one key phrase | marker band `scaleX(0→1)` from the left, 14 frames, accent at 18% |
| Underline draw | gentle emphasis | SVG hand-drawn underline, dash offset over 12 frames |
| Tracking collapse | taglines | letter-spacing `.4em → -.02em` plus opacity, 24 frames on `glide` |
| Counter / odometer | numbers | count up with tabular-nums; odometer digits roll right-to-left, 1 frame apart |
| Typewriter + caret | inputs, chat (inside UI) | 2–3 frames per character, caret blinks every 8 frames, hidden 12 frames after the end |
| Stream | AI answers | per word opacity (+blur 3), 0.9 frames apart |
| Stack push | short lists | new line rises in; earlier lines shift up and dim to .5 |
| Split reveal | chapter title | top and bottom halves clip apart ±12 px, then settle |
| Scale settle | brand word on an accent | 0.92→1, blur 6→0, 14 frames |
| Text on path | labels on a route | `<textPath startOffset>` plus `evolvePath` |
| Letter wave | playful brands only | per letter .55em rise with sine offset, rotate −7°→0 |

Rules:
- Centre statements; left-align text beside a mark.
- Balance two-line statements by hand and delay the second line to its VO word.
- No all-caps labels, no one-word colour accent in every line, no letter animation on sentences.

## Motion animations

- **Entrances:**
  - **Float:** cards, opacity, rise ≤28 px, rotateX ≤6°, scale .965→1, blur 8→0, 22 frames; exit 10 frames, −14 px.
  - **Scale-in:** chips and pins, .8–.96→1, plus a pulse ring.
  - **Clip reveal:** `inset()` from one edge.
  - **Draw-on:** `pathLength=1`, dash offset, or `@remotion/paths` `evolvePath`.
  - **Staggered list:** 3–4 frames apart, capped at about 0.8 s in total.
  - **Drop-in stack:** new card from −18 px; older cards shift down.
- **State changes, in place:**
  - **Button press:** 1→.96→1 with a colour swap at the press frame.
  - **Content swap:** blur crossfade, the container size moving on `glide`.
  - **Toggle:** the knob slides and the outcomes follow 6–10 frames later.
  - **Spinner → check.**
  - **Progress fill:** rows tint in order.
  - **Badge flip:** crossfade with a 1.06 nudge.
  - **Count-up**, and **highlight band** (`rgba(accent,.12)`).
- **Emphasis, sparingly:**
  - **Pulse ring.**
  - **Spotlight:** a mask dims the rest to 62% white.
  - **Glow outline.**
  - **Hand-drawn circle or arrow:** see `builder/product-svg-artist`.
  - **Snap punch:** 1→1.03→1.
- **Data:**
  - **Bars** grow from the baseline, stagger 3.
  - **Line** draws on with a dot riding the tip (`getPointAtLength`).
  - **Donut** sweeps.
  - **KPI tiles** stagger, then count.
  - **Map accumulation:** pops at `t ∝ (i/N)^0.5`, stopping before saturation.
  - **Map propagation:** reveal at `R(t) > d` over a Dijkstra distance field, with the radius tied to view width.
- **Paths:** follow a path rotated by its tangent. Cursor travel on `glide`, arriving 2 frames before the press.
- **Ambient:**
  - Backdrop gradients drift on `sin(f/90)`.
  - Slow creep 1→1.04.
  - Micro float ±2 px, never on text-heavy UI.

## Transitions

One default carries most cuts; special ones mark the 1–2 biggest moments. Land them on a beat, overlapping 8–12 frames.

| Transition | Use for | Recipe |
|---|---|---|
| Whip (default) | calm product film | outgoing opacity→0, −20 px, scale .98, blur 8, 10 frames on `emilIn` |
| Crossfade | same space, new state | 8-frame opacity overlap of scene windows |
| Push / slide | sequential steps | out to −120 px, in from +120 px, 14 frames on `glide`; keep one direction |
| Zoom-through | entering a detail | push to about 3× over 18 frames; the next scene fades in during the last 8 |
| Shared-element morph | card → screen, chip → header | interpolate rect (l, t, w, h, radius) on `glide` |
| Iris | a button or pin opens a view | `clip-path: circle(r at x y)` from the press point, 16–20 frames |
| Wipe | chapter or before/after | `inset()` sweep plus a 2 px accent edge, 18 frames |
| Type bridge | a line links two scenes | the text stays while the scene behind it changes |
| Dip to backdrop | problem → product reveal | fade to the clean backdrop for 4–6 frames, then the mark pops |
| Directional carry | quick sequences | exit direction = next entry direction, same speed |
| Blur pass | time skip | whole frame blur 0→12→0 with the swap at the peak |

Implementation:
- **Hand-rolled:** scene windows with an 8-frame overlap plus a per-scene `whip(f, out)`.
- **`@remotion/transitions`:** `TransitionSeries` with `fade`, `slide`, `wipe`, `flip`, `clockWipe` and `springTiming({config:{damping:200}})`. The version must match `remotion` exactly.
- **Motion blur** only on fast moves: `@remotion/motion-blur` `CameraMotionBlur`.

## Common mistakes

- Mixing four type styles in one film; animating letters of a full sentence.
- Bounce or elastic easing on product UI; exits slower than entrances.
- Two special transitions back to back; directions that flip at random.
- Captions inside a transitioning layer (they must stay put).
- Leaving a settled element with `blur(0px)` or `scale(1)` applied, which softens text.
- `@remotion/*` packages at a version different from `remotion`.

## Verification

- Render a Full HD preview clip of every scene that uses a transition or more than one animation, and step through it frame by frame around the transition.
- Count the styles used across the film: primary type 1, title 1, default transition 1, specials ≤2.
- Check reading time per line and that word events land at or just before the VO word.

## Example

Close of a product film:
1. "Smarter routes." and "Faster billing." in blur rise, each exiting with blur-up.
2. "Better service for every / household you serve." as two hand-balanced lines, the second in the accent colour.
3. A dip to the backdrop.
4. The mark scale-settles on the music accent while the wordmark mask-slides in beside it.
5. The tagline in blur rise holds to the end.
