---
name: builder/hig-taste
description: The owner's design standard - Apple HIG applied to the web, less is more, modern and readable, one clean sans typeface. The default for every UI task; a project's own design authority overrides it where they differ.
agents: [builder, design-critic, reviewer]
domains: [frontend, visual, design]
triggers: [design, ui, ux, redesign, look, visual, styling, beautiful, taste, layout, typography, typeface, hig, minimal, visual polish, clean ui, landing page, hero, brand, looks generic]
dependencies: [builder/anti-ai-slop, builder/accessibility, builder/responsive-design]
conflicts: [builder/design-taste, builder/hallmark]
priority: 10
version: 1.0.0
---

# HIG taste

## Order of authority

1. WCAG AA. Always.
2. The project's own design rules (for example `.claude/rules/design.md`, a design system, tokens). Where they set a value, use it.
3. This skill, for everything the project leaves open.

Facts and sources: the vault note `Design Mastery — Apple HIG`. Owner taste and the decisions log: `Design Preferences`. Read both before a design task when the vault is linked.

## The standard

**Less is more.** Every element earns its place. Remove before you add.

- **One primary action per view.** It is the only accent-filled control. Everything else is quiet: outline, plain or text.
- **Preference by style, not size.** Never make a button bigger to make it win.
- **Never a destructive primary.** Destructive actions use the danger colour and a confirm.

## Type

- One sans family. System stack by default: `-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, "Helvetica Neue", Arial, sans-serif`. If the project names a font, use it.
- A fixed ramp, nothing in between: 34/41, 28/34, 22/28, 20/25, 17/22 (body), 16/21, 15/20, 13/18, 12/16, 11/13.
- Weights 400, 500, 600. Nothing under 400. Bold only for real emphasis.
- Tighten tracking only at 28px and up (-0.01 to -0.02em). Measure 45–75 characters.

## Layout and space

- Spacing scale 4, 8, 12, 16, 24, 32, 48, 64 (a convention, not a HIG number). Pick one scale and stay on it.
- Separate by space first, then a 1px hairline. No shadow on cards. Shadow only on floating layers (menus, dialogs, popovers).
- Symmetric, aligned layouts with clear edges. Do not break the grid for effect.
- Group by proximity: small gaps inside a group, large gaps between groups.
- Hit targets 44×44px on touch, 28px minimum on dense desktop UI.

## Colour

- Neutral surfaces, one accent. The accent marks interactive elements only, never plain text.
- Semantic tokens (`--label`, `--label-secondary`, `--bg`, `--separator`, `--accent`, `--danger`) with light, dark and `prefers-contrast` variants. No hex in components.
- Status is a word, with a dot if needed. Never colour alone.
- Contrast: 4.5:1 body text, 3:1 large text and UI parts.

## Depth and motion

- Blur or glass only on floating chrome (sticky header, tab bar), with an opaque fallback under `prefers-reduced-transparency`. Never on content.
- Motion explains a change of state. 150–250ms, interruptible. Under `prefers-reduced-motion`, replace movement with a fade.

## Reject on sight

Gradients as decoration · a card inside a card · heavy or stacked shadows · glass on content · two accent colours · more than one filled button per view · thin weights · mixed icon sets · centred body paragraphs · grey text under 4.5:1 · decorative motion · placeholder copy.

## Check before you hand back

1. Squint: one thing dominates, and the groups read as shapes.
2. Count: font families (1), weights (≤3), accent hues (1), filled buttons per view (1), shadow depths (≤1 on content: 0).
3. Every value comes from the ramp, the spacing scale or a token.
4. Keyboard focus is visible; targets meet 44px on touch; contrast passes.
5. When the owner approves or rejects a design, add one line to the `Design Preferences` decisions log: date, surface, decision, reason.
