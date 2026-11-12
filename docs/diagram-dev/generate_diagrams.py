"""Generate accessionflow documentation diagrams as hand-editable SVG.

Design rules for Illustrator-friendliness:
  * every visual unit is a named <g id="..."> (becomes a layer/group)
  * all styling is inline attributes (no CSS, no classes)
  * text stays as live <text>, baselines set explicitly (no dominant-baseline)
  * arrowheads are plain polygons (no <marker>)
"""

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
    ("collate", ["Group files into", "sessions & series"], False),
    ("attach", ["Link non-DICOM", "files to sessions"], False),
    ("label", ["Assign project,", "subject, session IDs"], False),
    ("deidentify", ["Remove identifying", "header metadata"], True),
    ("package", ["Bundle data for the", "target repository"], True),
    ("store", ["Upload to the", "repository"], False),
]


# ------------------------------------------------- 1. pipeline overview (README)
def overview():
    W, H = 1440, 420
    out = [
        title_block(
            40,
            "accessionflow",
            "From instrument to repository through configurable, reorderable stages",
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
                text(118, top + 144, "DICOM & raw data", 12.5, 400, MUTED),
            ],
        )
    )

    x0, sw_, gap = 244, 140, 24
    xs = [x0 + i * (sw_ + gap) for i in range(len(STAGES))]
    out.append(arrow(196 + 4, cy, xs[0] - 4, cy, SLATE, id="arrow-source"))
    stage_groups = []
    for i, (name, desc, opt) in enumerate(STAGES):
        x = xs[i]
        stroke = TEAL
        parts = [
            rect(
                x,
                top,
                sw_,
                h,
                rx=14,
                fill=WHITE if opt else TEAL_L,
                stroke=stroke,
                sw=1.8,
                dash="6 5" if opt else None,
            ),
            f'<circle cx="{x + sw_ / 2}" cy="{top + 32}" r="14" fill="{TEAL}"/>',
            text(x + sw_ / 2, top + 37, str(i + 1), 13, 700, WHITE),
            text(x + sw_ / 2, top + 76, name, 18, 700, TEAL_D, mono=True),
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
    rx_, rw = 1236, 164
    end = xs[-1] + sw_
    out.append(arrow(end + 4, cy, rx_ - 4, cy, INDIGO, id="arrow-repositories"))
    repos = [
        rect(rx_, top, rw, h, rx=14, fill=INDIGO_L, stroke=INDIGO, sw=1.5),
        text(rx_ + rw / 2, top + 30, "Repositories", 16, 700, INK),
    ]
    for j, (lbl, dash) in enumerate(
        [("XNAT", None), ("Object storage", None), ("Others via plugins", "5 4")]
    ):
        yy = top + 46 + j * 38
        repos += [
            rect(
                rx_ + 14,
                yy,
                rw - 28,
                30,
                rx=8,
                fill=WHITE,
                stroke=INDIGO,
                sw=1.2,
                dash=dash,
            ),
            text(
                rx_ + rw / 2,
                yy + 20,
                lbl,
                13,
                600 if not dash else 400,
                INDIGO if not dash else MUTED,
            ),
        ]
    out.append(group("repositories", repos))

    # bracket under stages
    by = top + h + 26
    out.append(
        group(
            "stage-note",
            [
                line(xs[0], by, end, by, LINE, 1.5),
                line(xs[0], by - 8, xs[0], by, LINE, 1.5),
                line(end, by - 8, end, by, LINE, 1.5),
                line((xs[0] + end) / 2, by, (xs[0] + end) / 2, by + 8, LINE, 1.5),
                text(
                    (xs[0] + end) / 2,
                    by + 30,
                    "Each stage is a standalone command — stages are configured per deployment and can be reordered",
                    13.5,
                    400,
                    MUTED,
                ),
            ],
        )
    )
    return svg(W, H, "accessionflow pipeline overview", out)


# ------------------------------------------------- 2. stage-by-stage
def session_box(cx, y, w=144, h=150, label="session"):
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
        text(
            cx - w / 2 + 17 + len(label) * 3.6, y + 4, label, 11, 600, WHITE, mono=True
        ),
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
    W, H = 1440, 520
    out = [
        title_block(
            40,
            "What each stage does",
            "How a scanning session is transformed on its way to the repository",
        )
    ]
    cols = [("incoming", None, False)] + [(n, d, o) for n, d, o in STAGES]
    cw, gap, x0 = 176, 24, 40
    hy, hh = 116, 42
    py, ph = 178, 300
    captions = {
        "incoming": ["Unsorted DICOM and", "raw files arrive"],
        "collate": ["Sorted into sessions", "and series"],
        "attach": ["Associated non-DICOM", "files linked in"],
        "label": ["Project, subject and", "session IDs assigned"],
        "deidentify": ["Identifying header", "fields removed"],
        "package": ["Series bundled for", "the target repository"],
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
                ax_, ay_ = cx + 36, iy + 58
                ill.append(file_icon(ax_, ay_, fill=AMBER_L, stroke=AMBER, sw=1.6))
                ill.append(text(ax_ + 11, ay_ + 46, "raw", 11, 600, AMBER, mono=True))
                ill.append(
                    group(
                        "plus",
                        [
                            f'<circle cx="{ax_ + 24}" cy="{ay_ - 2}" r="9" fill="{AMBER}"/>',
                            line(ax_ + 19.5, ay_ - 2, ax_ + 28.5, ay_ - 2, WHITE, 2),
                            line(ax_ + 24, ay_ - 6.5, ax_ + 24, ay_ + 2.5, WHITE, 2),
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
            zx, zy = cx - 30, iy + 14
            zp = [
                f'<path d="M{zx},{zy} h44 l16,16 v96 h-60 z" fill="{WHITE}" stroke="{TEAL}" '
                f'stroke-width="1.8" stroke-linejoin="round"/>',
                f'<path d="M{zx + 44},{zy} v16 h16" fill="none" stroke="{TEAL}" stroke-width="1.8" '
                f'stroke-linejoin="round"/>',
            ]
            for k in range(6):
                zp.append(
                    rect(
                        zx + 22 + (k % 2) * 8,
                        zy + 6 + k * 9,
                        8,
                        7,
                        rx=1,
                        fill=TEAL,
                        stroke="none",
                        sw=0,
                    )
                )
            zp.append(
                rect(zx + 20, zy + 64, 20, 20, rx=3, fill=TEAL_L, stroke=TEAL, sw=1.4)
            )
            zp.append(text(cx, zy + 136, ".zip", 13, 700, TEAL_D, mono=True))
            ill.append(group("archive", zp))
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
    cw_, g_ = 132, 14
    names = [s[0] for s in STAGES]
    sx0 = X + 210
    for i, n in enumerate(names):
        opt = STAGES[i][2]
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
                    text(xx + cw_ / 2, y2 + 54, n, 15, 700, TEAL_D, mono=True),
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
                420,
                66,
                "Shared data model",
                "sessions · series · resources",
                color=TEAL,
                mono_sub=False,
            ),
        )
    )
    p.append(
        group(
            "core-staging",
            chip(
                X + 650,
                y2 + 96,
                420,
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
            "Repository plugins — provide the store subcommands",
            13,
            600,
            INK,
            "start",
        )
    )
    p.append(
        group(
            "plugin-xnat",
            chip(X + 210, y3 + 50, 200, 56, "XNAT", "store xnat", color=INDIGO),
        )
    )
    p.append(
        group(
            "plugin-other-repos",
            chip(
                X + 426,
                y3 + 50,
                200,
                56,
                "Other repositories",
                "store <repo>",
                planned=True,
            ),
        )
    )
    p.append(text(X + 670, y3 + 34, "Data types", 13, 600, INK, "start"))
    p.append(
        group("type-dicom", chip(X + 670, y3 + 50, 120, 56, "DICOM", color=INDIGO))
    )
    p.append(
        group(
            "type-biosignals",
            chip(X + 802, y3 + 50, 120, 56, "Biosignals", planned=True),
        )
    )
    p.append(
        group(
            "type-omics",
            chip(X + 934, y3 + 50, 136, 56, "Bioinformatics", planned=True),
        )
    )
    p.append(
        text(
            X + 210,
            y3 + 150,
            "Plugins are installed per deployment, so a site only carries the repositories and data types it uses.",
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


def deployment():
    W, H = 1440, 960
    out = [
        title_block(
            40,
            "Reference deployment",
            "How accessionflow sits between the scanner and the repository — today and planned",
        )
    ]

    def panel(y, label, badge_color, badge_fill, planned):
        P = []
        ph = 380
        P.append(rect(40, y, W - 80, ph, rx=16, fill=PANEL, stroke="none", sw=0))
        P.append(
            tag(64, y + 18, label, badge_color, badge_fill, size=12, anchor="start")
        )
        top = y + 70
        # scanner
        P.append(
            group(
                "scanner",
                [
                    rect(
                        60, top + 70, 150, 150, rx=14, fill=WHITE, stroke=SLATE, sw=1.6
                    ),
                    scanner_icon(135, top + 122, 0.85),
                    text(135, top + 188, "MRI scanner", 15, 700, INK),
                    text(135, top + 206, "e.g. Siemens Cima X", 11.5, 400, MUTED),
                ],
            )
        )
        # cluster
        cx0, cw = 262, 860
        P.append(
            group(
                "cluster",
                [
                    rect(
                        cx0,
                        top,
                        cw,
                        290,
                        rx=16,
                        fill=WHITE,
                        stroke=SLATE,
                        sw=1.4,
                        dash="2 5",
                    ),
                    text(
                        cx0 + 20,
                        top + 26,
                        "Kubernetes (MicroK8s)",
                        12.5,
                        700,
                        SLATE,
                        "start",
                    ),
                ],
            )
        )
        P.append(
            node(
                cx0 + 24,
                top + 82,
                168,
                126,
                "Orthanc",
                "DICOM listener",
                sub2="C-STORE receiver",
                id="orthanc",
            )
        )
        P.append(
            arrow(210 + 4, top + 145, cx0 + 24 - 4, top + 145, SLATE, id="arrow-dicom")
        )
        P.append(text(236, top + 136, "DICOM", 11, 600, MUTED))

        # accessionflow box
        ax, aw, ay, ah = cx0 + 228, 540, top + 40, 158
        if planned:
            box = [
                rect(ax, ay, aw, ah, rx=14, fill=TEAL_L, stroke=TEAL, sw=1.8),
                text(
                    ax + 20,
                    ay + 28,
                    "accessionflow",
                    16,
                    700,
                    TEAL_D,
                    "start",
                    mono=True,
                ),
                text(
                    ax + 160,
                    ay + 28,
                    "Prefect flows, configured by YAML",
                    12.5,
                    500,
                    AMBER,
                    "start",
                ),
            ]
            chain = [
                "collate",
                "attach",
                "label",
                "deidentify",
                "package",
                "transfer†",
                "store",
            ]
            box.append(
                mini_chain(
                    ax + 20, ay + 50, chain, highlight=("transfer†",), w=116, per_row=4
                )
            )
        else:
            box = [
                rect(ax, ay, aw, ah, rx=14, fill=TEAL_L, stroke=TEAL, sw=1.8),
                text(
                    ax + 20,
                    ay + 28,
                    "accessionflow",
                    16,
                    700,
                    TEAL_D,
                    "start",
                    mono=True,
                ),
                text(
                    ax + 160, ay + 28, "command-line stages", 12.5, 500, MUTED, "start"
                ),
            ]
            chain = ["collate", "attach", "label", "deidentify", "package", "store"]
            box.append(mini_chain(ax + 20, ay + 50, chain, w=116, per_row=4))
        P.append(group("accessionflow", box))
        P.append(
            arrow(
                cx0 + 192 + 4, top + 145, ax - 4, top + 145, SLATE, id="arrow-orthanc"
            )
        )

        # staging storage
        sy = ay + ah + 26
        P.append(
            node(
                ax,
                sy,
                aw,
                52,
                "Staging storage",
                "local volume or S3",
                color=TEAL,
                id="staging",
            )
        )
        P.append(
            arrow(
                ax + aw / 2,
                ay + ah + 3,
                ax + aw / 2,
                sy - 3,
                TEAL,
                sw=1.8,
                both=True,
                id="arrow-staging",
            )
        )

        # outputs
        ox, ow = 1166, 230
        if planned:
            P.append(
                group(
                    "repositories",
                    [
                        rect(
                            ox,
                            top + 10,
                            ow,
                            160,
                            rx=14,
                            fill=INDIGO_L,
                            stroke=INDIGO,
                            sw=1.6,
                        ),
                        text(ox + ow / 2, top + 36, "Repositories", 15, 700, INK),
                        rect(
                            ox + 16,
                            top + 52,
                            ow - 32,
                            40,
                            rx=8,
                            fill=WHITE,
                            stroke=INDIGO,
                            sw=1.2,
                        ),
                        text(ox + ow / 2, top + 77, "XNAT", 14, 700, INDIGO),
                        rect(
                            ox + 16,
                            top + 104,
                            ow - 32,
                            46,
                            rx=8,
                            fill=AMBER_L,
                            stroke=AMBER,
                            sw=1.2,
                            dash="5 4",
                        ),
                        text(
                            ox + ow / 2, top + 124, "Other repositories", 13.5, 700, INK
                        ),
                        text(ox + ow / 2, top + 141, "via plugins", 11.5, 500, AMBER),
                    ],
                )
            )
            P.append(
                elbow([(ax + aw, ay + 60), (ox, ay + 60)], INDIGO, id="arrow-store")
            )
            P.append(
                text(
                    (ax + aw + cx0 + cw) / 2,
                    ay + 52,
                    "store",
                    11.5,
                    700,
                    INDIGO,
                    mono=True,
                )
            )
            P.append(
                node(
                    ox,
                    top + 196,
                    ow,
                    80,
                    "S3 / remote drive",
                    "via transfer† stage",
                    color=INDIGO,
                    fill=INDIGO_L,
                    id="object-storage",
                )
            )
            P.append(
                elbow(
                    [
                        (ax + aw, ay + 128),
                        (ax + aw + 22, ay + 128),
                        (ax + aw + 22, top + 236),
                        (ox, top + 236),
                    ],
                    AMBER,
                    dash="6 4",
                    id="arrow-transfer",
                )
            )
        else:
            P.append(
                node(
                    ox,
                    top + 10,
                    ow,
                    110,
                    "XNAT",
                    "imaging repository",
                    color=INDIGO,
                    fill=INDIGO_L,
                    id="xnat",
                )
            )
            P.append(
                elbow([(ax + aw, ay + 25), (ox, ay + 25)], INDIGO, id="arrow-store")
            )
            P.append(
                text(
                    (ax + aw + cx0 + cw) / 2,
                    ay + 17,
                    "store xnat",
                    11.5,
                    700,
                    INDIGO,
                    mono=True,
                )
            )
            # rclone script
            rx0 = ox
            P.append(
                node(
                    rx0,
                    top + 150,
                    ow,
                    56,
                    "rclone sync",
                    "separate script",
                    color=SLATE,
                    id="rclone",
                )
            )
            P.append(
                node(
                    rx0,
                    top + 232,
                    ow,
                    56,
                    "S3 / remote drive",
                    color=INDIGO,
                    fill=INDIGO_L,
                    id="object-storage",
                )
            )
            P.append(
                elbow(
                    [
                        (ax + aw, sy + 26),
                        (ax + aw + 22, sy + 26),
                        (ax + aw + 22, top + 178),
                        (rx0, top + 178),
                    ],
                    SLATE,
                    dash="6 4",
                    id="arrow-rclone",
                )
            )
            P.append(
                arrow(
                    rx0 + ow / 2,
                    top + 206 + 3,
                    rx0 + ow / 2,
                    top + 232 - 3,
                    SLATE,
                    sw=1.8,
                    id="arrow-sync",
                )
            )
        return group("panel-planned" if planned else "panel-current", P)

    out.append(panel(110, "Current", SLATE, SLATE_L, False))
    out.append(panel(520, "Planned", AMBER, AMBER_L, True))
    out.append(
        group(
            "footnote",
            [
                text(
                    40,
                    H - 24,
                    "† Stage name to be confirmed. Brings the separate rclone sync into accessionflow.",
                    12.5,
                    400,
                    MUTED,
                    "start",
                )
            ],
        )
    )
    return svg(W, H, "accessionflow reference deployment", out)


if __name__ == "__main__":
    outdir = Path("diagrams")
    outdir.mkdir(exist_ok=True)
    for name, fn in [
        ("accessionflow-overview", overview),
        ("accessionflow-stages", stage_by_stage),
        ("accessionflow-architecture", architecture),
        ("accessionflow-deployment", deployment),
    ]:
        (outdir / f"{name}.svg").write_text(fn())
        print("wrote", name)
