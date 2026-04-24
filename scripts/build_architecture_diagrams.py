"""Educational architecture diagrams for ICBB-AMRSS (A3 landscape, 300 DPI)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle


A3_W, A3_H = 16.5, 11.7
DPI = 300

PAPER       = "#fbf6ea"
PAPER_ALT   = "#efe6cf"
BORDER_S    = "#8a7d5c"
INK         = "#1a160c"
INK_MUTED   = "#5a5340"

PEOPLE      = "#1f4e79"; PEOPLE_S    = "#d3e1ee"
APP         = "#1d6b4f"; APP_S       = "#cfe6dc"
DATA        = "#7a3a14"; DATA_S      = "#f1d6c0"
EXT         = "#8a6a14"; EXT_S       = "#f1e0b3"
HIGHLIGHT   = "#a01a1a"; HIGHLIGHT_S = "#f1cdcd"

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "docs" / "architecture"
OUT.mkdir(parents=True, exist_ok=True)
TODAY = date.today().isoformat()


def new_figure():
    fig, ax = plt.subplots(figsize=(A3_W, A3_H), dpi=DPI)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)
    return fig, ax


def card(ax, x, y, w, h, *, fill=PAPER, edge=BORDER_S, lw=1.6, radius=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle=f"round,pad=0.0,rounding_size={radius}",
        linewidth=lw, edgecolor=edge, facecolor=fill))


def lbl(ax, x, y, t, *, size=12, weight="normal", color=INK, ha="center", va="center"):
    ax.text(x, y, t, fontsize=size, fontweight=weight, color=color,
            ha=ha, va=va, family="DejaVu Sans")


def arrow(ax, x1, y1, x2, y2, *, color=APP, lw=2.6, ms=26):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=ms, linewidth=lw, color=color,
        shrinkA=4, shrinkB=4))


def num_circle(ax, x, y, n, color, r=1.8):
    ax.add_patch(Circle((x, y), r, facecolor=color, edgecolor="white", lw=2.0, zorder=5))
    lbl(ax, x, y, str(n), size=15, weight="bold", color="white")


def title_block(ax, big, small):
    lbl(ax, 50, 95.0, big, size=30, weight="bold", color=INK)
    lbl(ax, 50, 90.8, small, size=15, color=INK_MUTED)
    ax.plot([28, 72], [88.5, 88.5], color=EXT, linewidth=2.4)


def footer(ax, p, total):
    ax.add_patch(Rectangle((0, 0), 100, 2.6, facecolor=PAPER_ALT, edgecolor="none"))
    lbl(ax, 3, 1.3, "ICBB-AMRSS  ·  System Architecture  ·  Educational Diagram",
        size=10, color=INK_MUTED, ha="left")
    lbl(ax, 97, 1.3, f"{TODAY}   ·   Page {p} of {total}",
        size=10, color=INK_MUTED, ha="right")


def build_engineering_schematic():
    fig, ax = new_figure()
    title_block(ax, "How the AMR Dashboard is Built",
                "The four parts that work together to make the system run")

    # Legend
    leg_y = 84.5
    leg_items = [("People who use it", PEOPLE), ("The application", APP),
                 ("Where data lives", DATA),    ("Outside helpers", EXT)]
    for (txt, c), cx in zip(leg_items, [10, 33, 56, 79]):
        ax.add_patch(Rectangle((cx, leg_y), 2.5, 1.8, facecolor=c, edgecolor="none"))
        lbl(ax, cx + 3.4, leg_y + 0.9, txt, size=12, color=INK_MUTED, ha="left")

    # 1. PEOPLE
    card(ax, 6, 68, 88, 12.5, fill=PEOPLE_S, edge=PEOPLE, lw=2.0)
    lbl(ax, 50, 78.6, "1.  People who use the system",
        size=17, weight="bold", color=PEOPLE)
    user_t = [("Lab staff",       "Upload AST results",  "Scientists, technicians"),
              ("Health officers", "Explore dashboards",  "Surveillance, epidemiology"),
              ("Administrators",  "Manage users & data", "ICBB / NPHRL")]
    for x, (who, what, sub) in zip([22, 50, 78], user_t):
        ax.add_patch(Circle((x, 75.1), 2.2, facecolor="white",
                             edgecolor=PEOPLE, lw=2.4))
        lbl(ax, x, 75.1, "P", size=14, weight="bold", color=PEOPLE)
        lbl(ax, x, 71.6, who, size=13, weight="bold", color=INK)
        lbl(ax, x, 70.0, what, size=11, color=INK)
        lbl(ax, x, 68.7, sub, size=10, color=INK_MUTED)

    # 2. APPLICATION
    card(ax, 6, 30, 88, 35, fill=APP_S, edge=APP, lw=2.4)
    lbl(ax, 50, 62.3, "2.  The application", size=17, weight="bold", color=APP)
    lbl(ax, 50, 60.0,
        "A Python program built with Streamlit.  Opens in any web browser.",
        size=12, color=INK_MUTED)

    sub_y, sub_h, sub_w, sub_gap, sub_start = 33.5, 23, 27, 2.5, 8
    sub_data = [
        ("Show", "Turns data into pictures",
         ["Dashboards & charts", "Maps & hot-spots",
          "Pathogen profiles",   "Antibiogram tables",
          "PPS / AMU / AMC views"]),
        ("Calculate", "Turns data into knowledge",
         ["Resistance rates (%)", "MDR / XDR flags",
          "Trends over time",    "Sentinel signals",
          "EUCAST interpretation"]),
        ("Manage", "Keeps the system running",
         ["Login & user accounts", "Excel file uploads",
          "Data quality checks",   "Multi-lab dataset switch",
          "Optional AI assistant"]),
    ]
    for i, (t, tag, bullets) in enumerate(sub_data):
        x = sub_start + i * (sub_w + sub_gap)
        card(ax, x, sub_y, sub_w, sub_h, fill="white", edge=APP, lw=1.6, radius=0.8)
        lbl(ax, x + sub_w/2, sub_y + sub_h - 2.6, t, size=16, weight="bold", color=APP)
        lbl(ax, x + sub_w/2, sub_y + sub_h - 5.2, tag, size=11, color=INK_MUTED)
        ax.plot([x + 2.5, x + sub_w - 2.5],
                [sub_y + sub_h - 7.0, sub_y + sub_h - 7.0],
                color=APP, lw=1.0, alpha=0.5)
        for bi, b in enumerate(bullets):
            lbl(ax, x + sub_w/2, sub_y + sub_h - 9.2 - bi*2.2,
                "•  " + b, size=11.5, color=INK)

    # 3. DATABASE
    card(ax, 6, 6, 42, 22, fill=DATA_S, edge=DATA, lw=2.2)
    lbl(ax, 27, 25.0, "3.  Where the data lives",
        size=17, weight="bold", color=DATA)
    lbl(ax, 27, 22.5, "PostgreSQL database", size=13, weight="bold", color=INK)
    ax.add_patch(FancyBboxPatch((10, 9.5), 8, 10,
        boxstyle="round,pad=0.0,rounding_size=1.6",
        facecolor="white", edgecolor=DATA, lw=1.8))
    for dy in [16.5, 14.5, 12.5, 10.5]:
        ax.plot([11, 17], [dy, dy], color=DATA, lw=1.0, alpha=0.7)
    for bi, b in enumerate(["Users  &  lab accounts",
                            "Datasets  (one per upload)",
                            "Samples  &  AST results",
                            "Alerts  &  audit history"]):
        lbl(ax, 21, 19.6 - bi*2.4, "•  " + b, size=11.5, color=INK, ha="left")
    lbl(ax, 27, 7.6,
        "A safe, organised filing cabinet for every record.",
        size=10.5, color=INK_MUTED, weight="bold")

    # 4. OUTSIDE HELPERS  (Gmail / SMTP intentionally removed)
    card(ax, 52, 6, 42, 22, fill=EXT_S, edge=EXT, lw=2.2)
    lbl(ax, 73, 25.0, "4.  Helpers from outside",
        size=17, weight="bold", color=EXT)
    lbl(ax, 73, 22.5,
        "Optional online services the system can talk to.",
        size=11, color=INK_MUTED)
    for i, (name, lines) in enumerate([
        ("KoboToolbox", ["Collects field forms", "submitted by labs"]),
        ("OpenAI",      ["Powers the optional", "AI question assistant"]),
    ]):
        bx = 55 + i * 19
        card(ax, bx, 9, 17, 12, fill="white", edge=EXT, lw=1.4, radius=0.7)
        lbl(ax, bx + 8.5, 18.5, name, size=14, weight="bold", color=EXT)
        for li, line in enumerate(lines):
            lbl(ax, bx + 8.5, 14.2 - li*1.9, line, size=11, color=INK_MUTED)

    # Connecting arrows
    arrow(ax, 50, 68, 50, 65, color=PEOPLE, lw=3.0, ms=28)
    lbl(ax, 51.6, 66.5, "open in browser",
        size=11.5, color=PEOPLE, ha="left", weight="bold")
    arrow(ax, 27, 30, 27, 28, color=DATA, lw=3.0, ms=28)
    lbl(ax, 28.8, 29.0, "save / read records",
        size=11, color=DATA, ha="left", weight="bold")
    arrow(ax, 73, 30, 73, 28, color=EXT, lw=3.0, ms=28)
    lbl(ax, 71.2, 29.0, "forms · AI",
        size=11, color=EXT, ha="right", weight="bold")

    footer(ax, 1, 2)
    _save(fig, "engineering_schematic")


def build_dataflow_diagram():
    fig, ax = new_figure()
    title_block(ax, "How Data Moves Through the System",
                "Follow one lab result from collection to a published insight  ·  6 steps")

    step_y, step_h, step_w, step_gap = 60, 22, 14, 1.6
    n_steps = 6
    total_w = n_steps * step_w + (n_steps - 1) * step_gap
    start_x = (100 - total_w) / 2

    steps = [
        ("Collect",
         ["A lab tests a", "bacterial sample",
          "against a panel", "of antibiotics."],
         "Lab staff", PEOPLE, PEOPLE_S),
        ("Upload",
         ["Results are uploaded", "as an Excel file",
          "to the dashboard", "by an authorised user."],
         "Upload page", APP, APP_S),
        ("Validate",
         ["The system checks", "the file: required",
          "columns, valid codes,", "no duplicates."],
         "validate.py", APP, APP_S),
        ("Store",
         ["Clean records are", "saved to the",
          "PostgreSQL database", "as one dataset."],
         "db.save_dataset()", DATA, DATA_S),
        ("Analyse",
         ["Resistance %, MDR,", "trends and hot-spots",
          "are calculated and", "interpreted."],
         "analytics  ·  plots", APP, APP_S),
        ("Display & Alert",
         ["Dashboards refresh.", "Sentinel signals are",
          "raised on the Alerts", "page for action."],
         "dashboards  ·  alerts", HIGHLIGHT, HIGHLIGHT_S),
    ]

    centres = []
    for i, (t, lines, mod, edge, fill) in enumerate(steps):
        x = start_x + i * (step_w + step_gap)
        cx = x + step_w / 2
        centres.append(cx)
        card(ax, x, step_y - step_h/2, step_w, step_h,
             fill=fill, edge=edge, lw=2.2, radius=0.9)
        num_circle(ax, cx, step_y + step_h/2, i + 1, edge, r=1.8)
        lbl(ax, cx, step_y + step_h/2 - 4.0, t,
            size=15, weight="bold", color=edge)
        for li, line in enumerate(lines):
            lbl(ax, cx, step_y + 2.2 - li*1.9, line, size=11, color=INK)
        card(ax, x + 0.8, step_y - step_h/2 + 1.2, step_w - 1.6, 3.2,
             fill="white", edge=edge, lw=1.2, radius=0.5)
        lbl(ax, cx, step_y - step_h/2 + 2.8, mod,
            size=10, weight="bold", color=edge)

    for i in range(n_steps - 1):
        x1 = centres[i] + step_w/2 - 0.2
        x2 = centres[i+1] - step_w/2 + 0.2
        arrow(ax, x1, step_y - 1.6, x2, step_y - 1.6,
              color=INK_MUTED, lw=2.4, ms=24)

    panel_y, panel_h = 8, 28

    card(ax, 5, panel_y, 44, panel_h, fill=PEOPLE_S, edge=PEOPLE, lw=2.0)
    lbl(ax, 27, panel_y + panel_h - 3.2, "What the user sees",
        size=15, weight="bold", color=PEOPLE)
    seen = ["•  A login page",
            "•  An Excel upload page with quality feedback",
            "•  Interactive dashboards, charts and maps",
            "•  A heat-map of resistance across Ghana",
            "•  An alerts page with sentinel signals",
            "•  A button to download a PDF report"]
    for i, s in enumerate(seen):
        lbl(ax, 8, panel_y + panel_h - 7.0 - i*2.8, s,
            size=12, color=INK, ha="left")

    card(ax, 51, panel_y, 44, panel_h, fill=APP_S, edge=APP, lw=2.0)
    lbl(ax, 73, panel_y + panel_h - 3.2, "What happens behind the scenes",
        size=15, weight="bold", color=APP)
    behind = ["•  Python checks your password (bcrypt hashing)",
              "•  Pandas reads and cleans the spreadsheet",
              "•  validate.py rejects bad rows with reasons",
              "•  SQL queries fetch and save data (psycopg2)",
              "•  analytics.py computes resistance rates & MDR",
              "•  Plotly turns the numbers into interactive charts"]
    for i, s in enumerate(behind):
        lbl(ax, 54, panel_y + panel_h - 7.0 - i*2.8, s,
            size=12, color=INK, ha="left")

    lbl(ax, 50, 5.0,
        "Read left → right.  Each numbered card is one stage of the journey.",
        size=12, color=INK_MUTED, weight="bold")
    lbl(ax, 50, 3.5,
        "Colour code:    blue = people    ·    green = the application    "
        "·    brown = database    ·    red = action & alerts",
        size=11, color=INK_MUTED)

    footer(ax, 2, 2)
    _save(fig, "dataflow_module_design")


def _save(fig, name):
    png = OUT / f"{name}.png"
    svg = OUT / f"{name}.svg"
    fig.savefig(png, dpi=DPI, bbox_inches="tight", pad_inches=0.25,
                facecolor=fig.get_facecolor())
    fig.savefig(svg, bbox_inches="tight", pad_inches=0.25,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {png.relative_to(ROOT)}")
    print(f"Wrote {svg.relative_to(ROOT)}")


def main():
    build_engineering_schematic()
    build_dataflow_diagram()


if __name__ == "__main__":
    main()
