"""Generate the PM Triage hero architecture diagram as a hand-tuned SVG."""
from pathlib import Path

W, H = 1440, 600

INK = "#141821"
MUTED = "#606B7B"
FAINT = "#8B95A5"
LINE = "#E2E7EE"
BG = "#FFFFFF"

BLUE = "#2563EB"
BLUE_BG = "#EEF3FE"
VIOLET = "#7C3AED"
VIOLET_BG = "#F5EFFE"
AMBER = "#C2710A"
AMBER_BG = "#FDF3E3"
GREEN = "#07845C"
GREEN_BG = "#E7F6EF"
GREY = "#64748B"
GREY_BG = "#F1F4F8"

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

out = []


def add(s):
    out.append(s)


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def est(text, size, weight=400, tracking=0.0):
    f = 0.505 if weight < 600 else 0.545
    return len(text) * size * f + len(text) * tracking


def text(x, y, s, size=12, fill=INK, weight=400, anchor="start", tracking=None, opacity=None):
    attrs = [
        f'x="{x:.1f}"', f'y="{y:.1f}"', f'font-size="{size}"',
        f'fill="{fill}"', f'font-weight="{weight}"',
    ]
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if tracking:
        attrs.append(f'letter-spacing="{tracking}"')
    if opacity:
        attrs.append(f'opacity="{opacity}"')
    add(f'<text {" ".join(attrs)}>{esc(s)}</text>')


def rect(x, y, w, h, rx=12, fill="none", stroke="none", sw=1.2, extra=""):
    add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def chip(x, y, label, color, bg, size=9.5, tracking=0.9, pad=9, h=19):
    w = est(label, size, 700, tracking) + pad * 2
    rect(x, y, w, h, rx=h / 2, fill=bg)
    text(x + pad, y + h / 2 + size * 0.36, label, size=size, fill=color, weight=700, tracking=tracking)
    return w


def arrow(x1, y, x2, color="#9BA7B7"):
    add(f'<path d="M {x1:.1f} {y:.1f} L {x2:.1f} {y:.1f}" stroke="{color}" stroke-width="1.7" '
        f'marker-end="url(#ah)" fill="none"/>')


# ---------------------------------------------------------------- geometry
M = 48
CARD_W = 197
GAP = 32
CARD_T = 172
CARD_H = 164
CARD_B = CARD_T + CARD_H
ZONE_T = 128
ZONE_B = 352


def cx(i):
    return M + i * (CARD_W + GAP)


GATE_X = cx(4) - GAP / 2

add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    f'font-family="{FONT}" role="img" aria-label="PM Triage architecture: telemetry is detected by '
    f'deterministic code, classified by physics rules and a narrow trained model, explained by a '
    f'language model, then approved by a human planner before any CMMS work order is created.">')
add('<defs>'
    '<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M 0 1 L 9 5 L 0 9 z" fill="#9BA7B7"/></marker>'
    '<filter id="sh" x="-20%" y="-20%" width="140%" height="140%">'
    '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#1B2434" flood-opacity="0.07"/>'
    '</filter>'
    '</defs>')
rect(0, 0, W, H, rx=0, fill=BG)

# ---------------------------------------------------------------- header
text(M, 56, "PM Triage", size=27, weight=700)
text(M, 84, "How one abnormal sensor reading becomes an approved maintenance work order.",
     size=14.5, fill=MUTED)

# ---------------------------------------------------------------- zones
rect(M - 16, ZONE_T, (GATE_X - 10) - (M - 16), ZONE_B - ZONE_T, rx=18, fill="#F7F9FB")
rect(GATE_X + 10, ZONE_T, (W - M + 16) - (GATE_X + 10), ZONE_B - ZONE_T, rx=18, fill=GREEN_BG)
text(M, ZONE_T + 26, "MACHINE PROPOSES", size=10, fill=FAINT, weight=700, tracking=1.6)
text(W - M, ZONE_T + 26, "HUMAN AUTHORIZES", size=10, fill=GREEN, weight=700, tracking=1.6,
     anchor="end")

# the gate line
add(f'<path d="M {GATE_X} {ZONE_T + 12} L {GATE_X} {ZONE_B - 12}" stroke="{GREEN}" '
    f'stroke-width="1.6" stroke-dasharray="5 5" opacity="0.75"/>')

# ---------------------------------------------------------------- cards
def card(i, kicker, kcolor, kbg, title, lines):
    x = cx(i)
    rect(x, CARD_T, CARD_W, CARD_H, rx=14, fill="#FFFFFF", stroke=LINE, sw=1.1,
         extra='filter="url(#sh)"')
    chip(x + 16, CARD_T + 18, kicker, kcolor, kbg)
    text(x + 16, CARD_T + 74, title, size=17, weight=700)
    ty = CARD_T + 100
    for ln in lines:
        text(x + 16, ty, ln, size=11.5, fill=MUTED)
        ty += 17


card(0, "SOURCE", GREY, GREY_BG, "Telemetry", [
    "Eight simulated assets, plus real",
    "SKAB pump and CWRU bearing",
    "recordings replayed row by row.",
])

card(1, "DETERMINISTIC", BLUE, BLUE_BG, "Detect", [
    "Fixed engineering limits and a",
    "robust median/MAD excursion that",
    "must persist before it raises a case.",
])

# card 2 — the split, drawn as two authority rows
x2 = cx(2)
rect(x2, CARD_T, CARD_W, CARD_H, rx=14, fill="#FFFFFF", stroke=LINE, sw=1.1,
     extra='filter="url(#sh)"')
chip(x2 + 16, CARD_T + 18, "RULES + MODEL", GREY, GREY_BG)
text(x2 + 16, CARD_T + 74, "Classify", size=17, weight=700)
row_y = CARD_T + 88
for color, bg, head, sub in [
    (BLUE, BLUE_BG, "Physics rules", "own every clear fault"),
    (VIOLET, VIOLET_BG, "Trained model", "owns one overlapping pair"),
]:
    rect(x2 + 16, row_y, CARD_W - 32, 31, rx=8, fill=bg)
    rect(x2 + 16, row_y, 3.5, 31, rx=1.75, fill=color)
    text(x2 + 28, row_y + 14, head, size=11.5, fill=color, weight=700)
    text(x2 + 28, row_y + 26, sub, size=10, fill=MUTED)
    row_y += 36

card(3, "LANGUAGE MODEL", AMBER, AMBER_BG, "Explain", [
    "Writes the case: evidence, cited",
    "past work orders, recommended",
    "actions, a drafted work order.",
])

card(4, "HUMAN", GREEN, GREEN_BG, "Decide", [
    "A named planner approves, edits",
    "or rejects. Priority P1–P4 comes",
    "from a formula, not from a model.",
])

card(5, "SYSTEM OF RECORD", GREEN, GREEN_BG, "Act", [
    "An idempotent work order lands",
    "in the CMMS over HTTP, retried",
    "on failure, never duplicated.",
])

# ---------------------------------------------------------------- arrows
mid = CARD_T + CARD_H / 2
for i in range(5):
    a = cx(i) + CARD_W + 7
    b = cx(i + 1) - 7
    if i == 3:
        arrow(a, mid, GATE_X - 16)
        arrow(GATE_X + 16, mid, b)
    else:
        arrow(a, mid, b)

# lock glyph on the gate
add(f'<circle cx="{GATE_X}" cy="{mid}" r="14" fill="#FFFFFF" stroke="{GREEN}" stroke-width="1.6"/>')
add(f'<rect x="{GATE_X - 5}" y="{mid - 1}" width="10" height="8" rx="2" fill="{GREEN}"/>')
add(f'<path d="M {GATE_X - 3} {mid - 1} v -2.5 a 3 3 0 0 1 6 0 v 2.5" stroke="{GREEN}" '
    f'stroke-width="1.5" fill="none"/>')

# ---------------------------------------------------------------- guarantees
PILL_T = 386
PILL_H = 44
total = W - 2 * M
pw = (total - 2 * 24) / 3
guarantees = [
    ("It abstains below 0.45 confidence", "instead of guessing", BLUE),
    ("The model never sets the fault class,", "the priority or the work order", AMBER),
    ("No work order exists without", "a named human approval", GREEN),
]
for i, (l1, l2, color) in enumerate(guarantees):
    x = M + i * (pw + 24)
    rect(x, PILL_T, pw, PILL_H, rx=11, fill="#FFFFFF", stroke=LINE, sw=1.1)
    add(f'<circle cx="{x + 20:.1f}" cy="{PILL_T + PILL_H / 2:.1f}" r="4.5" fill="{color}"/>')
    text(x + 36, PILL_T + 20, l1, size=12.5, fill=INK, weight=600)
    text(x + 36, PILL_T + 35, l2, size=12.5, fill=MUTED)

# ---------------------------------------------------------------- audit rail
AUD_T = 456
rect(M, AUD_T, W - 2 * M, 42, rx=11, fill="#FBFCFD", stroke=LINE, sw=1.1,
     extra='stroke-dasharray="4 4"')
text(W / 2, AUD_T + 26, "Append-only audit  ·  every detection, every model call, every decision, "
     "with its actor and timestamp", size=12.5, fill=MUTED, anchor="middle")

# ---------------------------------------------------------------- runtime strip
RUN_Y = 540
text(M, RUN_Y + 13, "RUNS ON", size=9.5, fill=FAINT, weight=700, tracking=1.5)
x = M + est("RUNS ON", 9.5, 700, 1.5) + 18
for label in ["Next.js · Vercel", "FastAPI · Render", "Supabase Postgres",
              "CMMS as a separate service", "OpenRouter · capped, off by default"]:
    w = chip(x, RUN_Y, label, MUTED, "#F1F4F8", size=11, tracking=0, pad=11, h=25)
    x += w + 10

text(W - M, RUN_Y + 17, "Detail: docs/ARCHITECTURE.md", size=11, fill=FAINT, anchor="end")

add("</svg>")

path = Path(__file__).resolve().parents[4] / "docs" / "diagrams" / "architecture-hero.svg"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("\n".join(out) + "\n")
print("wrote", path)
