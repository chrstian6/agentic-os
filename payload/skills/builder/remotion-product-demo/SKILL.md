---
name: builder/remotion-product-demo
description: Direct and build a code-only motion-graphics product demo video, scene by scene as React code rendered in Remotion at Full HD, from a real app's code, data and an ElevenLabs voice-over.
agents: [builder, design-critic]
domains: [video, remotion, explainer]
triggers: [remotion, demo video, product video, explainer video, promo video, motion graphics video, voice-over, voiceover, elevenlabs, storyboard, render the video, video for the app]
dependencies: [builder/motion-graphics-library, builder/product-svg-artist, builder/design-taste]
conflicts: []
priority: 7
version: 1.0.0
---

# Remotion product demo video

A playbook for a minimal, modern product explainer (about 1.5 to 2 minutes). It is built entirely in code from the real app's source and seed data, timed to the user's own voice-over (VO) and a music track, and rendered with Remotion at 1920×1080. It came from the BWD Billing and Water Billing & Monitoring System demos.

Work in two roles: **director first** (what each moment must make the viewer believe, how it moves, where the camera goes), then **builder** (each scene written as code and rendered with Remotion).

## When it applies

- A promo, explainer or demo video for a software product, where the UI, numbers and maps must be the product's own.
- A voice-over exists or will be recorded (ElevenLabs), and the video must follow it.
- The output is an MP4 video made with code, not with a video editor.

## When it does not

- In-app UI animation for the web (use `builder/motion` and `builder/interaction-design`).
- Live-action editing, screen recordings, or stock-footage montages.
- A single animated graphic or GIF with no VO; use `builder/motion-graphics-library` alone.

## Non-negotiables

- **Everything is code.** Each scene is its own React component (`src/scenes/S1Problem.tsx` …). It is built from code-rebuilt app UI, SVG, CSS and data JSON. There are no screenshots or browser captures of the app, no stock footage and no video editors. Sound effects are synthesized in Python; music and VO are the user's files.
- **Remotion renders the film.** `Main.tsx` composes the scenes (scene windows with crossfades), the VO, music and captions. ffmpeg is used only for loudness, splicing a re-rendered range, and the compressed sending copy.
- **Full HD always.**
  - Composition is 1920×1080 at 30 fps; design on a 1280×720 logical canvas scaled 1.5×.
  - Master settings: H.264, CRF ≤14 (12 when time allows), `yuv420p`, `--jpeg-quality` ≥95, AAC 256k.
  - Never scale down. The copy that must fit under 30 MB for chat stays 1920×1080; only its bitrate drops (two-pass).
- **Crisp text.** Settled elements carry no `transform` or `filter`. Raster layers (basemap JPEGs) soften when zoomed past about 1.3×; swap to SVG detail tiles for close shots.
- **Real data, generic names.** Run the app's own engine over its seed data. Never show test-data names; for an anonymous version, map place names to neutral ones (for example "Zone 1…16"). Coordinates must be plausible.
- **Style.** Minimal: kinetic type, floating cards with light blur and tilt, a pale gradient backdrop. Use 1–2 primary type styles per film. Taps are crisp clicks, only on cursor presses or sends. Captions are on.

## How to use it

1. **Script the VO first.** Short sentences with a blank line between paragraphs: those pauses become scene cuts. Write acronyms as "B-W-D" so TTS reads them letter by letter. Ask the user: product name, anonymous or proof-case, contact card, features to highlight. The user records it in ElevenLabs. Deliver the script and storyboard in one message when both are asked for.
2. **Direct.** Write a beat sheet per scene: `VO phrase | time | claim | on-screen event | type style | camera | transition out | SFX`.
3. **Set up once:**
   - **Stack:** Remotion 4 with React 19 (18 breaks). Point `remotion.config.ts` at the Playwright headless shell if Chrome downloads are blocked.
   - **Brand:** fonts loaded via `FontFace` inside `delayRender`, and the app's CSS tokens copied into `tokens.ts`.
   - **Data:** the app's pure TS modules copied verbatim into `scripts/app/`. `scripts/compute.ts` (run with `node --experimental-strip-types`) writes `src/data/computed.json`; every figure on screen comes from it.
   - **Kits:** a motion kit (`motion.tsx`), a UI kit rebuilt from the app (`kit.tsx`), and `icons.tsx`.
4. **Build scene by scene.** For each scene:
   1. Write the component from its beat sheet, using `vn(sec) = round((sec + 0.5) * 30)`, with the VO placed 15 frames in.
   2. Add it to `SCENES`, then run `npx tsc --noEmit`.
   3. Bundle and render 3–6 stills across it, read as a contact sheet.
   4. For camera moves or transitions, render a short Full HD clip with `--frames=A-B`.
   5. Fix, then move on.
5. **Whole-film pass:** director's checklist and captions, then the full render in the background.
6. **Finish:** loudnorm to −14 LUFS, a two-pass 1080p copy under 30 MB, verify, then send it with a project zip (no node_modules, out or huge maps).

## Directing

**One claim, one hero action per scene.** Write the claim (what the viewer must believe), then one action that *performs* it on screen, rather than labelling it.
- **Smart route (model scene).** It opens at street level on one reader pin. Red lines grow out of it along the real streets: a shortest-path tree over the road graph, branching like a tree. The camera pulls back exponentially from one street to the whole town, with the growth front kept just ahead of the frame edge. Then a route chip proves it. Growth *is* the planning, and the move from one person to the whole town mirrors "every stop".
- **Meter mapping (model scene).** Red dots pop sparse, then faster and faster (`t ∝ (i/N)^0.5`), each with a fading ring. A counter chip ticks up and the camera eases toward the clusters. It stops well short of filling the map; saturation looks fake.
- **Pattern:** origin → spread or accumulate → camera reveals scale → proof chip or number → release on a beat.

**Metaphor from the VO's verb:**
| VO says | Visual |
|---|---|
| spread, route, assign | propagation from an origin |
| every, all, thousands | accumulation |
| tap, open | selection plus push-in |
| in seconds | compressed time |
| automatically | a toggle flips, then outcomes land |
| compute | itemised build-up, total counts up |
| oldest first | sequential fill |
| balanced | before and after |
| offline | state flip |
| ask | dialogue (type, steps, streamed answer, actions) |
| notify | arrivals stacking |
| problem lines | plain type on empty space |

**Words to events.**
- Nouns make things appear, verbs make things happen, numbers count.
- Land each event 0–3 frames before its word.
- No dead air longer than about 2 s.

**Choreography.**
- One lead mover at a time; stagger a camera move and a card entrance by 6–12 frames.
- Every scene runs establish → act → prove → release.
- Transform in place instead of cutting. The result appears where the action happened.
- Exits (10 frames) are faster than entrances (22).

**Composition.**
- One hero at about 60–70% of the frame. Keep the bottom 150 px clear for captions.
- Never leave half the frame empty: a lone element starts centred, then glides aside when its partner arrives.
- Never leave orphan words. Reuse the same accounts and amounts across scenes so the story connects.

**Rhythm.**
- Cuts sit in VO pauses, snapped to music beats. Alternate busy and calm scenes.
- Arc: problem → brand reveal on the music's phrase accent → one hero action per feature → close.

## Camera

A camera move needs a reason: a VO word, an action, or a reveal of scale. Otherwise lock the frame.
- **Rig:** `translate(640 - cx*s, 360 - cy*s) scale(s)`, optionally with `rotateX`/`rotateY` and perspective 1600, keyframed on the `glide` curve (0.32, 0.72, 0, 1). For maps, move the SVG viewBox and keep strokes constant with `inv = vb.w / W`.
- **Shots:**
  - **Establishing wide:** 1–1.5 s.
  - **Push-in:** on a named thing, 1→1.6–2.5×, 24–30 frames.
  - **Pull-back reveal:** exponential zoom `w = w0*(w1/w0)^z`, drifting toward the destination by `k = (w-w0)/(w1-w0)`.
  - **Slow creep:** 1.00→1.04 across a hold.
  - **Pan/track:** follow a reading order.
  - **Follow with lag:** read the subject about 6 frames late.
  - **Reframe for a partner.**
  - **Rack focus:** blur and dim the background.
  - **2.5D tilt:** 8–14° on entrance only.
  - **Parallax:** depth 0.2 / 0.6 / 1.0 / 1.15.
  - **Snap-zoom punch:** 1→1.03→1 at most twice per film.
- **Rules:**
  - Hold 0.5–1 s after every move.
  - Exaggerate scale changes.
  - Zoom DOM or SVG up to about 2.5×, rasters about 1.3×. No roll.
  - End scenes still, unless the transition is a zoom-through.

## Timing, music, captions

- **VO segments:** `ffmpeg silencedetect=noise=-38dB:d=0.28`.
- **Word times:** PocketSphinx (`pip install pocketsphinx`; recognition with `start_frame/100`). If forced alignment fails, the recording differs from the script: re-transcribe that part.
- **Reusing scenes on a new read:** a piecewise-linear `REMAP` from old phrase times to new ones.
- **Music:**
  - Measure the beat grid with librosa. `snap(frame)` moves cuts and entrances to the nearest beat.
  - Set `MUSIC_OFFSET` so a phrase-accent downbeat lands on the logo pop.
  - Extend the track seamlessly by looping at phrase boundaries with a 30 ms crossfade, always extending the already-verified file.
- **SFX tap:** 35 ms of band-passed noise (3–9 kHz) plus a 2350 Hz ping and a light 620 Hz body; energy below 300 Hz about 1%.
- **Captions:**
  - `CUES` in VO seconds. Skip lines already shown as kinetic type.
  - Up to 46 characters per line, then two balanced lines, in a dark pill 48 px from the bottom, outside the camera.

## Fast iteration

- **Audio-only:** an `AUDIO_ONLY` input prop makes `Canvas`/`Backdrop` return null; render `--codec=wav` in seconds and remux.
- **Captions-only:** render a transparent ProRes 4444 overlay.
- **One scene changed:**
  - Re-render only `--frames=A-B --muted` at Full HD.
  - Splice with `[1:v]setpts=PTS-STARTPTS+A/30/TB[s];[0:v][s]overlay=eof_action=pass`. Using `-itsoffset` with `enable=between(n,…)` silently did nothing.
- **Never rebuild a bundle folder a render is reading;** bundle to `out/bundle2`.

## Common mistakes

- Screenshots or browser captures instead of code-rebuilt UI.
- Test-data names on screen, or numbers typed in by hand instead of computed by the app's own engine.
- Many type styles in one film, letter animation on long sentences, or bounce easing.
- Camera moving while a card enters, or a move with no reason and no hold after it.
- A lone element leaving half the frame empty.
- Taps on every event instead of on clicks only, or a thumpy click.
- Rendering below 1080p to save size instead of lowering the bitrate.
- A still named `.png` while using `--image-format=jpeg`: it fails silently.

## Verification

- **Contact sheets** per scene (stills at `--scale=0.5`, internal only). Check:
  - cursor targets (often 20–50 px off at first)
  - framing, empty halves, orphan words
  - captions covering key UI
  - leftover client names (grep the source)
- **Preview clips** for every camera move and transition: no jitter, no overlapping moves, no soft rasters.
- **Splices:** check frames on both sides of each seam.
- **Final:** `ffprobe` shows 1920×1080, 30 fps, the expected duration, −14 LUFS, and under 30 MB for the sending copy.

## Example

The "Water Billing & Monitoring System" demo (1:56) runs:
1. Three problem lines in blur-rise.
2. The mark settles on the music accent and the wordmark unmasks.
3. Zone map: push-in on the tapped zone.
4. Auto-assign table: highlight bands.
5. Smart route: a propagation tree from street level out to the whole town.
6. Cashier: oldest-first fill.
7. SMS/email: phone centred, then gliding aside for the email.
8. Assistant: a portal page answering "Who's overdue in Zone 3?" with the balance left after the cashier's OR-0012.
9. Meter mapping: accumulation.
10. Close: three lines, brand, tagline.

Rendered with Remotion at 1920×1080, CRF 14, then loudnorm, and a 29 MB two-pass copy.
