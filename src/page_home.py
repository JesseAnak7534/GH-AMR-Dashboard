"""
The public landing page.

A door, not a dashboard. It is the only page written on the assumption that the
reader has no account, no briefing and no obligation to stay, so it answers
three questions in the first screen -- what this is, how much data stands
behind it, and what can be looked at -- and then gets out of the way.

Deliberately, no analysis happens here. An earlier version of this page carried
four tabs of tables and charts, which meant a first-time visitor met a
cumulative antibiogram before they had been told what they were looking at, and
every section competed with the others for the same screen. The sections now
live on their own pages (``src/page_public.py``) and this page is six cards that
lead to them.

Each card carries one live number, so the grid is not a menu of promises: a
reader can see before clicking that the genomics section has 1,800 genomes
behind it or that it has none. Those numbers come from one cached count query,
because six cards each running their own aggregate would open six connections
on the one page that has to be fast.

Three rules hold here as on every public page.

**Nothing identifies a person.** No patient pseudonym, no specimen identifier,
no record-level row. The cards show collection-level totals only.

**Nothing is stated more confidently than the data supports.** The coverage line
at the foot is not a disclaimer; it is the part that lets a reader judge
everything above it.

**Colour never carries a meaning on its own.** Each card's colour is repeated by
its badge text and its title, so a reader who sees no colour at all loses
nothing but speed. See ``src.palette``.

Laboratory identity is shown deliberately. It is in the data, attribution is
the point of sentinel surveillance, and a rate nobody can attribute is a rate
nobody can act on.
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import streamlit as st

from src import palette
from src.page_public import SECTIONS, Section, go, landing_counts

#: The institution behind the platform, named on the page a visitor arrives at.
#: A surveillance figure with no owner is a figure nobody is accountable for.
OWNER = "Institute for Clinical Biochemistry and Biotechnology"
OWNER_SHORT = "ICBB-AMRSS"


def _hero(counts: Dict[str, object]) -> None:
    st.markdown(
        f"<div style='font-size:0.85rem;letter-spacing:0.12em;"
        f"text-transform:uppercase;color:{palette.GREY};margin-bottom:0.2rem'>"
        f"{OWNER_SHORT} &middot; antimicrobial resistance surveillance</div>",
        unsafe_allow_html=True)
    st.title("Antimicrobial resistance in Ghana")
    st.markdown(
        "Resistance, the organisms behind it, the antimicrobials being used "
        "and the genomes explaining it -- collected across human, animal, "
        "food, environmental and aquaculture sources and reported together. "
        f"Published by the {OWNER}, University of Ghana.")
    st.caption(
        "Everything on these pages is an aggregate. No patient, specimen or "
        "individual result is shown, and any figure resting on too few records "
        "is withheld rather than published.")


def _headline(counts: Dict[str, object]) -> None:
    cells = st.columns(5)
    cells[0].metric("Specimens", f"{int(counts.get('specimens') or 0):,}")
    cells[1].metric("Isolates", f"{int(counts.get('isolates') or 0):,}")
    cells[2].metric("Susceptibility results",
                    f"{int(counts.get('results') or 0):,}")
    cells[3].metric("Genomes", f"{int(counts.get('genomes') or 0):,}")
    cells[4].metric("Laboratories", f"{int(counts.get('labs') or 0):,}")

    period = _period(counts)
    if period:
        st.caption(period)


def _period(counts: Dict[str, object]) -> Optional[str]:
    """The collection window, stated in words rather than as two timestamps."""
    first = counts.get("first_collected")
    last = counts.get("last_collected")
    try:
        start = pd.to_datetime(first, errors="coerce", utc=True)
        end = pd.to_datetime(last, errors="coerce", utc=True)
    except Exception:                                 # noqa: BLE001
        return None
    if pd.isna(start) or pd.isna(end):
        return None
    sectors = int(counts.get("sectors") or 0)
    regions = int(counts.get("regions") or 0)
    return (f"Specimens collected between {start:%B %Y} and {end:%B %Y}, "
            f"across {sectors} sector{'s' if sectors != 1 else ''} and "
            f"{regions} region{'s' if regions != 1 else ''}. Each patient's "
            "first isolate of an organism is counted once, following CLSI M39, "
            "so repeat sampling of one patient does not weight any figure.")


def _card(section: Section, counts: Dict[str, object]) -> None:
    """One card.

    Streamlit has no clickable container, so the card is a bordered block with
    a button at its foot rather than a link-shaped div. That is the honest
    version: a reader can see what is clickable instead of discovering it by
    hovering, and it keeps the whole card out of raw HTML, which is what broke
    the layout the last time this page was built with wrapper markup.
    """
    value, unit = section.stat(counts)
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:0.55rem;"
            f"margin-bottom:0.35rem'>"
            f"<span style='background:{section.colour};color:#ffffff;"
            f"font-size:0.7rem;font-weight:700;letter-spacing:0.08em;"
            f"padding:0.15rem 0.45rem;border-radius:0.25rem'>"
            f"{section.icon}</span>"
            f"<span style='font-size:1.15rem;font-weight:700'>"
            f"{section.title}</span></div>"
            f"<div style='font-size:2.1rem;font-weight:700;line-height:1.1;"
            f"color:{section.colour}'>{value}</div>"
            f"<div style='font-size:0.8rem;color:{palette.GREY};"
            f"margin-bottom:0.5rem'>{unit}</div>",
            unsafe_allow_html=True)
        st.write(section.blurb)
        if st.button(f"Open {section.title}", key=f"card_{section.key}",
                     use_container_width=True):
            go(section.key)


#: Card styling. Streamlit draws a bordered container as a flat box, which is
#: correct for a form and too quiet for something a reader is meant to click.
#: This lifts it on hover and gives the button inside it the whole card's width
#: -- the only two cues available without rebuilding the card as raw HTML,
#: which is what broke this layout the last time it was attempted.
_CARD_CSS = """
<style>
  div[data-testid="stVerticalBlockBorderWrapper"] {
      border-radius: 0.6rem;
      transition: box-shadow 140ms ease, transform 140ms ease;
      height: 100%;
  }
  div[data-testid="stVerticalBlockBorderWrapper"]:hover {
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.12);
      transform: translateY(-2px);
  }
</style>
"""


def _grid(counts: Dict[str, object]) -> None:
    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    st.subheader("Explore the surveillance")
    st.caption(
        "Each section opens its own page, with its own filters and its own "
        "statement of what it does not show.")
    for start in range(0, len(SECTIONS), 3):
        row = SECTIONS[start:start + 3]
        columns = st.columns(3)
        for column, section in zip(columns, row):
            with column:
                _card(section, counts)


def _footer() -> None:
    st.markdown("---")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**How to read anything on these pages**")
        st.caption(
            "A percentage is never published on fewer than thirty isolates, "
            "every percentage carries a 95% confidence interval, rates are "
            "pooled rather than averaged across facilities, and sectors are "
            "never combined into one national figure unless a page says so. "
            "Counts resting on fewer than five records are withheld -- and "
            "withheld means too few to publish, not none found.")
    with right:
        st.markdown("**What this is and is not**")
        st.caption(
            "This is laboratory-based sentinel surveillance. It describes the "
            "isolates that reached a participating laboratory, which is not a "
            "random sample of infections in the country: specimens arrive more "
            "often from severe infections and from facilities with a "
            "laboratory on site. It is not a measure of the burden of "
            "resistance in the general population.")

    st.caption(
        f"{OWNER}, University of Ghana. Laboratories are named throughout, "
        "because a rate nobody can attribute is a rate nobody can act on.")

    _admin_hint()


def _admin_hint() -> None:
    """Shown only to someone who already asked for it.

    There is no sign-in control on the public surface: a visitor has no account
    and no use for a login box, and offering one makes a published page look
    like something they are being kept out of. Administrators append
    ``?admin=1``. That is not the security measure -- the password is -- it
    only keeps the staff door off the shop front.
    """
    try:
        wants = str(st.query_params.get("admin", "")).lower() in (
            "1", "true", "yes")
    except Exception:                                 # noqa: BLE001
        wants = False
    if wants:
        st.caption("Administrative view requested. Sign in from the sidebar.")


def render_home_page() -> None:
    counts = landing_counts()

    _hero(counts)

    if not int(counts.get("specimens") or 0):
        st.info(
            "No surveillance data has been published yet. Once data is "
            "available, this page will show how much of it there is and open "
            "onto the resistance, organism, One Health, genomic and "
            "antimicrobial-use sections.")
        _footer()
        return

    st.markdown("")
    _headline(counts)
    st.markdown("---")
    _grid(counts)
    _footer()


__all__ = ["render_home_page", "OWNER", "OWNER_SHORT"]
