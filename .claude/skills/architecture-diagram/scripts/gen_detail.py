"""Generate the PM Triage drill-down architecture diagram (runtime + modules)."""
from pathlib import Path

W, H = 1440, 1064

INK = "#141821"
MUTED = "#606B7B"
FAINT = "#8B95A5"
LINE = "#E2E7EE"

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
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"

out = []


def add(s):
    out.append(s)


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def est(text, size, weight=400, tracking=0.0):
    f = 0.505 if weight < 600 else 0.545
    return len(text) * size * f + len(text) * tracking


def text(x, y, s, size=12, fill=INK, weight=400, anchor="start", tracking=None, mono=False):
    attrs = [f'x="{x:.1f}"', f'y="{y:.1f}"', f'font-size="{size}"', f'fill="{fill}"',
             f'font-weight="{weight}"']
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if tracking:
        attrs.append(f'letter-spacing="{tracking}"')
    if mono:
        attrs.append(f'font-family="{MONO}"')
    add(f'<text {" ".join(attrs)}>{esc(s)}</text>')


def rect(x, y, w, h, rx=12, fill="none", stroke="none", sw=1.1, extra=""):
    add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def chip(x, y, label, color, bg, size=10, tracking=0.0, pad=10, h=22, mono=False):
    w = est(label, size, 600, tracking) + pad * 2
    rect(x, y, w, h, rx=h / 2, fill=bg)
    text(x + pad, y + h / 2 + size * 0.36, label, size=size, fill=color, weight=600,
         tracking=tracking, mono=mono)
    return w


def vaarrow(x, y1, y2, label=None, dashed=False, color="#9BA7B7"):
    d = ' stroke-dasharray="5 4"' if dashed else ""
    add(f'<path d="M {x:.1f} {y1:.1f} L {x:.1f} {y2:.1f}" stroke="{color}" stroke-width="1.7" '
        f'marker-end="url(#ah)" fill="none"{d}/>')
    if label:
        text(x + 12, (y1 + y2) / 2 + 4, label, size=11, fill=MUTED)


M = 48
INNER = W - 2 * M

add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    f'font-family="{FONT}" role="img" aria-label="PM Triage runtime detail: a Next.js frontend on '
    f'Vercel, a FastAPI backend on Render containing ingest, detection, classification, agent and '
    f'decision modules plus a mounted CMMS service, backed by Supabase Postgres and an optional '
    f'capped OpenRouter model.">')
add('<defs>'
    '<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M 0 1 L 9 5 L 0 9 z" fill="#9BA7B7"/></marker>'
    '<filter id="sh" x="-20%" y="-20%" width="140%" height="140%">'
    '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#1B2434" flood-opacity="0.07"/>'
    '</filter></defs>')
rect(0, 0, W, H, rx=0, fill="#FFFFFF")

# ---------------------------------------------------------------- header
text(M, 54, "PM Triage — what runs where", size=26, weight=700)
text(M, 82, "Every box is a real file or a real service. The arrows are the only paths between them.",
     size=14, fill=MUTED)


def band(y, h, title, sub, accent):
    rect(M, y, INNER, h, rx=18, fill="#FAFBFC", stroke=LINE, sw=1.1)
    text(M + 24, y + 32, title, size=13.5, weight=700, fill=INK)
    tw = est(title, 13.5, 700) * 1.28
    text(M + 24 + tw + 16, y + 32, sub, size=12, fill=FAINT)
    add(f'<rect x="{M:.1f}" y="{y:.1f}" width="4" height="{h:.1f}" rx="2" fill="{accent}"/>')


def modbox(x, y, w, h, title, lines, color, bg, mono_title=True):
    rect(x, y, w, h, rx=11, fill="#FFFFFF", stroke=LINE, sw=1.1, extra='filter="url(#sh)"')
    add(f'<rect x="{x:.1f}" y="{y + 11:.1f}" width="3" height="{h - 22:.1f}" rx="1.5" fill="{color}"/>')
    text(x + 16, y + 24, title, size=11.5, fill=color, weight=600, mono=mono_title)
    ty = y + 41
    for ln in lines:
        text(x + 16, ty, ln, size=10.5, fill=MUTED)
        ty += 14


# ---------------------------------------------------------------- band 1: browser
B1_Y, B1_H = 118, 118
band(B1_Y, B1_H, "BROWSER", "Next.js App Router, deployed on Vercel", GREY)
px = M + 24
for label in ["/  fleet", "/cases", "/cases/[id]", "/machines/[id]", "/cmms", "/audit", "/eval"]:
    px += chip(px, B1_Y + 52, label, INK, GREY_BG, size=11.5, mono=True) + 10
text(M + 24, B1_Y + 100, "lib/api.ts is the only network layer: one base URL, and a bearer token "
     "on every state-changing call.", size=11.5, fill=MUTED)

# ---------------------------------------------------------------- band 2: backend
B2_Y, B2_H = 300, 494
band(B2_Y, B2_H, "BACKEND", "FastAPI on Render — one ASGI app, one async event loop", BLUE)

vaarrow(W / 2, B1_Y + B1_H + 8, B2_Y - 8, "HTTPS · JSON · bearer token on every write")

COL_W = (INNER - 48 - 3 * 20) / 4
COL_X = [M + 24 + i * (COL_W + 20) for i in range(4)]
COL_TOP = B2_Y + 62

headers = [
    ("INGEST", GREY),
    ("DETECT + CLASSIFY", BLUE),
    ("AGENT", AMBER),
    ("DECIDE + WRITE BACK", GREEN),
]
for i, (htext, hcolor) in enumerate(headers):
    text(COL_X[i], COL_TOP - 14, htext, size=9.5, fill=hcolor, weight=700, tracking=1.4)

columns = [
    [
        ("simulator.py", ["eight assets, one reading every 3 s,", "detection runs on every reading"], GREY),
        ("replay.py", ["real SKAB pump and CWRU bearing", "episodes, replayed row by row"], GREY),
        ("POST /simulate/inject", ["faults are manual in production", "(SPONTANEOUS_FAULT_PROB=0)"], GREY),
        ("retention.py", ["raw telemetry pruned after 24 h;", "cases and audit events are records"], GREY),
    ],
    [
        ("detector.py", ["fixed limits + robust median/MAD,", "sustained, one case per event"], BLUE),
        ("classifier.py", ["signature rules over cross-signal", "trends — owns the clear faults"], BLUE),
        ("ml_classifier.py", ["Extra Trees, trained on one job:", "suction vs discharge restriction"], VIOLET),
        ("novelty + roster guard", ["IsolationForest and an exact feature", "roster; unknown input abstains"], VIOLET),
    ],
    [
        ("agent/triage.py", ["bounded tool loop; a provider failure", "falls back to the free policy"], AMBER),
        ("agent/tools.py", ["machine info · recent telemetry ·", "history search · recurrence count"], AMBER),
        ("agent/llm.py", ["mock policy or OpenRouter —", "identical tool protocol"], AMBER),
        ("agent/calibration.py", ["grounds confidence in precedent and", "signature; below 0.45 it abstains"], AMBER),
    ],
    [
        ("priority.py", ["P1–P4 from criticality, severity,", "recurrence, safety. Agent may ±1"], GREEN),
        ("POST /cases/{id}/decision", ["the only path to approval; needs a", "token and a named reviewer"], GREEN),
        ("agent/cmms_adapter.py", ["httpx + Idempotency-Key + retry,", "only after an approval"], GREEN),
        ("audit.py", ["append-only: system, agent,", "human:<name>, with a timestamp"], GREEN),
    ],
]

BOX_H = 66
BOX_GAP = 12
for i, col in enumerate(columns):
    y = COL_TOP
    for title, lines, color in col:
        bg = {BLUE: BLUE_BG, VIOLET: VIOLET_BG, AMBER: AMBER_BG, GREEN: GREEN_BG, GREY: GREY_BG}[color]
        modbox(COL_X[i], y, COL_W, BOX_H, title, lines, color, bg)
        y += BOX_H + BOX_GAP

# flow arrows between columns
for i in range(3):
    x1 = COL_X[i] + COL_W + 3
    x2 = COL_X[i + 1] - 3
    ymid = COL_TOP + 130
    add(f'<path d="M {x1:.1f} {ymid:.1f} L {x2:.1f} {ymid:.1f}" stroke="#C6CEDA" stroke-width="1.6" '
        f'marker-end="url(#ah)" fill="none"/>')

# mounted CMMS service
CM_Y = B2_Y + B2_H - 96
rect(M + 24, CM_Y, INNER - 48, 72, rx=12, fill="#FFFFFF", stroke=GREEN, sw=1.2,
     extra='stroke-dasharray="6 5"')
text(M + 40, CM_Y + 28, "app.mount(\"/cmms\")  →  cmms/service.py", size=12, fill=GREEN,
     weight=600, mono=True)
text(M + 40, CM_Y + 50, "A separate ASGI service with its own work-order store. The triage backend "
     "reaches it over HTTP with an idempotency key and a retry — never by importing it. Point "
     "CMMS_BASE_URL at SAP or Maximo and nothing above this line changes.",
     size=11.5, fill=MUTED)

# ---------------------------------------------------------------- band 3: data & providers
B3_Y, B3_H = 858, 178
band(B3_Y, B3_H, "STATE + PROVIDERS", "outside the request path", VIOLET)

C3_W = (INNER - 48 - 2 * 20) / 3
C3_X = [M + 24 + i * (C3_W + 20) for i in range(3)]

vaarrow(C3_X[0] + C3_W / 2, B2_Y + B2_H + 8, B3_Y - 8, "SQLAlchemy")
vaarrow(C3_X[1] + C3_W / 2, B2_Y + B2_H + 8, B3_Y - 8, "live mode only", dashed=True)

# db
rect(C3_X[0], B3_Y + 46, C3_W, 112, rx=11, fill="#FFFFFF", stroke=LINE, sw=1.1)
text(C3_X[0] + 16, B3_Y + 68, "Supabase Postgres · schema pm_triage", size=12, weight=600)
tx = C3_X[0] + 16
ty = B3_Y + 80
for t in ["machines", "telemetry", "anomalies", "triage_cases", "llm_calls", "maintenance_logs",
          "audit_events"]:
    w = est(t, 10, 400) + 16
    if tx + w > C3_X[0] + C3_W - 16:
        tx = C3_X[0] + 16
        ty += 24
    rect(tx, ty, w, 20, rx=6, fill=GREY_BG)
    text(tx + 8, ty + 14, t, size=10, fill=MUTED, mono=True)
    tx += w + 6
text(C3_X[0] + 16, B3_Y + 146, "SQLite locally and in tests — one domain model either way.",
     size=10.5, fill=FAINT)

# llm
rect(C3_X[1], B3_Y + 46, C3_W, 112, rx=11, fill="#FFFFFF", stroke=LINE, sw=1.1)
text(C3_X[1] + 16, B3_Y + 68, "OpenRouter · deepseek/deepseek-v4-flash", size=12, weight=600)
for i, ln in enumerate([
    "Off by default: LLM_MODE=mock even when a key exists.",
    "12 calls/day · $0.25/day · 700 output tokens per call.",
    "Every request costed and stored in llm_calls; over cap, the case",
    "finishes free and deterministic and says so in its trace.",
]):
    text(C3_X[1] + 16, B3_Y + 88 + i * 14, ln, size=10.5, fill=MUTED)

# ci
rect(C3_X[2], B3_Y + 46, C3_W, 112, rx=11, fill="#FFFFFF", stroke=LINE, sw=1.1)
text(C3_X[2] + 16, B3_Y + 68, "GitHub Actions", size=12, weight=600)
for i, ln in enumerate([
    "keep-warm.yml — a health ping every 10 minutes so the free",
    "Render instance answers a demo. It never runs triage.",
    "eval.yml — the offline evaluation suite.",
    "Backend tests cover detection, calibration, budget and CMMS write-back.",
]):
    text(C3_X[2] + 16, B3_Y + 88 + i * 14, ln, size=10.5, fill=MUTED)

add("</svg>")

path = Path(__file__).resolve().parents[4] / "docs" / "diagrams" / "architecture-detail.svg"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("\n".join(out) + "\n")
print("wrote", path)
