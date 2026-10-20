"""
The public landing page.

A door, not a dashboard. It is the only page written on the assumption that the
reader has no account, no briefing and no obligation to stay, so it answers
three questions in the first screen -- what this is, how much data stands
behind it, and what can be looked at -- and then gets out of the way.

Deliberately, no analysis happens here. An earlier version carried four tabs of
tables and charts, which meant a first-time visitor met a cumulative
antibiogram before being told what they were looking at. The sections now live
on their own pages (``src/page_public.py``) and this page is six cards leading
to them.

**The whole card is the link.** Streamlit has no clickable container, so the
card is not a Streamlit container at all: the grid is one block of HTML in
which each card is an ``<a>``. That buys three things a button inside a
bordered box cannot. The entire box is a target, not a strip at its foot. Every
section gets a real URL -- ``?page=public:resistance`` -- so a reader can
bookmark a section, a colleague can be sent a link to it, and the browser's
back button works. And the cards lay out on a CSS grid, so they keep equal
heights and reflow on a narrow screen instead of staying three fixed columns.

Nothing inside the HTML is a Streamlit widget. That is what went wrong the last
time this page used wrapper markup: a ``st.markdown`` div opened around real
widgets does not contain them, it just leaves an empty box drawn on the page.

Each card carries one live number, so the grid is not a menu of promises: a
reader can see before clicking whether the genomics section has 1,800 genomes
behind it or none. Those numbers come from one cached count query.

Three rules hold here as on every public page.

**Nothing identifies a person.** No patient pseudonym, no specimen identifier,
no record-level row. The cards show collection-level totals only.

**Nothing is stated more confidently than the data supports.** The coverage line
is not a disclaimer; it is the part that lets a reader judge everything else.

**Colour never carries a meaning on its own.** Each card's colour is repeated by
its badge text and its title, so a reader who sees no colour at all loses
nothing but speed. See ``src.palette``.

Laboratory identity is shown deliberately. It is in the data, attribution is
the point of sentinel surveillance, and a rate nobody can attribute is a rate
nobody can act on.
"""

from __future__ import annotations

from html import escape
from typing import Dict, Optional
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

from src import palette
from src.page_public import SECTIONS, Section, landing_counts

#: The institution behind the platform, named on the page a visitor arrives at.
#: A surveillance figure with no owner is a figure nobody is accountable for.
OWNER = "Institute of Computational Biology and Bioinformatics"
OWNER_SHORT = "ICBB-AMRSS"

#: Warm editorial tokens, matching the theme in ``.streamlit/config.toml`` so
#: the page does not read as two designs stacked on each other.
_INK = "#1a170e"
_DEEP = "#1d4d43"
_SURFACE = "#fdfaf2"
_LINE = "rgba(26, 23, 14, 0.14)"
_MUTED = "rgba(26, 23, 14, 0.62)"


def _href(page: Optional[str]) -> str:
    """A link to one page, preserving whatever else is in the URL.

    ``?admin=1`` has to survive a click, or an administrator who followed a
    card loses the staff door and has to retype the query string.
    """
    params = {}
    try:
        for key, value in st.query_params.items():
            if key != "page":
                params[key] = value
    except Exception:                                 # noqa: BLE001
        params = {}
    if page:
        params["page"] = page
    return "?" + urlencode(params) if params else "?"


_CSS = f"""
<style>
  .amr-hero {{
      background: linear-gradient(135deg, {_DEEP} 0%, #16382f 100%);
      color: #f6efdd;
      border-radius: 0.9rem;
      padding: 2.4rem 2.2rem 2rem 2.2rem;
      margin-bottom: 1.1rem;
  }}
  .amr-eyebrow {{
      font-size: 0.74rem;
      letter-spacing: 0.17em;
      text-transform: uppercase;
      color: rgba(246, 239, 221, 0.72);
      margin-bottom: 0.7rem;
  }}
  .amr-hero h1 {{
      font-size: clamp(1.9rem, 4.2vw, 3rem);
      line-height: 1.07;
      font-weight: 700;
      margin: 0 0 0.85rem 0;
      color: #f6efdd;
      letter-spacing: -0.015em;
  }}
  .amr-hero p {{
      font-size: 1.04rem;
      line-height: 1.62;
      max-width: 60ch;
      margin: 0;
      color: rgba(246, 239, 221, 0.9);
  }}
  .amr-hero .amr-fineprint {{
      font-size: 0.86rem;
      margin-top: 0.9rem;
      color: rgba(246, 239, 221, 0.68);
      max-width: 72ch;
  }}

  .amr-stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 0.6rem;
      margin-bottom: 0.7rem;
  }}
  .amr-stat-cell {{
      background: {_SURFACE};
      border: 1px solid {_LINE};
      border-radius: 0.6rem;
      padding: 0.85rem 0.95rem;
  }}
  .amr-stat-cell .n {{
      display: block;
      font-size: 1.62rem;
      font-weight: 700;
      line-height: 1.1;
      color: {_INK};
      letter-spacing: -0.01em;
  }}
  .amr-stat-cell .k {{
      display: block;
      font-size: 0.78rem;
      color: {_MUTED};
      margin-top: 0.15rem;
  }}
  .amr-coverage {{
      font-size: 0.86rem;
      line-height: 1.55;
      color: {_MUTED};
      margin: 0 0 1.6rem 0;
      max-width: 88ch;
  }}

  .amr-section-label {{
      font-size: 0.74rem;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: {_MUTED};
      margin-bottom: 0.55rem;
  }}

  .amr-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(275px, 1fr));
      gap: 0.85rem;
      margin-bottom: 1.6rem;
  }}
  .amr-card {{
      display: flex;
      flex-direction: column;
      position: relative;
      overflow: hidden;
      background: {_SURFACE};
      border: 1px solid {_LINE};
      border-radius: 0.7rem;
      padding: 1.15rem 1.15rem 1.05rem 1.3rem;
      text-decoration: none !important;
      color: {_INK} !important;
      transition: box-shadow 150ms ease, transform 150ms ease,
                  border-color 150ms ease;
  }}
  .amr-card:hover, .amr-card:focus-visible {{
      box-shadow: 0 10px 26px rgba(26, 23, 14, 0.14);
      transform: translateY(-3px);
      border-color: rgba(26, 23, 14, 0.3);
      outline: none;
  }}
  .amr-card:focus-visible {{
      box-shadow: 0 0 0 3px rgba(29, 77, 67, 0.45);
  }}
  .amr-rule {{
      position: absolute;
      left: 0; top: 0; bottom: 0;
      width: 5px;
  }}
  .amr-card-head {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.55rem;
  }}
  .amr-badge {{
      font-size: 0.64rem;
      font-weight: 700;
      letter-spacing: 0.09em;
      color: #ffffff;
      padding: 0.17rem 0.42rem;
      border-radius: 0.25rem;
  }}
  .amr-card-title {{
      font-size: 1.12rem;
      font-weight: 700;
      letter-spacing: -0.005em;
  }}
  .amr-stat {{
      font-size: 2.15rem;
      font-weight: 700;
      line-height: 1.05;
      letter-spacing: -0.02em;
  }}
  .amr-unit {{
      font-size: 0.79rem;
      color: {_MUTED};
      margin-bottom: 0.6rem;
  }}
  .amr-blurb {{
      font-size: 0.89rem;
      line-height: 1.55;
      color: rgba(26, 23, 14, 0.78);
      flex-grow: 1;
  }}
  .amr-cta {{
      font-size: 0.83rem;
      font-weight: 600;
      margin-top: 0.85rem;
  }}

  .amr-notes {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
      gap: 1.3rem;
      border-top: 1px solid {_LINE};
      padding-top: 1.2rem;
  }}
  .amr-notes h4 {{
      font-size: 0.95rem;
      font-weight: 700;
      margin: 0 0 0.4rem 0;
      color: {_INK};
  }}
  .amr-notes p {{
      font-size: 0.86rem;
      line-height: 1.6;
      color: {_MUTED};
      margin: 0;
  }}
  .amr-owner {{
      font-size: 0.82rem;
      color: {_MUTED};
      margin-top: 1.2rem;
  }}
</style>
"""


def _hero() -> str:
    return f"""
<div class="amr-hero">
  <div class="amr-eyebrow">{escape(OWNER_SHORT)} &middot; One Health surveillance</div>
  <h1>Antimicrobial resistance in Ghana</h1>
  <p>Resistance, the organisms behind it, the antimicrobials being used and the
  genomes explaining it &mdash; collected across human, animal, food,
  environmental and aquaculture sources, and reported together.</p>
  <div class="amr-fineprint">Published by the {escape(OWNER)}, University of
  Ghana. Everything on these pages is an aggregate: no patient, specimen or
  individual result is shown.</div>
</div>
"""


def _stats(counts: Dict[str, object]) -> str:
    cells = [
        (int(counts.get("specimens") or 0), "Specimens"),
        (int(counts.get("isolates") or 0), "Isolates"),
        (int(counts.get("results") or 0), "Susceptibility results"),
        (int(counts.get("genomes") or 0), "Genomes sequenced"),
        (int(counts.get("labs") or 0), "Laboratories"),
        (int(counts.get("regions") or 0), "Regions"),
    ]
    blocks = "".join(
        f'<div class="amr-stat-cell"><span class="n">{value:,}</span>'
        f'<span class="k">{escape(label)}</span></div>'
        for value, label in cells)
    return f'<div class="amr-stats">{blocks}</div>'


def _coverage(counts: Dict[str, object]) -> str:
    """The collection window, stated in words rather than as two timestamps."""
    try:
        start = pd.to_datetime(counts.get("first_collected"), errors="coerce",
                               utc=True)
        end = pd.to_datetime(counts.get("last_collected"), errors="coerce",
                             utc=True)
    except Exception:                                 # noqa: BLE001
        return ""
    if pd.isna(start) or pd.isna(end):
        return ""
    sectors = int(counts.get("sectors") or 0)
    return (
        f'<p class="amr-coverage">Specimens collected between '
        f'<strong>{start:%B %Y}</strong> and <strong>{end:%B %Y}</strong>, '
        f'across {sectors} sector{"s" if sectors != 1 else ""}. Each '
        "patient's first isolate of an organism is counted once, following "
        "CLSI M39, so repeat sampling of one patient does not weight any "
        "figure.</p>")


def _card(section: Section, counts: Dict[str, object]) -> str:
    value, unit = section.stat(counts)
    return f"""
<a class="amr-card" href="{escape(_href(section.key))}" target="_self"
   aria-label="Open {escape(section.title)}">
  <span class="amr-rule" style="background:{section.colour}"></span>
  <span class="amr-card-head">
    <span class="amr-badge" style="background:{section.colour}">{escape(section.icon)}</span>
    <span class="amr-card-title">{escape(section.title)}</span>
  </span>
  <span class="amr-stat" style="color:{section.colour}">{escape(value)}</span>
  <span class="amr-unit">{escape(unit)}</span>
  <span class="amr-blurb">{escape(section.blurb)}</span>
  <span class="amr-cta" style="color:{section.colour}">Open {escape(section.title)} &rarr;</span>
</a>
"""


def _grid(counts: Dict[str, object]) -> str:
    cards = "".join(_card(section, counts) for section in SECTIONS)
    return (f'<div class="amr-section-label">Explore the surveillance</div>'
            f'<div class="amr-grid">{cards}</div>')


def _notes() -> str:
    """The owner line. The two explanatory blocks that used to sit here were
    removed: the figures carry themselves, and the page is a door."""
    return f"""
<p class="amr-owner">{escape(OWNER)}, University of Ghana</p>
"""


def render_home_page() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(_hero(), unsafe_allow_html=True)

    # The database sits on the far side of a network the platform does not
    # control, and some networks reset the PostgreSQL TLS handshake outright.
    # Letting that surface as a traceback took the whole page down, including
    # the staff sign-in, so an administrator could not reach the form to find
    # out what was wrong.
    try:
        counts = landing_counts()
        failure = None
    except Exception as error:                        # noqa: BLE001
        counts, failure = {}, error

    if failure is not None:
        st.error(
            "The surveillance database could not be reached, so no figures "
            "can be shown. This is a connection problem, not an absence of "
            "data.")
        st.caption(
            "Networks that inspect database traffic block the PostgreSQL TLS "
            "handshake: the port opens and the connection is then reset. "
            "Trying another network is the quickest way to tell a local cause "
            "from a provider one.")
        with st.expander("Technical detail"):
            st.code(str(failure)[:1200])
        _staff_door()
        return

    if not int(counts.get("specimens") or 0):
        st.info(
            "No surveillance data has been published yet. Once data is "
            "available, this page will show how much of it there is and open "
            "onto the resistance, organism, One Health, genomic and "
            "antimicrobial-use sections.")
        st.markdown(_notes(), unsafe_allow_html=True)
        _staff_door()
        return

    # One block, so the browser lays the grid out rather than Streamlit laying
    # out three columns that cannot equalise their heights.
    st.markdown(_stats(counts) + _coverage(counts) + _grid(counts) + _notes(),
                unsafe_allow_html=True)

    _staff_door()
    _admin_hint()


def _staff_door() -> None:
    """The way in for staff.

    The sidebar is hidden from the public surface, which left the sign-in
    reachable only by typing ``?admin=1`` into the address bar -- so the
    platform's own administrator had no way in.
    """
    if st.session_state.get("authenticated"):
        return

    _, door = st.columns([5, 1])
    with door:
        if st.button("Staff sign-in", use_container_width=True,
                     help="Opens the sign-in panel for laboratory and "
                          "programme staff."):
            # Straight to the flag the sign-in screen is gated on. Setting
            # ?admin=1 and calling st.rerun() did not work: the rerun raises
            # immediately and the query-parameter update never reached the
            # browser, so the button appeared to do nothing at all.
            st.session_state.show_login = True
            st.rerun()


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


__all__ = ["render_home_page", "OWNER", "OWNER_SHORT"]
