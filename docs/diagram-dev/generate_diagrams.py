"""Generate accessionflow documentation diagrams as hand-editable SVG.

Usage (from anywhere):

    python docs/diagram-dev/generate_diagrams.py

Writes the SVGs (plus a -dark variant of each) to docs/source/_static/images/diagrams/, which the Sphinx pages and
README.md reference. Stage names, order and descriptions live in OVERVIEW_STAGES and
COMING_STAGES near the top of the overview section.

Design rules for Illustrator-friendliness:
  * every visual unit is a named <g id="..."> (becomes a layer/group)
  * all styling is inline attributes (no CSS, no classes)
  * text stays as live <text>, baselines set explicitly (no dominant-baseline)
  * arrowheads are plain polygons (no <marker>)
"""

import re
from math import atan2, cos, sin
from pathlib import Path
from xml.sax.saxutils import escape

FONT = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', Menlo, Consolas, monospace"

INK = "#172033"
MUTED = "#5A6478"
LINE = "#C3CBD6"
PANEL = "#F5F7FA"
WHITE = "#FFFFFF"
IMG = "#111827"  # image thumbnails
ON = "#FFFFFE"  # text/marks drawn on solid accent fills

TEAL = "#0E7C86"
TEAL_L = "#E3F3F4"
TEAL_D = "#0A5C63"
SLATE = "#475569"
SLATE_L = "#EEF1F5"
INDIGO = "#4338CA"
INDIGO_L = "#EEF0FD"
AMBER = "#B45309"
AMBER_L = "#FEF3E2"
RED = "#B42318"


# ---------------------------------------------------------------- primitives
def rect(x, y, w, h, rx=10, fill=WHITE, stroke=LINE, sw=1.5, dash=None, id=None):
    a = f' id="{id}"' if id else ""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<rect{a} x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
    )


def text(
    x, y, s, size=14, weight=400, fill=INK, anchor="middle", mono=False, italic=False
):
    fam = MONO if mono else FONT
    it = ' font-style="italic"' if italic else ""
    return (
        f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{it}>{escape(s)}</text>'
    )


def line(x1, y1, x2, y2, stroke=LINE, sw=1.5, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
        f'stroke-width="{sw}" stroke-linecap="round"{d}/>'
    )


def head(x, y, ang, color, size=9):
    """Arrowhead polygon with its tip at (x, y) pointing along ang."""
    p1 = (
        x - size * cos(ang) + size * 0.55 * sin(ang),
        y - size * sin(ang) - size * 0.55 * cos(ang),
    )
    p2 = (
        x - size * cos(ang) - size * 0.55 * sin(ang),
        y - size * sin(ang) + size * 0.55 * cos(ang),
    )
    return (
        f'<polygon points="{x:.1f},{y:.1f} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" '
        f'fill="{color}"/>'
    )


def arrow(x1, y1, x2, y2, color=SLATE, sw=2, dash=None, both=False, id=None):
    ang = atan2(y2 - y1, x2 - x1)
    s = 8
    ex, ey = x2 - s * cos(ang), y2 - s * sin(ang)
    sx, sy = (x1 + s * cos(ang), y1 + s * sin(ang)) if both else (x1, y1)
    parts = [line(sx, sy, ex, ey, color, sw, dash), head(x2, y2, ang, color)]
    if both:
        parts.append(head(x1, y1, ang + 3.14159265, color))
    return group(id or "arrow", parts)


def elbow(points, color=SLATE, sw=2, dash=None, id="connector"):
    """Orthogonal polyline ending in an arrowhead."""
    (ax, ay), (bx, by) = points[-2], points[-1]
    ang = atan2(by - ay, bx - ax)
    pts = list(points[:-1]) + [(bx - 8 * cos(ang), by - 8 * sin(ang))]
    d = f' stroke-dasharray="{dash}"' if dash else ""
    poly = " ".join(f"{x},{y}" for x, y in pts)
    return group(
        id,
        [
            f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linejoin="round" stroke-linecap="round"{d}/>',
            head(bx, by, ang, color),
        ],
    )


_ids = {}


def group(id, children):
    n = _ids.get(id, 0)
    _ids[id] = n + 1
    gid = id if n == 0 else f"{id}-{n + 1}"
    return f'<g id="{gid}">\n  ' + "\n  ".join(children) + "\n</g>"


def svg(w, h, title, children):
    _ids.clear()
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f"<title>{escape(title)}</title>\n"
        + group(
            "background", [rect(0, 0, w, h, rx=16, fill=WHITE, stroke="#E2E7EE", sw=1)]
        )
        + "\n"
        + "\n".join(children)
        + "\n</svg>\n"
    )


def tag(x, y, label, color=AMBER, fill=AMBER_L, size=10.5, anchor="middle"):
    w = len(label) * size * 0.66 + 14
    x0 = x - w / 2 if anchor == "middle" else x
    return group(
        "tag",
        [
            rect(x0, y, w, size + 9, rx=(size + 9) / 2, fill=fill, stroke="none", sw=0),
            text(x0 + w / 2, y + size + 2.5, label.upper(), size, 700, color),
        ],
    )


def file_icon(x, y, w=22, h=28, fill=WHITE, stroke=SLATE, sw=1.4, id="file"):
    f = 7
    return group(
        id,
        [
            f'<path d="M{x},{y} h{w - f} l{f},{f} v{h - f} h{-w} z" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linejoin="round"/>',
            f'<path d="M{x + w - f},{y} v{f} h{f}" fill="none" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linejoin="round"/>',
        ],
    )


def cylinder(cx, y, w, h, fill=INDIGO_L, stroke=INDIGO, sw=1.6, id="repository"):
    rx, ry = w / 2, w * 0.14
    x = cx - rx
    return group(
        id,
        [
            f'<path d="M{x},{y + ry} v{h - 2 * ry} a{rx},{ry} 0 0 0 {w},0 v{-(h - 2 * ry)}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>',
            f'<ellipse cx="{cx}" cy="{y + ry}" rx="{rx}" ry="{ry}" fill="{WHITE}" stroke="{stroke}" stroke-width="{sw}"/>',
            f'<path d="M{x},{y + h * 0.45} a{rx},{ry} 0 0 0 {w},0" fill="none" stroke="{stroke}" '
            f'stroke-width="{sw * 0.7}" opacity="0.5"/>',
        ],
    )


def scanner_icon(cx, cy, s=1.0, color=SLATE):
    """MRI scanner glyph (front view): housing, bore and patient table."""
    W, H = 76 * s, 62 * s
    x, y = cx - W / 2, cy - H / 2
    r = 20 * s
    return group(
        "scanner-icon",
        [
            rect(x, y, W, H, rx=14 * s, fill=WHITE, stroke=color, sw=1.8),
            f'<circle cx="{cx}" cy="{cy - 2 * s}" r="{r}" fill="{SLATE_L}" stroke="{color}" stroke-width="1.8"/>',
            rect(
                cx - r * 0.86,
                cy + 6 * s,
                r * 1.72,
                5 * s,
                rx=2.5 * s,
                fill=color,
                stroke="none",
                sw=0,
            ),
            rect(
                x + 8 * s,
                y + H - 2 * s,
                W - 16 * s,
                6 * s,
                rx=3 * s,
                fill=color,
                stroke="none",
                sw=0,
            ),
        ],
    )


def title_block(x, title, subtitle):
    return group(
        "title",
        [
            text(x, 54, title, 26, 700, INK, "start"),
            text(x, 81, subtitle, 15, 400, MUTED, "start"),
        ],
    )


STAGES = [
    ("collate", ["Group files into", "accessions"], False),
    ("attach", ["Link secondary data", "to its accession"], True),
    ("label", ["Assign project,", "subject, session IDs"], False),
    ("deidentify", ["Remove identifying", "header metadata"], True),
    ("package", ["Package acquisitions", "into resources"], True),
    ("store", ["Upload to the", "repository"], False),
]


def mini(x, y, label, kind="stage", w=None, h=30):
    """Small stage/repository pill. Returns (svg, width)."""
    w = w or len(label) * 8.2 + 26
    styles = {
        "stage": (WHITE, TEAL, TEAL_D, None),
        "opt": (WHITE, TEAL, TEAL_D, "5 4"),
        "moved": (AMBER_L, AMBER, AMBER, None),
        "repo": (INDIGO_L, INDIGO, INDIGO, None),
    }
    fill, stroke, ink, dash = styles[kind]
    return (
        group(
            f"mini-{label.replace(' ', '-')}",
            [
                rect(x, y, w, h, rx=h / 2, fill=fill, stroke=stroke, sw=1.4, dash=dash),
                text(x + w / 2, y + h / 2 + 4.5, label, 12.5, 700, ink, mono=True),
            ],
        ),
        w,
    )


def flex_panel(x, y, w, h, title, sub):
    return [
        rect(x, y, w, h, rx=14, fill=PANEL, stroke="none", sw=0),
        text(x + 20, y + 30, title, 15, 700, INK, "start"),
        text(x + 20, y + h - 20, sub, 12.5, 400, MUTED, "start"),
    ]


def flex_reordered(x, y, w, h):
    P = flex_panel(x, y, w, h, "Reorder stages", "e.g. deidentify before labelling")
    P.append(tag(x + w - 20 - 80, y + 14, "reordered", AMBER, AMBER_L, anchor="start"))
    cy = y + h / 2 - 2
    cx = x + 24
    seq = [
        ("collate", "stage"),
        ("deidentify", "moved"),
        ("label", "stage"),
        ("annotate", "opt"),
        ("store", "stage"),
    ]
    for i, (n, k) in enumerate(seq):
        g, ww = mini(cx, cy - 15, n, k)
        P.append(g)
        if i < len(seq) - 1:
            P.append(arrow(cx + ww + 3, cy, cx + ww + 19, cy, TEAL, sw=1.5, id="arrow"))
        cx += ww + 22
    return P


def flex_branched(x, y, w, h):
    P = flex_panel(
        x,
        y,
        w,
        h,
        "Branch to several destinations",
        "e.g. identifiable copy to a secure archive, de-identified copy to research",
    )
    P.append(tag(x + w - 20 - 76, y + 14, "branched", AMBER, AMBER_L, anchor="start"))
    cy = y + h / 2 - 2
    cx = x + 24
    for n in ("collate", "label"):
        g, ww = mini(cx, cy - 15, n)
        P.append(g)
        P.append(arrow(cx + ww + 3, cy, cx + ww + 19, cy, TEAL, sw=1.5, id="arrow"))
        cx += ww + 22
    # fork point
    fx = cx - 3
    P[-1] = group("arrow", [line(fx - 16, cy, fx, cy, TEAL, 1.5)])
    P.append(f'<circle cx="{fx}" cy="{cy}" r="4.5" fill="{AMBER}"/>')
    up, dn = cy - 30, cy + 30
    bx = fx + 22
    # upper branch: deidentify -> store xnat -> XNAT
    P.append(elbow([(fx, cy), (fx, up), (bx - 2, up)], TEAL, sw=1.5, id="arrow-branch"))
    g, ww = mini(bx, up - 15, "deidentify", "opt")
    P.append(g)
    ux = bx + ww
    P.append(arrow(ux + 3, up, ux + 19, up, TEAL, sw=1.5, id="arrow"))
    g, ww = mini(ux + 22, up - 15, "store xnat")
    P.append(g)
    # lower branch: store s3
    P.append(elbow([(fx, cy), (fx, dn), (bx - 2, dn)], TEAL, sw=1.5, id="arrow-branch"))
    g, ww = mini(bx, dn - 15, "store s3")
    P.append(g)
    return P


# ------------------------------------------------- 1. pipeline overview (README)
OVERVIEW_STAGES = [
    ("collate", ["Group files into", "accessions"], False),
    ("attach", ["Link secondary data", "to its accession"], True),
    ("label", ["Assign project,", "subject, session IDs"], False),
    ("deidentify", ["Remove identifying", "header metadata"], True),
    ("annotate", ["Record metadata to", "upload with the data"], True),
    ("package", ["Package acquisitions", "into resources"], True),
    ("store", ["Upload to the", "repository"], False),
]
COMING_STAGES = [("verify", "Check acquisitions against the expected protocol")]


def overview():
    W, H = 1610, 740
    out = [
        title_block(
            40,
            "accessionflow",
            "From instrument to repository through a growing set of configurable, reorderable stages",
        )
    ]
    top, h = 140, 168
    cy = top + h / 2

    # source
    out.append(
        group(
            "source",
            [
                rect(40, top, 156, h, rx=14, fill=SLATE_L, stroke=SLATE, sw=1.5),
                scanner_icon(118, top + 58, 0.95),
                text(118, top + 124, "Instrument", 16, 700, INK),
                text(118, top + 144, "primary & secondary data", 11, 400, MUTED),
            ],
        )
    )

    x0, sw_, gap = 244, 136, 24
    xs = [x0 + i * (sw_ + gap) for i in range(len(OVERVIEW_STAGES))]
    out.append(arrow(196 + 4, cy, xs[0] - 4, cy, SLATE, id="arrow-source"))
    stage_groups = []
    for i, (name, desc, opt) in enumerate(OVERVIEW_STAGES):
        x = xs[i]
        size = 18 if len(name) <= 10 else 15
        parts = [
            rect(
                x,
                top,
                sw_,
                h,
                rx=14,
                fill=WHITE if opt else TEAL_L,
                stroke=TEAL,
                sw=1.8,
                dash="6 5" if opt else None,
            ),
            f'<circle cx="{x + sw_ / 2}" cy="{top + 32}" r="14" fill="{TEAL}"/>',
            text(x + sw_ / 2, top + 37, str(i + 1), 13, 700, ON),
            text(x + sw_ / 2, top + 76, name, size, 700, TEAL_D, mono=True),
            text(x + sw_ / 2, top + 101, desc[0], 12, 400, MUTED),
            text(x + sw_ / 2, top + 118, desc[1], 12, 400, MUTED),
        ]
        if opt:
            parts.append(tag(x + sw_ / 2, top + 134, "optional", TEAL_D, TEAL_L))
        stage_groups.append(group(f"stage-{name}", parts))
        if i:
            stage_groups.append(
                arrow(xs[i - 1] + sw_ + 4, cy, x - 4, cy, TEAL, id=f"arrow-{name}")
            )
    out.append(group("stages", stage_groups))

    # repositories
    end = xs[-1] + sw_
    rx_, rw = end + 64, 164
    repos = [text(rx_ + rw / 2, top + 22, "Repositories", 15, 700, INK)]
    fan = []
    mx = end + 26
    for j, (lbl, dash) in enumerate(
        [("XNAT", None), ("Folder store", None), ("Others via plugins", "5 4")]
    ):
        yy = top + 38 + j * 44
        repos += [
            rect(
                rx_,
                yy,
                rw,
                36,
                rx=10,
                fill=INDIGO_L if not dash else WHITE,
                stroke=INDIGO,
                sw=1.4,
                dash=dash,
            ),
            text(
                rx_ + rw / 2,
                yy + 23,
                lbl,
                13.5,
                700 if not dash else 400,
                INDIGO if not dash else MUTED,
            ),
        ]
        ty = yy + 18
        fan.append(
            elbow(
                [(end + 2, cy), (mx, cy), (mx, ty), (rx_ - 2, ty)],
                INDIGO,
                sw=1.6,
                dash="5 4" if dash else None,
                id="arrow-store",
            )
        )
    out.append(group("store-fan-out", fan))
    out.append(group("repositories", repos))

    # note under the chain
    by = top + h + 22
    out.append(
        group(
            "stage-note",
            [
                line(xs[0], by, end, by, LINE, 1.5),
                line(xs[0], by - 8, xs[0], by, LINE, 1.5),
                line(end, by - 8, end, by, LINE, 1.5),
                text(
                    (xs[0] + end) / 2,
                    by + 26,
                    "Example configuration — each stage is a standalone command, chosen and ordered per deployment",
                    13.5,
                    400,
                    MUTED,
                ),
            ],
        )
    )

    # flexible pipelines: reorder + branch examples
    fy, fh = by + 50, 176
    pw = (end - xs[0] - 20) / 2
    out.append(group("example-reordered", flex_reordered(xs[0], fy, pw, fh)))
    out.append(group("example-branched", flex_branched(xs[0] + pw + 20, fy, pw, fh)))

    # coming-stages shelf
    sy, sh = fy + fh + 20, 92
    shelf = [
        rect(
            xs[0],
            sy,
            end - xs[0],
            sh,
            rx=14,
            fill=AMBER_L,
            stroke=AMBER,
            sw=1.5,
            dash="6 5",
        ),
        tag(xs[0] + 20, sy + 16, "coming stages", AMBER, WHITE, anchor="start"),
        text(
            xs[0] + 20, sy + 64, "New stages slot into the chain", 13, 600, INK, "start"
        ),
        text(
            xs[0] + 20,
            sy + 81,
            "wherever a deployment needs them",
            13,
            400,
            MUTED,
            "start",
        ),
    ]
    cx_ = xs[0] + 300
    for name, desc in COMING_STAGES:
        cw_ = 300
        shelf.append(
            group(
                f"coming-{name}",
                [
                    rect(
                        cx_,
                        sy + 18,
                        cw_,
                        56,
                        rx=12,
                        fill=WHITE,
                        stroke=AMBER,
                        sw=1.5,
                        dash="5 4",
                    ),
                    text(cx_ + cw_ / 2, sy + 42, name, 15, 700, AMBER, mono=True),
                    text(cx_ + cw_ / 2, sy + 61, desc, 11.5, 400, MUTED),
                ],
            )
        )
        cx_ += cw_ + 20
    shelf.append(
        group(
            "coming-plugins",
            [
                rect(
                    cx_,
                    sy + 18,
                    260,
                    56,
                    rx=12,
                    fill="none",
                    stroke=AMBER,
                    sw=1.5,
                    dash="5 4",
                ),
                f'<circle cx="{cx_ + 30}" cy="{sy + 46}" r="11" fill="{AMBER}"/>',
                line(cx_ + 24.5, sy + 46, cx_ + 35.5, sy + 46, ON, 2),
                line(cx_ + 30, sy + 40.5, cx_ + 30, sy + 51.5, ON, 2),
                text(cx_ + 52, sy + 42, "Site-specific stages", 14, 700, INK, "start"),
                text(
                    cx_ + 52,
                    sy + 61,
                    "added through plugins",
                    11.5,
                    400,
                    MUTED,
                    "start",
                ),
            ],
        )
    )
    out.append(group("coming-stages", shelf))
    return svg(W, H, "accessionflow pipeline overview", out)


# ------------------------------------------------- 2. stage-by-stage
def session_box(cx, y, w=144, h=150, label="accession"):
    return [
        rect(cx - w / 2, y, w, h, rx=10, fill=WHITE, stroke=SLATE, sw=1.2, dash="4 4"),
        rect(
            cx - w / 2 + 10,
            y - 9,
            len(label) * 7.2 + 14,
            18,
            rx=9,
            fill=SLATE,
            stroke="none",
            sw=0,
        ),
        text(cx - w / 2 + 17 + len(label) * 3.6, y + 4, label, 11, 600, ON, mono=True),
    ]


def series_stack(x, y, lbl, color=TEAL, fill=TEAL_L):
    p = [
        file_icon(x + 8, y, fill=fill, stroke=color, id="file"),
        file_icon(x + 4, y + 4, fill=fill, stroke=color, id="file"),
        file_icon(x, y + 8, fill=WHITE, stroke=color, id="file"),
        text(x + 15, y + 54, lbl, 11, 600, color, mono=True),
    ]
    return group("series", p)


def stage_by_stage():
    W, H = 1656, 520
    out = [
        title_block(
            40,
            "What each stage does",
            "How an accession is transformed on its way to the repository",
        )
    ]
    cols = [("incoming", None, False)] + [(n, d, o) for n, d, o in OVERVIEW_STAGES]
    cw, gap, x0 = 176, 24, 40
    hy, hh = 116, 42
    py, ph = 178, 300
    captions = {
        "incoming": ["Primary and secondary", "data arrive unsorted"],
        "collate": ["Sorted into accessions", "and acquisitions"],
        "attach": ["Secondary data linked", "to its accession"],
        "label": ["Project, subject and", "session IDs assigned"],
        "annotate": ["Chosen & derived fields", "recorded for upload"],
        "deidentify": ["Identifying header", "fields removed"],
        "package": ["Each acquisition packaged", "into repository resources"],
        "store": ["Uploaded to the", "repository"],
    }
    for i, (name, _, opt) in enumerate(cols):
        x = x0 + i * (cw + gap)
        cx = x + cw / 2
        incoming = name == "incoming"
        # header
        hdr = [
            rect(
                x,
                hy,
                cw,
                hh,
                rx=21,
                fill=SLATE_L if incoming else (WHITE if opt else TEAL_L),
                stroke=SLATE if incoming else TEAL,
                sw=1.6,
                dash="6 5" if opt else None,
            ),
            text(
                cx,
                hy + 27,
                "input" if incoming else name,
                16,
                700,
                SLATE if incoming else TEAL_D,
                mono=not incoming,
            ),
        ]
        parts = [group("header", hdr)]
        if opt:
            parts.append(tag(cx, hy - 24, "optional", TEAL_D, TEAL_L))
        if i:
            parts.append(
                arrow(
                    x - gap + 3,
                    hy + hh / 2,
                    x - 3,
                    hy + hh / 2,
                    TEAL if not incoming else SLATE,
                    sw=1.8,
                    id="arrow",
                )
            )
        # panel
        parts.append(rect(x, py, cw, ph, rx=14, fill=PANEL, stroke="none", sw=0))
        iy = py + 34  # illustration top
        ill = []
        if name == "incoming":
            pos = [
                (-58, 6),
                (-20, -4),
                (24, 10),
                (52, 0),
                (-46, 52),
                (-6, 44),
                (36, 58),
                (-58, 102),
                (-16, 92),
                (22, 104),
                (52, 86),
                (-30, 140),
                (14, 146),
            ]
            for k, (dx, dy) in enumerate(pos):
                raw = k in (3, 8)
                ill.append(
                    file_icon(
                        cx + dx - 11,
                        iy + dy + 6,
                        fill=AMBER_L if raw else WHITE,
                        stroke=AMBER if raw else SLATE,
                    )
                )
        elif name in ("collate", "attach"):
            ill += session_box(cx, iy, h=170)
            n = 3 if name == "collate" else 2
            for k in range(n):
                sx = cx - 62 + k * 44 + (0 if n == 3 else 0)
                ill.append(series_stack(sx, iy + 26, f"S{k + 1}"))
            if name == "collate":
                for k in range(3):
                    ill.append(series_stack(cx - 62 + k * 44, iy + 92, f"S{k + 4}"))
            else:
                for k in range(2):
                    ill.append(series_stack(cx - 62 + k * 44, iy + 92, f"S{k + 3}"))
                # attached raw file
                ax_, ay_ = cx + 28, iy + 58
                ill.append(file_icon(ax_, ay_, fill=AMBER_L, stroke=AMBER, sw=1.6))
                ill.append(
                    text(ax_ + 11, ay_ + 46, "secondary", 9.5, 600, AMBER, mono=True)
                )
                ill.append(
                    group(
                        "plus",
                        [
                            f'<circle cx="{ax_ + 24}" cy="{ay_ - 2}" r="9" fill="{AMBER}"/>',
                            line(ax_ + 19.5, ay_ - 2, ax_ + 28.5, ay_ - 2, ON, 2),
                            line(ax_ + 24, ay_ - 6.5, ax_ + 24, ay_ + 2.5, ON, 2),
                        ],
                    )
                )
        elif name == "label":
            ill += session_box(cx, iy, h=170, label="MR01")
            rows = [("project", "PRJ001"), ("subject", "SUBJ042"), ("session", "MR01")]
            for k, (key, val) in enumerate(rows):
                yy = iy + 24 + k * 46
                ill.append(
                    group(
                        f"id-{key}",
                        [
                            text(cx - 56, yy + 10, key, 10.5, 500, MUTED, "start"),
                            rect(
                                cx - 58,
                                yy + 16,
                                116,
                                24,
                                rx=6,
                                fill=TEAL_L,
                                stroke=TEAL,
                                sw=1.2,
                            ),
                            text(cx, yy + 33, val, 12.5, 700, TEAL_D, mono=True),
                        ],
                    )
                )
        elif name == "annotate":
            hdr = [
                rect(cx - 72, iy, 144, 62, rx=8, fill=WHITE, stroke=SLATE, sw=1.2),
                text(cx - 62, iy + 17, "DICOM header", 10.5, 700, INK, "start"),
            ]
            for k, (f, v) in enumerate(
                [("Manufacturer", "Siemens"), ("PatientAge", "042Y")]
            ):
                hdr.append(
                    text(
                        cx - 62,
                        iy + 35 + k * 15,
                        f,
                        9.5,
                        500,
                        MUTED,
                        "start",
                        mono=True,
                    )
                )
                hdr.append(
                    text(cx + 62, iy + 35 + k * 15, v, 9.5, 600, INK, "end", mono=True)
                )
            ill.append(group("header-card", hdr))
            ill.append(arrow(cx, iy + 64, cx, iy + 84, TEAL, sw=1.6, id="arrow-fields"))
            md = [
                rect(cx - 72, iy + 86, 144, 84, rx=8, fill=TEAL_L, stroke=TEAL, sw=1.4),
                text(
                    cx - 62,
                    iy + 103,
                    "metadata for repository",
                    10.5,
                    700,
                    TEAL_D,
                    "start",
                ),
            ]
            rows = [
                ("vendor", "Siemens", False),
                ("age", "42", False),
                ("age_group", "40-49", True),
            ]
            for k, (f, v, derived) in enumerate(rows):
                yy = iy + 122 + k * 16
                md.append(text(cx - 62, yy, f, 9.5, 600, TEAL_D, "start", mono=True))
                md.append(text(cx + 62, yy, v, 9.5, 600, INK, "end", mono=True))
                if derived:
                    md.append(
                        rect(
                            cx + 2,
                            yy - 10,
                            18,
                            13,
                            rx=3,
                            fill=AMBER,
                            stroke="none",
                            sw=0,
                        )
                    )
                    md.append(text(cx + 11, yy, "fx", 9, 700, ON, italic=True))
            ill.append(group("metadata-card", md))
        elif name == "deidentify":
            card = [
                rect(cx - 72, iy, 144, 170, rx=10, fill=WHITE, stroke=SLATE, sw=1.2),
                text(cx - 60, iy + 22, "DICOM header", 11, 700, INK, "start"),
            ]
            fields = [
                ("PatientName", True),
                ("PatientID", True),
                ("BirthDate", True),
                ("Institution", True),
                ("Modality", False),
                ("SeriesDesc", False),
            ]
            for k, (f, red) in enumerate(fields):
                yy = iy + 46 + k * 21
                card.append(text(cx - 60, yy, f, 10, 500, MUTED, "start", mono=True))
                if red:
                    card.append(
                        rect(
                            cx + 16,
                            yy - 10,
                            42,
                            12,
                            rx=2,
                            fill=INK,
                            stroke="none",
                            sw=0,
                        )
                    )
                else:
                    card.append(
                        text(
                            cx + 16,
                            yy,
                            "MR" if f == "Modality" else "T1w",
                            10,
                            600,
                            INK,
                            "start",
                            mono=True,
                        )
                    )
            ill.append(group("header-card", card))
        elif name == "package":
            ill.append(series_stack(cx - 15, iy, "acquisition"))
            ill.append(
                elbow(
                    [
                        (cx, iy + 62),
                        (cx, iy + 72),
                        (cx - 38, iy + 72),
                        (cx - 38, iy + 86),
                    ],
                    TEAL,
                    sw=1.5,
                    id="arrow-resource",
                )
            )
            ill.append(
                elbow(
                    [(cx, iy + 72), (cx + 38, iy + 72), (cx + 38, iy + 86)],
                    TEAL,
                    sw=1.5,
                    id="arrow-resource",
                )
            )
            # DICOM resource
            lx = cx - 72
            res = [
                rect(lx, iy + 88, 68, 82, rx=8, fill=WHITE, stroke=TEAL, sw=1.4),
                text(lx + 34, iy + 104, "DICOM", 10, 700, TEAL_D, mono=True),
                f'<path d="M{lx + 22},{iy + 112} h18 l6,6 v28 h-24 z" fill="{WHITE}" stroke="{TEAL}" '
                f'stroke-width="1.3" stroke-linejoin="round"/>',
            ]
            for k in range(4):
                res.append(
                    rect(
                        lx + 31 + (k % 2) * 4,
                        iy + 114 + k * 5,
                        4,
                        4,
                        rx=0.5,
                        fill=TEAL,
                        stroke="none",
                        sw=0,
                    )
                )
            res.append(text(lx + 34, iy + 162, ".zip", 10, 600, MUTED, mono=True))
            ill.append(group("resource-dicom", res))
            # SNAPSHOTS resource
            rx_ = cx + 4
            snap = [
                rect(rx_, iy + 88, 68, 82, rx=8, fill=WHITE, stroke=TEAL, sw=1.4),
                text(rx_ + 34, iy + 104, "SNAPSHOTS", 9, 700, TEAL_D, mono=True),
                rect(
                    rx_ + 20, iy + 112, 30, 30, rx=3, fill=SLATE_L, stroke=SLATE, sw=1
                ),
                rect(rx_ + 17, iy + 115, 30, 30, rx=3, fill=IMG, stroke=SLATE, sw=1),
                f'<ellipse cx="{rx_ + 32}" cy="{iy + 130}" rx="9" ry="11" fill="#9AA4B2"/>',
                f'<ellipse cx="{rx_ + 32}" cy="{iy + 130}" rx="4.5" ry="6" fill="#5A6478"/>',
                text(rx_ + 34, iy + 162, ".gif", 10, 600, MUTED, mono=True),
            ]
            ill.append(group("resource-snapshots", snap))
        elif name == "store":
            ill.append(cylinder(cx, iy + 20, 104, 118))
            ill.append(text(cx, iy + 108, "repository", 12, 700, INDIGO, mono=True))
            ill.append(arrow(cx, iy + 4, cx, iy + 20 + 2, INDIGO, sw=2, id="arrow-in"))
        parts.append(group("illustration", ill))
        cap = captions[name]
        parts.append(
            group(
                "caption",
                [
                    text(cx, py + ph - 42, cap[0], 13, 500, INK),
                    text(cx, py + ph - 23, cap[1], 13, 500, INK),
                ],
            )
        )
        out.append(group(f"column-{name}", parts))
    return svg(W, H, "accessionflow stage-by-stage", out)


# ------------------------------------------------- 4. architecture
def legend(x, y):
    return group(
        "legend",
        [
            rect(x, y, 26, 16, rx=4, fill=WHITE, stroke=SLATE, sw=1.4),
            text(x + 36, y + 13, "Available", 12.5, 500, MUTED, "start"),
            rect(
                x + 120, y, 26, 16, rx=4, fill=AMBER_L, stroke=AMBER, sw=1.4, dash="4 3"
            ),
            text(x + 156, y + 13, "Planned / exploratory", 12.5, 500, MUTED, "start"),
        ],
    )


def chip(
    x,
    y,
    w,
    h,
    title,
    sub=None,
    planned=False,
    color=SLATE,
    fill=WHITE,
    mono_sub=True,
    size=15,
):
    p = [
        rect(
            x,
            y,
            w,
            h,
            rx=10,
            fill=AMBER_L if planned else fill,
            stroke=AMBER if planned else color,
            sw=1.5,
            dash="5 4" if planned else None,
        )
    ]
    if sub:
        p += [
            text(x + w / 2, y + h / 2 - 3, title, size, 700, INK),
            text(
                x + w / 2,
                y + h / 2 + 16,
                sub,
                11.5,
                500,
                AMBER if planned else MUTED,
                mono=mono_sub,
            ),
        ]
    else:
        p.append(text(x + w / 2, y + h / 2 + 5, title, size, 700, INK))
    return p


def band(x, y, w, h, label, fill):
    return [
        rect(x, y, w, h, rx=16, fill=fill, stroke="none", sw=0),
        text(x + 24, y + 30, label.upper(), 12, 700, MUTED, "start"),
    ]


def architecture():
    W, H = 1240, 740
    out = [
        title_block(
            40,
            "accessionflow architecture",
            "A small core of stages, driven by interfaces above and extended by plugins below",
        )
    ]
    X, BW = 40, 1160

    # interfaces
    y1 = 116
    p = band(X, y1, BW, 116, "Interfaces", PANEL)
    p += [
        group(
            "cli",
            chip(X + 210, y1 + 28, 260, 62, "Command line", "accessionflow <stage> …"),
        ),
        group(
            "prefect",
            chip(
                X + 500,
                y1 + 28,
                260,
                62,
                "Prefect flows",
                "orchestration & scheduling",
                planned=True,
                mono_sub=False,
            ),
        ),
        group(
            "yaml",
            chip(
                X + 790,
                y1 + 28,
                260,
                62,
                "Deployment config",
                "constrained YAML",
                planned=True,
                mono_sub=False,
            ),
        ),
    ]
    out.append(group("layer-interfaces", p))
    out.append(
        arrow(
            W / 2, y1 + 116 + 4, W / 2, y1 + 116 + 30, SLATE, id="arrow-interfaces-core"
        )
    )

    # core
    y2 = y1 + 146
    p = band(X, y2, BW, 190, "Core", TEAL_L)
    cw_, g_ = 120, 14
    names = [s[0] for s in OVERVIEW_STAGES]
    sx0 = X + 210
    for i, n in enumerate(names):
        opt = OVERVIEW_STAGES[i][2]
        xx = sx0 + i * (cw_ + g_)
        p.append(
            group(
                f"core-{n}",
                [
                    rect(
                        xx,
                        y2 + 26,
                        cw_,
                        46,
                        rx=23,
                        fill=WHITE,
                        stroke=TEAL,
                        sw=1.6,
                        dash="6 5" if opt else None,
                    ),
                    text(
                        xx + cw_ / 2,
                        y2 + 54,
                        n,
                        15 if len(n) <= 10 else 13.5,
                        700,
                        TEAL_D,
                        mono=True,
                    ),
                ],
            )
        )
        if i:
            p.append(
                arrow(xx - g_ + 2, y2 + 49, xx - 2, y2 + 49, TEAL, sw=1.5, id="arrow")
            )
    p.append(
        group(
            "core-model",
            chip(
                X + 210,
                y2 + 96,
                452,
                66,
                "Shared data model",
                "accessions · acquisitions · resources",
                color=TEAL,
                mono_sub=False,
            ),
        )
    )
    p.append(
        group(
            "core-staging",
            chip(
                X + 682,
                y2 + 96,
                452,
                66,
                "Staging storage",
                "local filesystem or S3",
                color=TEAL,
                mono_sub=False,
            ),
        )
    )
    out.append(group("layer-core", p))
    out.append(
        arrow(W / 2, y2 + 190 + 4, W / 2, y2 + 190 + 30, SLATE, id="arrow-core-plugins")
    )

    # plugins
    y3 = y2 + 220
    p = band(X, y3, BW, 200, "Plugins", INDIGO_L)
    p.append(
        text(
            X + 210,
            y3 + 34,
            "Sources — provide collate subcommands",
            13,
            600,
            INK,
            "start",
        )
    )
    p.append(
        group(
            "source-folder",
            chip(X + 210, y3 + 50, 140, 56, "Folder", "collate folder", color=INDIGO),
        )
    )
    p.append(
        group(
            "source-orthanc",
            chip(X + 362, y3 + 50, 140, 56, "Orthanc", "collate orthanc", color=INDIGO),
        )
    )
    p.append(
        text(
            X + 560,
            y3 + 34,
            "Data stores — provide label, store and check-store",
            13,
            600,
            INK,
            "start",
        )
    )
    p.append(
        group(
            "store-xnat",
            chip(X + 560, y3 + 50, 150, 56, "XNAT", "store xnat", color=INDIGO),
        )
    )
    p.append(
        group(
            "store-folder",
            chip(
                X + 722,
                y3 + 50,
                180,
                56,
                "Folder",
                "local · S3 · SFTP",
                color=INDIGO,
                mono_sub=False,
            ),
        )
    )
    p.append(
        group(
            "store-others",
            chip(
                X + 914, y3 + 50, 156, 56, "Other stores", "store <repo>", planned=True
            ),
        )
    )
    p.append(
        text(
            X + 210,
            y3 + 146,
            "Plugins are installed per deployment, so a site only carries the sources and stores it uses.",
            13,
            400,
            MUTED,
            "start",
        )
    )
    p.append(
        text(
            X + 210,
            y3 + 166,
            "File-type support comes from the FileFormats package and its extensions.",
            13,
            400,
            MUTED,
            "start",
        )
    )
    out.append(group("layer-plugins", p))

    out.append(legend(X, H - 40))
    return svg(W, H, "accessionflow architecture", out)


# ------------------------------------------------- 5. deployment
def node(
    x,
    y,
    w,
    h,
    title,
    sub=None,
    color=SLATE,
    fill=WHITE,
    planned=False,
    id="node",
    sub2=None,
):
    p = chip(x, y, w, h, title, None, planned, color, fill)
    p = [
        rect(
            x,
            y,
            w,
            h,
            rx=12,
            fill=AMBER_L if planned else fill,
            stroke=AMBER if planned else color,
            sw=1.6,
            dash="5 4" if planned else None,
        )
    ]
    lines_ = [s for s in (sub, sub2) if s]
    ty = y + h / 2 - (len(lines_) * 9) + 5
    p.append(text(x + w / 2, ty, title, 15, 700, INK))
    for k, s in enumerate(lines_):
        p.append(text(x + w / 2, ty + 20 + k * 17, s, 12, 400, MUTED))
    return group(id, p)


def mini_chain(x, y, names, highlight=(), w=118, h=30, gx=12, gy=12, per_row=4):
    p = []
    for i, n in enumerate(names):
        r, c = divmod(i, per_row)
        xx, yy = x + c * (w + gx), y + r * (h + gy)
        new = n in highlight
        opt = n in ("deidentify", "package")
        p.append(
            group(
                f"stage-{n.strip('†')}",
                [
                    rect(
                        xx,
                        yy,
                        w,
                        h,
                        rx=15,
                        fill=AMBER_L if new else WHITE,
                        stroke=AMBER if new else TEAL,
                        sw=1.4,
                        dash="5 4" if (new or opt) else None,
                    ),
                    text(
                        xx + w / 2,
                        yy + 20,
                        n,
                        13,
                        700,
                        AMBER if new else TEAL_D,
                        mono=True,
                    ),
                ],
            )
        )
    return group("stage-chain", p)


def chip2(x, y, label, kind="stage", h=30, size=12):
    """Compact pill for deployment rows. Returns (svg, width)."""
    w = len(label) * size * 0.64 + 22
    styles = {
        "stage": (WHITE, TEAL, TEAL_D, None),
        "opt": (WHITE, TEAL, TEAL_D, "5 4"),
        "push": (AMBER, AMBER, ON, None),
        "repo": (INDIGO_L, INDIGO, INDIGO, None),
    }
    fill, stroke, ink, dash = styles[kind]
    return (
        group(
            f"stage-{label.replace(' ', '-')}",
            [
                rect(x, y, w, h, rx=h / 2, fill=fill, stroke=stroke, sw=1.4, dash=dash),
                text(x + w / 2, y + h / 2 + 4.3, label, size, 700, ink, mono=True),
            ],
        ),
        w,
    )


def chip_row(x, y, names, gap=14, size=12):
    """Lay out a row of stage pills joined by arrows. Returns (parts, end_x, {name: (x0, x1)})."""
    parts, pos = [], {}
    for i, n in enumerate(names):
        kind = (
            "push"
            if n == "push"
            else (
                "opt"
                if n in ("attach", "annotate", "deidentify", "package")
                else "stage"
            )
        )
        g, w = chip2(x, y, n, kind, size=size)
        parts.append(g)
        pos[n] = (x, x + w)
        if i < len(names) - 1:
            parts.append(
                arrow(
                    x + w + 2, y + 15, x + w + gap - 2, y + 15, TEAL, sw=1.4, id="arrow"
                )
            )
        x += w + gap
    return parts, x - gap, pos


def zone(x, y, w, h, label, fill):
    return [
        rect(x, y, w, h, rx=14, fill=fill, stroke="none", sw=0),
        text(x + 18, y + 26, label.upper(), 11.5, 700, MUTED, "start"),
    ]


def drive_node(x, y, w, h, id="network-drive"):
    return group(
        id,
        [
            rect(x, y, w, h, rx=12, fill=WHITE, stroke=AMBER, sw=1.6),
            text(x + w / 2, y + 30, "Network drive", 15, 700, INK),
            text(x + w / 2, y + 49, "secondary data: k-space,", 11.5, 400, MUTED),
            text(x + w / 2, y + 65, "spectroscopy, list-mode", 11.5, 400, MUTED),
        ],
    )


def badge(cx, cy, letter, color, r=10):
    return group(
        f"badge-{letter}",
        [
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" stroke="{WHITE}" stroke-width="2"/>',
            text(cx, cy + 4.2, letter, 12, 700, ON),
        ],
    )


def deployment():
    W, H = 1440, 110 + 410 + 30 + 340 + 70
    out = [
        title_block(
            40,
            "Reference deployment",
            "Stages can run at the edge (on site) or server side, as each site requires",
        )
    ]

    # ======================= CURRENT
    y0, ph = 110, 410
    P = [
        rect(40, y0, W - 80, ph, rx=16, fill=PANEL, stroke="none", sw=0),
        tag(64, y0 + 18, "Current", SLATE, WHITE, size=12, anchor="start"),
        text(
            160,
            y0 + 32,
            "Each site uses one of two alternative routes:",
            13,
            600,
            INK,
            "start",
        ),
        badge(474, y0 + 28, "A", INDIGO),
        text(490, y0 + 32, "upload directly from site", 13, 400, MUTED, "start"),
        text(660, y0 + 32, "or", 13, 600, INK, "start"),
        badge(694, y0 + 28, "B", AMBER),
        text(
            710,
            y0 + 32,
            "push offsite, then store server side",
            13,
            400,
            MUTED,
            "start",
        ),
    ]
    zt, zh = y0 + 56, ph - 76
    P += [
        group("zone-edge", zone(60, zt, 940, zh, "Edge · on site (MicroK8s)", WHITE)),
        group(
            "zone-server",
            zone(1020, zt, 360, zh, "Server side · data centre / cloud", INDIGO_L),
        ),
    ]
    top = zt + 44
    # scanner + inputs
    P.append(
        group(
            "scanner",
            [
                rect(78, top + 70, 130, 140, rx=14, fill=WHITE, stroke=SLATE, sw=1.6),
                scanner_icon(143, top + 118, 0.8),
                text(143, top + 180, "MRI scanner", 14, 700, INK),
                text(143, top + 197, "or other instrument", 11, 400, MUTED),
            ],
        )
    )
    P.append(
        node(
            240,
            top,
            160,
            100,
            "Orthanc",
            "DICOM listener",
            sub2="C-STORE receiver",
            id="orthanc",
        )
    )
    P.append(drive_node(240, top + 172, 160, 84))
    P.append(
        elbow(
            [(208, top + 110), (224, top + 110), (224, top + 50), (238, top + 50)],
            SLATE,
            sw=1.6,
            id="arrow-dicom",
        )
    )
    P.append(
        elbow(
            [(208, top + 170), (224, top + 170), (224, top + 214), (238, top + 214)],
            AMBER,
            sw=1.6,
            id="arrow-raw",
        )
    )
    P.append(text(222, top + 38, "DICOM", 10.5, 600, MUTED, "end"))
    P.append(text(222, top + 236, "secondary", 10.5, 600, AMBER, "end"))
    # accessionflow (edge)
    ax, ay, aw, ah = 432, top, 548, 220
    box = [
        rect(ax, ay, aw, ah, rx=14, fill=TEAL_L, stroke=TEAL, sw=1.8),
        text(ax + 20, ay + 28, "accessionflow", 16, 700, TEAL_D, "start", mono=True),
        text(ax + 160, ay + 28, "command-line stages", 12.5, 500, MUTED, "start"),
    ]
    r1, _, _ = chip_row(ax + 20, ay + 52, ["collate", "attach", "label", "deidentify"])
    r2, e2, _ = chip_row(ax + 20, ay + 98, ["annotate", "package"])
    box += r1 + r2
    ya, yb = ay + 113, ay + 159  # centre lines of the A and B rows
    fx, sx = e2 + 14, e2 + 34
    box.append(arrow(e2 + 2, ya, sx - 2, ya, TEAL, sw=1.4, id="arrow-a"))
    box.append(elbow([(fx, ya), (fx, yb), (sx - 2, yb)], TEAL, sw=1.4, id="arrow-b"))
    box.append(f'<circle cx="{fx}" cy="{ya}" r="3.5" fill="{TEAL}"/>')
    ga, wa = chip2(sx, ya - 15, "store xnat")
    box += [ga, badge(sx + wa - 2, ya - 15, "A", INDIGO, r=9)]
    gb, wb = chip2(sx, yb - 15, "push", "push")
    box += [gb, badge(sx + wb - 2, yb - 15, "B", AMBER, r=9)]
    box.append(
        text(sx + wb + 18, yb + 4, "to object storage", 11.5, 500, MUTED, "start")
    )
    box.append(
        text(
            ax + 20,
            ay + 204,
            "Secondary data (too little metadata to collate alone) is attached to its accession",
            11,
            400,
            MUTED,
            "start",
            italic=True,
        )
    )
    P.append(group("accessionflow-edge", box))
    P.append(
        arrow(400 + 3, top + 50, ax - 3, top + 50, SLATE, sw=1.8, id="arrow-orthanc")
    )
    P.append(
        elbow(
            [
                (400 + 2, top + 214),
                (416, top + 214),
                (416, top + 130),
                (ax - 2, top + 130),
            ],
            AMBER,
            sw=1.8,
            id="arrow-drive",
        )
    )
    # server side
    P.append(
        node(
            1180,
            top,
            180,
            100,
            "XNAT",
            "imaging repository",
            color=INDIGO,
            fill=WHITE,
            id="xnat",
        )
    )
    P.append(cylinder(1100, top + 120, 92, 80, fill=WHITE, id="s3-bucket"))
    P.append(text(1100, top + 184, "S3 bucket", 12.5, 700, INDIGO))
    P.append(
        node(
            1200,
            top + 129,
            160,
            60,
            "accessionflow",
            "store xnat",
            color=TEAL,
            fill=TEAL_L,
            id="accessionflow-server",
        )
    )
    P.append(badge(1200, top + 129, "B", AMBER, r=9))
    P.append(
        arrow(ax + aw + 3, top + 50, 1180 - 3, top + 50, INDIGO, sw=1.8, id="route-a")
    )
    P.append(badge(1036, top + 36, "A", INDIGO, r=9))
    P.append(text(1052, top + 40, "direct upload", 11.5, 700, INDIGO, "start"))
    P.append(arrow(ax + aw + 3, yb, 1054 - 3, yb, AMBER, sw=1.8, id="route-b-push"))
    P.append(badge(1000, yb - 14, "B", AMBER, r=9))
    P.append(text(1015, yb - 10, "push", 11.5, 700, AMBER, "start"))
    P.append(arrow(1146 + 3, yb, 1200 - 3, yb, INDIGO, sw=1.6, id="route-b-read"))
    P.append(
        arrow(
            1280, top + 129 - 3, 1280, top + 100 + 3, INDIGO, sw=1.8, id="route-b-store"
        )
    )
    out.append(group("panel-current", P))

    # ======================= PLANNED
    y1 = y0 + ph + 30
    ph2 = 340
    P = [
        rect(40, y1, W - 80, ph2, rx=16, fill=PANEL, stroke="none", sw=0),
        tag(64, y1 + 18, "Planned", AMBER, AMBER_L, size=12, anchor="start"),
        text(
            160,
            y1 + 32,
            "Each stage runs as a Prefect flow configured by YAML. A site chooses where each stage runs;",
            13,
            400,
            MUTED,
            "start",
        ),
        text(
            160,
            y1 + 50,
            "push moves data between locations. collate and attach always run on site, so push comes after them; any number of pushes.",
            13,
            400,
            MUTED,
            "start",
        ),
    ]
    # legend
    lx = 1010
    P.append(
        group(
            "legend",
            [
                rect(lx, y1 + 20, 22, 14, rx=3, fill=WHITE, stroke=LINE, sw=1),
                text(lx + 30, y1 + 32, "Edge", 12, 500, MUTED, "start"),
                rect(
                    lx + 78, y1 + 20, 22, 14, rx=3, fill=INDIGO_L, stroke="none", sw=0
                ),
                text(lx + 108, y1 + 32, "Server side", 12, 500, MUTED, "start"),
                rect(lx + 196, y1 + 20, 30, 14, rx=7, fill=AMBER, stroke="none", sw=0),
                text(lx + 234, y1 + 32, "push", 12, 600, MUTED, "start", mono=True),
            ],
        )
    )
    rt = y1 + 84
    rows = [
        (
            "All at the edge",
            "upload directly from site",
            [
                "collate",
                "attach",
                "label",
                "deidentify",
                "annotate",
                "package",
                "store",
            ],
        ),
        (
            "De-identify on site",
            "only de-identified data leaves",
            [
                "collate",
                "attach",
                "label",
                "deidentify",
                "push",
                "annotate",
                "package",
                "store",
            ],
        ),
        (
            "Minimal edge footprint",
            "process centrally",
            [
                "collate",
                "attach",
                "push",
                "label",
                "deidentify",
                "annotate",
                "package",
                "store",
            ],
        ),
    ]
    rh, rg = 66, 16
    # inputs column (edge)
    ih = len(rows) * rh + (len(rows) - 1) * rg
    P.append(
        group(
            "inputs",
            [
                rect(60, rt, 170, ih, rx=14, fill=WHITE, stroke=LINE, sw=1),
                text(78, rt + 24, "EDGE INPUTS", 11, 700, MUTED, "start"),
            ],
        )
    )
    P.append(
        node(
            76,
            rt + 38,
            138,
            74,
            "Orthanc",
            "primary data (DICOM)",
            id="orthanc-planned",
        )
    )
    P.append(
        group(
            "network-drive-planned",
            [
                rect(76, rt + 126, 138, 74, rx=12, fill=WHITE, stroke=AMBER, sw=1.6),
                text(145, rt + 156, "Network drive", 14, 700, INK),
                text(145, rt + 175, "secondary data", 11.5, 400, MUTED),
            ],
        )
    )
    # repositories column (server)
    rx0 = 1226
    P.append(
        group(
            "repositories",
            [
                rect(rx0, rt, 154, ih, rx=14, fill=INDIGO_L, stroke="none", sw=0),
                text(rx0 + 18, rt + 24, "REPOSITORIES", 11, 700, MUTED, "start"),
                rect(
                    rx0 + 16, rt + 38, 122, 46, rx=10, fill=WHITE, stroke=INDIGO, sw=1.4
                ),
                text(rx0 + 77, rt + 66, "XNAT", 14, 700, INDIGO),
                rect(
                    rx0 + 16,
                    rt + 96,
                    122,
                    46,
                    rx=10,
                    fill=WHITE,
                    stroke=INDIGO,
                    sw=1.2,
                    dash="5 4",
                ),
                text(rx0 + 77, rt + 116, "Others", 13, 600, INK),
                text(rx0 + 77, rt + 132, "via plugins", 11, 400, MUTED),
            ],
        )
    )
    for i, (title, sub, names) in enumerate(rows):
        ry = rt + i * (rh + rg)
        R = []
        bx0, bx1 = 250, 1206
        cx0 = 440
        cy = ry + rh / 2
        chips, end_x, pos = chip_row(cx0, cy - 15, names)
        if "push" in pos:
            px = (pos["push"][0] + pos["push"][1]) / 2
            R.append(rect(bx0, ry, px - bx0, rh, rx=12, fill=WHITE, stroke=LINE, sw=1))
            R.append(
                rect(px, ry, bx1 - px, rh, rx=12, fill=INDIGO_L, stroke="none", sw=0)
            )
            R.append(rect(px, ry, 12, rh, rx=0, fill=INDIGO_L, stroke="none", sw=0))
            R.append(line(px, ry - 6, px, ry + rh + 6, AMBER, 1.6, dash="4 4"))
        else:
            R.append(rect(bx0, ry, bx1 - bx0, rh, rx=12, fill=WHITE, stroke=LINE, sw=1))
        R.append(text(268, cy - 3, title, 14, 700, INK, "start"))
        R.append(text(268, cy + 15, sub, 11.5, 400, MUTED, "start"))
        R += chips
        R.append(arrow(230 + 3, cy, bx0 - 2, cy, SLATE, sw=1.4, id="arrow-in"))
        R.append(arrow(end_x + 3, cy, rx0 - 3, cy, INDIGO, sw=1.4, id="arrow-out"))
        P.append(group(f"site-{i + 1}", R))
    out.append(group("panel-planned", P))
    out.append(
        group(
            "footnote",
            [
                text(
                    40,
                    H - 26,
                    "Example site configurations. Stage order is also configurable, and outputs can branch to several repositories.",
                    12.5,
                    400,
                    MUTED,
                    "start",
                )
            ],
        )
    )
    return svg(W, H, "accessionflow reference deployment", out)


# ------------------------------------------------- 5. concepts: data model
LEVEL = {  # colour per level of the data model
    "accession": (TEAL, TEAL_L, TEAL_D),
    "acquisition": (INDIGO, INDIGO_L, INDIGO),
    "resource": (AMBER, AMBER_L, AMBER),
}


def level_pill(x, y, level, size=11):
    stroke, fill, ink = LEVEL[level]
    w = len(level) * size * 0.66 + 16
    return group(
        f"pill-{level}",
        [
            rect(
                x, y, w, size + 9, rx=(size + 9) / 2, fill=stroke, stroke="none", sw=0
            ),
            text(x + w / 2, y + size + 2.5, level, size, 700, ON, mono=True),
        ],
    )


def resource_card(x, y, w, name, files, id="resource"):
    stroke, fill, ink = LEVEL["resource"]
    p = [
        rect(x, y, w, 44, rx=8, fill=WHITE, stroke=stroke, sw=1.4),
        text(x + 14, y + 27, name, 12.5, 700, ink, "start", mono=True),
    ]
    for k in range(files):
        p.append(
            file_icon(
                x + w - 26 - k * 20,
                y + 9 + (files - 1 - k) * 0,
                w=16,
                h=20,
                fill=WHITE,
                stroke=stroke,
                sw=1.1,
                id="file",
            )
        )
    return group(id, p)


def concepts_model():
    W, H = 1240, 528
    out = [
        title_block(
            40,
            "Accessions, acquisitions and resources",
            "The data model every stage works with, and what each data store calls each level",
        )
    ]
    # ---- nested example
    ax, ay, aw, ah = 40, 116, 600, 372
    stroke, fill, ink = LEVEL["accession"]
    acc = [
        rect(ax, ay, aw, ah, rx=16, fill=fill, stroke=stroke, sw=1.8),
        level_pill(ax + 20, ay + 18, "accession"),
        text(
            ax + 128, ay + 32, "PRJ001.SUBJ042.MR01", 13, 700, ink, "start", mono=True
        ),
        text(
            ax + 20,
            ay + 60,
            "e.g. one imaging session of a patient",
            12.5,
            400,
            MUTED,
            "start",
        ),
    ]
    acqs = [
        ("1.T1w_MPRAGE", [("DICOM", 3), ("NIfTI", 1), ("SNAPSHOTS", 1)]),
        ("5.fMRI_rest", [("DICOM", 3), ("RAW", 1)]),
    ]
    cw = (aw - 60) / 2
    for i, (name, res) in enumerate(acqs):
        cx = ax + 20 + i * (cw + 20)
        cy = ay + 82
        s2, f2, i2 = LEVEL["acquisition"]
        p = [
            rect(cx, cy, cw, 268, rx=12, fill=WHITE, stroke=s2, sw=1.6),
            level_pill(cx + 14, cy + 14, "acquisition"),
            text(cx + 14, cy + 58, name, 13, 700, i2, "start", mono=True),
            text(
                cx + 14,
                cy + 76,
                "e.g. one DICOM series" if i == 0 else "with a secondary resource",
                11.5,
                400,
                MUTED,
                "start",
            ),
        ]
        for k, (rn, nf) in enumerate(res):
            p.append(
                resource_card(
                    cx + 14,
                    cy + 92 + k * 54,
                    cw - 28,
                    rn,
                    nf,
                    id=f"resource-{rn.lower()}",
                )
            )
        acc.append(group(f"acquisition-{i + 1}", p))
    out.append(group("example-accession", acc))

    # ---- mapping table
    tx, tw = 690, 510
    cols = [("AccessionFlow", 150), ("XNAT", 190), ("Folder store", 170)]
    ty = 116
    tbl = [rect(tx, ty, tw, 44, rx=10, fill=PANEL, stroke="none", sw=0)]
    cx = tx
    for name, w in cols:
        tbl.append(text(cx + 16, ty + 28, name, 13, 700, INK, "start"))
        cx += w
    rows = [
        (
            "accession",
            ["session", "(an XNAT experiment,", "in a project & subject)"],
            ["innermost label", "folder"],
        ),
        ("acquisition", ["scan"], ["<id>.<description>", "folder"]),
        ("resource", ["resource"], ["resource folder"]),
    ]
    ry = ty + 56
    for level, xn, fo in rows:
        s3, f3, i3 = LEVEL[level]
        rh = 84
        r = [
            rect(tx, ry, tw, rh, rx=10, fill=WHITE, stroke=LINE, sw=1),
            rect(tx, ry, 6, rh, rx=3, fill=s3, stroke="none", sw=0),
            level_pill(tx + 16, ry + 16, level),
        ]
        for k, t_ in enumerate(xn):
            r.append(
                text(
                    tx + 150 + 16,
                    ry + 30 + k * 17,
                    t_,
                    12.5 if k == 0 else 11.5,
                    700 if k == 0 else 400,
                    INK if k == 0 else MUTED,
                    "start",
                )
            )
        for k, t_ in enumerate(fo):
            r.append(
                text(
                    tx + 340 + 16,
                    ry + 30 + k * 17,
                    t_,
                    12.5,
                    600,
                    INK,
                    "start",
                    mono=t_.startswith("<"),
                )
            )
        tbl.append(group(f"row-{level}", r))
        ry += rh + 10
    out.append(group("store-names", tbl))
    out.append(
        group(
            "note",
            [
                text(
                    tx,
                    ry + 18,
                    "An accession is not a RIS accession number: DICOM's",
                    12,
                    400,
                    MUTED,
                    "start",
                ),
                text(
                    tx,
                    ry + 35,
                    "AccessionNumber is just one field that can label it.",
                    12,
                    400,
                    MUTED,
                    "start",
                ),
            ],
        )
    )
    return svg(W, H, "accessionflow data model", out)


# ------------------------------------------------- 6. concepts: staging directories
def tree(x, y, rows, w, dy=19):
    """rows: (indent, label, style) where style in {'dir','file','acc','acq','res','warn','dim'}"""
    styles = {
        "dir": (INK, 600),
        "file": (MUTED, 400),
        "acc": (TEAL_D, 700),
        "acq": (INDIGO, 700),
        "res": (AMBER, 700),
        "warn": (AMBER, 700),
        "dim": ("#98A2B3", 500),
    }
    p = []
    for k, (ind, label, st) in enumerate(rows):
        col, wt = styles[st]
        yy = y + k * dy
        if ind:
            p.append(line(x + ind * 14 - 8, yy - 13, x + ind * 14 - 8, yy - 4, LINE, 1))
            p.append(line(x + ind * 14 - 8, yy - 4, x + ind * 14 - 2, yy - 4, LINE, 1))
        p.append(text(x + ind * 14, yy, label, 11, wt, col, "start", mono=True))
    return p


def dir_card(x, y, w, h, title, rows, id):
    p = [
        rect(x, y, w, h, rx=12, fill=WHITE, stroke=SLATE, sw=1.4),
        rect(x, y, w, 34, rx=12, fill=SLATE_L, stroke="none", sw=0),
        rect(x, y + 22, w, 12, rx=0, fill=SLATE_L, stroke="none", sw=0),
        line(x, y + 34, x + w, y + 34, SLATE, 1.4),
        rect(x, y, w, h, rx=12, fill="none", stroke=SLATE, sw=1.4),
        text(x + 14, y + 23, title, 13, 700, INK, "start", mono=True),
    ]
    p += tree(x + 14, y + 58, rows, w)
    return group(id, p)


def stage_link(x1, x2, y, name, optional=False):
    w = len(name) * 8.2 + 24
    cx = (x1 + x2) / 2
    return group(
        f"stage-{name}",
        [
            line(x1 + 2, y, cx - w / 2 - 2, y, TEAL, 1.6),
            rect(
                cx - w / 2,
                y - 15,
                w,
                30,
                rx=15,
                fill=TEAL_L if not optional else WHITE,
                stroke=TEAL,
                sw=1.5,
                dash="5 4" if optional else None,
            ),
            text(cx, y + 4.5, name, 12.5, 700, TEAL_D, mono=True),
            arrow(cx + w / 2 + 2, y, x2 - 2, y, TEAL, sw=1.6, id="arrow"),
        ],
    )


def concepts_staging():
    W, H = 1560, 510
    out = [
        title_block(
            40,
            "Accessions moving through staging directories",
            "Each stage reads the previous stage's output directory and writes its own",
        )
    ]
    top, ch = 130, 250
    cy = top + 120
    # source
    out.append(
        group(
            "source",
            [
                rect(40, top, 150, ch, rx=12, fill=SLATE_L, stroke=SLATE, sw=1.4),
                text(115, top + 26, "Source", 14, 700, INK),
                text(115, top + 44, "folder or Orthanc", 11.5, 400, MUTED),
            ]
            + [
                file_icon(
                    70 + (k % 3) * 30,
                    top + 80 + (k // 3) * 42,
                    fill=WHITE,
                    stroke=SLATE,
                )
                for k in range(9)
            ],
        )
    )
    cw, gap = 248, 124
    xs = [190 + gap + i * (cw + gap) for i in range(3)]
    cards = [
        (
            "collated/",
            [
                (0, "_.1.2.840.113619…/", "acc"),
                (1, "__METADATA__.json", "file"),
                (1, "1/", "acq"),
                (2, "__METADATA__.json", "file"),
                (2, "DICOM/", "res"),
                (3, "__MANIFEST__.json", "file"),
                (3, "*.dcm", "file"),
                (0, "__build__/", "dim"),
                (1, "(accessions being written)", "dim"),
            ],
        ),
        (
            "labelled/",
            [
                (0, "PRJ001.SUBJ042.MR01/", "acc"),
                (1, "1.T1w_MPRAGE/", "acq"),
                (2, "DICOM/", "res"),
                (3, "*.dcm", "file"),
                (0, "__invalid__/", "warn"),
                (1, "INVALID_MISSING_PROJECT_ab12…/", "warn"),
            ],
        ),
        (
            "deidentified/",
            [
                (0, "PRJ001.SUBJ042.MR01/", "acc"),
                (1, "1.T1w_MPRAGE/", "acq"),
                (2, "DICOM/", "res"),
                (3, "*.dcm  (de-identified)", "file"),
            ],
        ),
    ]
    for i, (title, rows) in enumerate(cards):
        out.append(
            dir_card(xs[i], top, cw, ch, title, rows, id=f"dir-{title.strip('/')}")
        )
    links = [
        (190, xs[0], "collate", False),
        (xs[0] + cw, xs[1], "label", False),
        (xs[1] + cw, xs[2], "deidentify", True),
        (xs[2] + cw, xs[2] + cw + gap, "store", False),
    ]
    for x1, x2, n, opt in links:
        out.append(stage_link(x1, x2, cy, n, opt))
    rx = xs[2] + cw + gap
    out.append(cylinder(rx + 60, top + 60, 120, 120))
    out.append(text(rx + 60, top + 140, "data store", 12.5, 700, INDIGO))
    # callouts under cards
    notes = [
        (
            xs[0],
            "Unlabelled accessions are named _.<UID>;",
            "acquisitions have no description yet",
        ),
        (
            xs[1],
            "Labelled: named by their labels. Ones that",
            "can't be labelled go to __invalid__/ for review",
        ),
        (
            xs[2],
            "Each stage carries the metadata, manifests",
            "and fields through to the next",
        ),
    ]
    for x, a, b in notes:
        out.append(
            group(
                "note",
                [
                    text(x, top + ch + 26, a, 11.5, 400, MUTED, "start"),
                    text(x, top + ch + 42, b, 11.5, 400, MUTED, "start"),
                ],
            )
        )
    by = top + ch + 76
    out.append(
        group(
            "footer",
            [
                rect(40, by, W - 80, 44, rx=10, fill=PANEL, stroke="none", sw=0),
                text(
                    60,
                    by + 27,
                    "Accessions are built in __build__/ and moved into place once complete, so a later stage "
                    "never sees a partial one.  --unlink-source removes a stage's input once its output is saved.",
                    12.5,
                    400,
                    INK,
                    "start",
                ),
            ],
        )
    )
    return svg(W, H, "accessionflow staging directories", out)


# ---------------------------------------------------------------- dark mode
# The dark variants are made by remapping the light palette, so every diagram only has
# to be drawn once. Keys must match the colour constants above.
DARK_PALETTE = {
    WHITE: "#181C23",  # cards and background
    PANEL: "#20252E",
    "#E2E7EE": "#2A303A",  # background border
    INK: "#E6EAF0",
    MUTED: "#9AA4B2",
    LINE: "#3A4250",
    "#98A2B3": "#6B7484",  # struck-through fields
    "#9AA4B2": "#5A6478",  # snapshot image
    ON: "#0E1116",
    IMG: "#0B0E13",
    TEAL: "#2CB5BF",
    TEAL_L: "#123438",
    TEAL_D: "#6AD3DA",
    SLATE: "#94A3B8",
    SLATE_L: "#262C36",
    INDIGO: "#8F92F7",
    INDIGO_L: "#23264A",
    AMBER: "#F0A04B",
    AMBER_L: "#3A2A14",
}


def to_dark(svg_text):
    """Return a dark-mode copy of a diagram by swapping palette colours in one pass."""
    lookup = {k.upper(): v for k, v in DARK_PALETTE.items()}
    pattern = re.compile("|".join(re.escape(k) for k in lookup), re.IGNORECASE)
    return pattern.sub(lambda m: lookup[m.group(0).upper()], svg_text)


if __name__ == "__main__":
    # docs/diagram-dev/generate_diagrams.py -> docs/source/_static/images/diagrams/
    outdir = (
        Path(__file__).resolve().parent.parent
        / "source"
        / "_static"
        / "images"
        / "diagrams"
    )
    outdir.mkdir(parents=True, exist_ok=True)
    for name, fn in [
        ("accessionflow-overview", overview),
        ("accessionflow-stages", stage_by_stage),
        ("accessionflow-architecture", architecture),
        ("accessionflow-deployment", deployment),
        ("accessionflow-model", concepts_model),
        ("accessionflow-staging", concepts_staging),
    ]:
        light = fn()
        (outdir / f"{name}.svg").write_text(light)
        (outdir / f"{name}-dark.svg").write_text(to_dark(light))
        print("wrote", name)
