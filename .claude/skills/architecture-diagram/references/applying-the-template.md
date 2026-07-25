# Applying the template: what actually bit (local addition)

Notes from filling `assets/template.html` for this repository. The upstream
`SKILL.md` is accurate; these are the things that cost time anyway.

## Patch the template with a script, not by hand

`../scripts/build_interactive.py` copies `assets/template.html`, replaces the
five edit regions by locating their marker lines, and writes
`docs/diagrams/architecture-interactive.html`. Re-running it reproduces the
committed file byte-for-byte, so the content lives in one place and the template
can be re-vendored later without losing the edits.

Anchor on the template's own comment markers (`<!-- User / client / browser -->`,
`TO ADD MORE NODES:`, `const flows = {`) rather than line numbers.

## Renaming the modes

Mode keys are structural: the JS reads `data-tech-<mode>`, `data-port-<mode>`,
`payload<Mode>`, `chips<Mode>`, `data-modes="<mode>"`, and the panel badge prints
the key uppercased. The CSS also selects `[data-mode="offline"]` / `"online"` for
the pill colours.

Do a whole-file token replace (`offline`→`mock`, `online`→`live`, `Offline`→`Mock`,
`Online`→`Live`) **before** inserting your content, so every reference moves
together. Then write your steps in the new vocabulary. Modes are worth using
when the same system runs two ways — here `LLM_MODE=mock` vs live, which swaps
the agent node's tech line and every payload, and makes the provider node exist
at all (`data-modes="live"`).

## Two config lists must follow your flow keys

`CONFIG.fallbackFlow` and `CONFIG.keyboardFlowOrder` near the bottom of the JS
still hold `flow_a` / `flow_b` / `flow_c` after you rewrite the `flows` object.
The diagram looks fine until someone presses `2`. Update both, and
`<kbd id="kbFlowMax">` in the shortcut line.

## Node width limits how many columns you get

`.node` is 150px wide and the side panel eats ~400px, leaving a stage of roughly
990px. That is **four mid-row columns at most**; five overlap. Options, in order
of preference:

1. Move nodes to the top/bottom rows — vertical neighbours can share a column.
2. Narrow `.node` to ~132px (one CSS value) to fit five.
3. Drop a node. Infrastructure that carries no decision (an API router whose
   route already appears in a step's `route:` field) is the first to go.

Rule of thumb: horizontal gap ≥ node width + 2%. Rows at 6% / 40% / 68% give
three clean bands.

## Do not run a wire through a node

Two nodes in the same column with a third between them means the connecting wire
is drawn straight through the middle node. Check every consecutive step pair for
this after placing nodes; it is the one layout error a screenshot makes obvious
and the markup hides.

## Verify the flows headlessly

Screenshotting the page only proves flow 1, step 1 works. Inject a boot script
into a temp copy and screenshot the state you care about:

```python
inject = "<script>window.addEventListener('load',()=>{setTimeout(()=>{%s},250)});</script>"
open('t_spend.html','w').write(html.replace('</body>', inject % "pickFlow('spend');" + '</body>'))
```

`pickFlow(key)`, `pickMode(m)` and `document.getElementById('btnNext').click()`
are the handles. Check at least: one mid-flow step (wires and badges), and an
`onlyMode` flow (mode auto-switch, mode-exclusive node appearing, payload swap).

## Content mapping that worked

Nodes are decision owners, not deployment units. Flows are scenarios, and the
useful set was: the happy path, the human gate, **the failure/abstention path**,
and **the cost/fallback path**. The last two are what make the diagram honest —
they show what happens when the system does not know, and what happens when the
provider fails or the budget runs out. Payloads should be the real shapes copied
from the code (request bodies, table rows), trimmed to the interesting fields.

Worked example in this repo: `docs/diagrams/architecture-interactive.html`,
built from `../scripts/build_interactive.py`, described in `docs/ARCHITECTURE.md`.
