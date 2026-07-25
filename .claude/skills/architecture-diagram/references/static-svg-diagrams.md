# Static SVG diagrams (local addition)

The upstream skill covers interactive HTML and says to use Mermaid for anything
static. That gap is real: a README hero diagram must render inline on GitHub,
and Mermaid's auto-layout cannot produce a diagram whose *layout itself* carries
the argument. This file covers the third option — a hand-tuned SVG committed to
the repo — and the method that produced `docs/diagrams/architecture-hero.svg`
and `architecture-detail.svg`.

## Which of the three to build

| Need | Build |
|---|---|
| Renders inline in the README, layout carries meaning, worth an hour | Static SVG (this file) |
| Click through it, step by step, payload per step, workshop or demo | The interactive template (upstream `SKILL.md`) |
| A quick boxes-and-arrows sketch nobody will look at twice | Mermaid inline, and move on |

A repo usually wants the first two: the hero SVG in the README, the interactive
page linked from it.

## Method: generate, don't hand-write

Write a Python layout script with helpers (`text`, `rect`, `chip`, `arrow`) and
named geometry constants, then commit the *output* SVG. Hand-editing raw SVG
coordinates does not survive a second revision — every spacing change becomes
dozens of manual offsets.

Working generators: `../scripts/gen_hero.py`, `../scripts/gen_detail.py`. Both
write into `docs/diagrams/` relative to the repo root and are idempotent — re-run
them and `git status` stays clean. Keep that property; it is how you know the
committed SVG and the script have not drifted.

Text width has no measuring API in this setup. Estimate:

```python
def est(text, size, weight=400, tracking=0.0):
    f = 0.505 if weight < 600 else 0.545      # avg glyph width / font-size
    return len(text) * size * f + len(text) * tracking
```

It is close enough for chip widths and right-edge placement, but it
**underestimates all-caps strings by ~25%** — multiply by 1.28 when positioning
something after a caps label, or the next element will collide with it. That was
a real bug in the first pass (band titles overlapping their subtitles).

## Verify by looking, not by reading the markup

Chromium is pre-installed. Screenshot the SVG directly and read the PNG back:

```sh
/opt/pw-browsers/chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=1 --window-size=1480,700 \
  --screenshot=/abs/path/out.png "file:///abs/path/diagram.svg"
```

Use absolute paths — the shell's working directory resets between calls. Give
the window ~60px more height than the canvas: content near the bottom edge gets
clipped and looks like a missing element, which will send you debugging markup
that is perfectly fine.

Iterate on the picture: baseline rhythm, collisions, and cramped rows are
obvious in a screenshot and invisible in the XML.

## Design rules that made the hero work

- **One organizing idea, expressed geometrically.** The hero's whole argument is
  a dashed vertical gate with a lock: left of it the machine proposes, right of
  it a human authorizes. Tint the two zones and label them. A viewer gets the
  safety story before reading a single box.
- **Colour means authority, not category.** One colour per decision owner
  (deterministic code / trained model / language model / human / source /
  system of record). Then the diagram answers "who decides this?" at a glance.
- **Put the legend inside the cards.** A small colored tag chip on each card
  ("DETERMINISTIC", "LANGUAGE MODEL", "HUMAN") removes the separate legend and
  the eye-travel it costs.
- **Keep the baseline rhythm.** Every card's chip, title, and body text start at
  the same offsets. The one card that broke this (a split card with two colored
  rows) looked wrong immediately in the screenshot; giving it a chip and the same
  title baseline fixed it.
- **A band of guarantees under the pipeline.** Short claims the diagram must
  make — abstention, what the model never decides, no action without approval —
  as equal-width pills, so they read as a set.
- **Detail belongs in a second diagram.** Deployment topology, module names and
  table names go in a drill-down. Anything that would push the hero past ~6
  boxes should move down a level.

## GitHub rendering constraints

- Markdown embeds SVG through `<img>`. Scripts do not run; CSS filters
  (`feDropShadow`), `letter-spacing` and web-safe font stacks all work.
- **Do not theme-switch.** `prefers-color-scheme` inside the SVG follows the OS,
  not GitHub's theme, so a light page can get a dark diagram. Commit one light
  design with an explicit background — it reads fine on GitHub's dark theme.
- Write a real `aria-label` on the root `<svg>` and a full sentence as the
  markdown alt text. Both get read; neither is decoration.
- No external assets. Inline everything.

## Honesty rule

A diagram is a claim surface. Do not put a number in it you cannot verify right
now (test counts, accuracy, cost) — it will drift silently and it will be the
number someone quotes back at you. Keep measured figures in the doc that owns
them, and let the diagram carry structure.
