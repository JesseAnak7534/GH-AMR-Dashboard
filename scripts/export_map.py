"""
The Ghana map, built with Folium as the platform has always built it.

Folium writes a self-contained Leaflet page, so the export produces an HTML
file and the site embeds it. That keeps one map implementation rather than two,
and it is the same OpenStreetMap basemap and the same region centroids the
Streamlit pages use.

The map shows **where resistance is**, with the reader choosing which result to
see: resistant, intermediate, susceptible, or the isolate count alone. Each is
a base layer in Leaflet's own control, so the choice is a radio button on the
map itself rather than a separate widget beside it.

Colour follows the convention already used throughout this platform --
``{'R': '#d62728', 'I': '#ff7f0e', 'S': '#2ca02c'}`` -- shaded by rate within
each. Red and green are a poor pair for the roughly one man in twelve with a
colour vision deficiency, so the figure is never left to the colour: every
circle carries its percentage in the tooltip, all three rates are in the popup,
and the table beneath the map repeats the lot.

Circles, not shading. No specimen in the platform carries usable coordinates
and there are no boundary polygons here, so each region is a circle at its
centroid.

**The circle is sized by the figure on display.** On the resistant layer a
bigger circle means more resistance, on the susceptible layer it means more
susceptibility, and on the count layer it means more isolates. Sizing every
layer by the isolate count instead left sixteen near-identical circles, since
every region here reports a similar number -- the map showed nothing.

The size scale for a rate runs between the smallest and largest value on the
layer rather than from zero. A set of rates between 30% and 48% mapped from
zero gives circles within a fifth of each other, which is no scale at all. The
legend therefore prints the three reference sizes with the values they stand
for, so a reader can decode a circle rather than guess at it, and the exact
figure is on every tooltip. Counts, which have a true zero, are scaled from it
by area -- scaling the radius would make four times the isolates look sixteen
times the size.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import folium

from src.ghana_map import GHANA_REGIONS

#: Ghana's extent. The map is fitted to these rather than opened at a fixed
#: zoom, because zoom_start depends on the size of the container and the
#: container here is an iframe whose width the page decides.
GHANA_BOUNDS = [[4.5, -3.35], [11.25, 1.25]]
GHANA_CENTRE = [7.95, -1.05]

#: The platform's S/I/R colours, and a five-step ramp of each. The darkest step
#: is the base colour; the lighter steps are it mixed toward white.
LAYERS: List[Dict[str, object]] = [
    {
        "key": "resistant",
        "name": "Resistant (R)",
        "base": "#d62728",
        "ramp": ["#fbe3e3", "#f3b0b0", "#e87a7a", "#dc4a4a", "#d62728"],
        "default": True,
    },
    {
        "key": "intermediate",
        "name": "Intermediate (I)",
        "base": "#ff7f0e",
        "ramp": ["#ffeedd", "#ffd1a3", "#ffb166", "#ff9733", "#ff7f0e"],
        "default": False,
    },
    {
        "key": "susceptible",
        "name": "Susceptible (S)",
        "base": "#2ca02c",
        "ramp": ["#e3f3e3", "#b5debb", "#81c784", "#4caf50", "#2ca02c"],
        "default": False,
    },
    {
        "key": None,
        "name": "All isolates (count only)",
        "base": "#1f77b4",
        "ramp": ["#1f77b4"] * 5,
        "default": False,
    },
]

#: Rate bands, shared by every layer so the five steps mean the same thing
#: whichever result is on screen.
BAND_EDGES = [10.0, 25.0, 40.0, 60.0]
BAND_LABELS = ["under 10%", "10-25%", "25-40%", "40-60%", "60% and over"]


def _step(percent: Optional[float]) -> int:
    if percent is None:
        return -1
    for index, edge in enumerate(BAND_EDGES):
        if percent < edge:
            return index
    return len(BAND_EDGES)


def _legend(layer: Dict[str, object]) -> str:
    ramp = layer["ramp"]            # type: ignore[index]
    rows = "".join(
        f'<div style="margin:2px 0"><span style="display:inline-block;width:12px;'
        f'height:12px;background:{ramp[i]};border:1px solid rgba(0,0,0,.25);'
        f'margin-right:6px;vertical-align:-1px"></span>{BAND_LABELS[i]}</div>'
        for i in range(len(BAND_LABELS)))
    return (f'<div style="font-weight:700;margin:6px 0 3px">'
            f'{layer["name"]}</div>{rows}')


#: Circle radii, in pixels, from the smallest value on a layer to the largest.
R_MIN, R_MAX = 7.0, 27.0


def _sizer(values: List[float], from_zero: bool):
    """Return a function mapping a value to a radius, and the key points.

    ``from_zero`` is right for a count, which has a true zero and should be
    compared by area. It is wrong for a rate: a set of rates between 30% and
    48% anchored at zero produces circles within a fifth of each other, and a
    map nobody can read is not more honest than one with a stated scale.
    """
    if not values:
        return (lambda v: R_MIN), []
    low, high = min(values), max(values)
    if from_zero:
        low = 0.0
    span = high - low

    def radius(value: Optional[float]) -> float:
        if value is None:
            return R_MIN
        if span <= 0:
            return (R_MIN + R_MAX) / 2
        share = (value - low) / span
        # Area-proportional for counts, linear for a rate's narrow band.
        share = share ** 0.5 if from_zero else share
        return R_MIN + (R_MAX - R_MIN) * max(0.0, min(1.0, share))

    marks = [low, (low + high) / 2, high] if span > 0 else [high]
    return radius, marks


def _size_key(marks: List[float], suffix: str, radius) -> str:
    """Three reference circles, so a size can be read back as a number."""
    if not marks:
        return ""
    circles = ""
    for mark in marks:
        r = radius(mark)
        circles += (
            f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0">'
            f'<span style="display:inline-flex;width:{2*R_MAX:.0f}px;'
            f'justify-content:center"><span style="display:inline-block;'
            f'width:{2*r:.0f}px;height:{2*r:.0f}px;border-radius:50%;'
            f'background:#cfd6da;border:1px solid rgba(0,0,0,.35)"></span></span>'
            f'<span>{mark:,.1f}{suffix}</span></div>')
    return ('<div style="font-weight:700;margin:7px 0 2px">Circle size</div>'
            + circles)


def _legend_html(size_key: str) -> str:
    blocks = "".join(_legend(layer) for layer in LAYERS if layer["key"])
    return f"""
    <div style="position:fixed;bottom:16px;left:12px;z-index:9999;
                background:rgba(255,255,255,.95);border:1px solid #c9ced1;
                border-radius:6px;padding:8px 10px;max-height:66%;
                overflow:auto;font:11.5px/1.35 system-ui,-apple-system,
                'Segoe UI',sans-serif;color:#16181a">
      <div style="font-weight:700;margin-bottom:2px">Share of results</div>
      {blocks}
      {size_key}
      <div style="margin-top:6px;color:#6b7378">Size and shade both follow the
        result you pick, top right.</div>
    </div>
    """


def _tooltip(name: str, row: Dict[str, object]) -> str:
    def pct(key: str) -> str:
        value = row.get(f"percent_{key}")
        return f"{float(value):.1f}%" if isinstance(value, (int, float)) else "—"
    return (f"{name}: R {pct('resistant')} · I {pct('intermediate')} · "
            f"S {pct('susceptible')}")


def _popup(name: str, row: Dict[str, object]) -> folium.Popup:
    def line(label: str, key: str, colour: str) -> str:
        count = row.get(key)
        percent = row.get(f"percent_{key}")
        count_text = f"{int(count):,}" if isinstance(count, (int, float)) else "—"
        percent_text = (f"{float(percent):.1f}%"
                        if isinstance(percent, (int, float)) else "—")
        return (f'<div><span style="display:inline-block;width:10px;height:10px;'
                f'background:{colour};border-radius:2px;margin-right:6px"></span>'
                f'{label} <strong>{percent_text}</strong> '
                f'<span style="color:#6b7378">({count_text})</span></div>')

    isolates = row.get("isolates")
    isolates_text = (f"{int(isolates):,}" if isinstance(isolates, (int, float))
                     else "not published")
    interpreted = row.get("interpreted")
    interpreted_text = (f"{int(interpreted):,}"
                        if isinstance(interpreted, (int, float)) else "—")
    return folium.Popup(
        f'<div style="font:13px/1.55 system-ui,sans-serif;min-width:190px">'
        f'<strong style="font-size:14px">{name}</strong><br>'
        f'<span style="color:#6b7378">{isolates_text} isolates · '
        f'{interpreted_text} results</span>'
        f'<div style="margin-top:6px">'
        + line("Resistant", "resistant", "#d62728")
        + line("Intermediate", "intermediate", "#ff7f0e")
        + line("Susceptible", "susceptible", "#2ca02c")
        + "</div></div>",
        max_width=280)


def build_region_map(regions: List[Dict[str, object]], out_path: str) -> str:
    """Write the region map and return the path it was written to.

    ``regions`` is the already-suppressed export payload, so nothing reaches
    the map that was not cleared for publication.
    """
    def values_for(key: Optional[str]) -> List[float]:
        field = f"percent_{key}" if key else "isolates"
        return [float(r[field]) for r in regions
                if isinstance(r.get(field), (int, float))]

    # The basemap is added with control=False so it does not appear in the
    # layer control beside the data layers. Folium would otherwise list it as a
    # base layer too, and selecting it would switch every circle off -- a
    # control that can blank the map is worse than no control.
    # zoom_start as well as fit_bounds: with tiles=None Leaflet has no zoom
    # until something sets one, and fit_bounds runs against a container the
    # iframe has not sized yet, which left the whole country as a thumbnail in
    # the middle of the frame. The explicit zoom is the floor; fit_bounds then
    # refines it once the container has dimensions.
    # scrollWheelZoom off: the map sits inside a scrolling page, and a wheel
    # over it would zoom the map instead of moving the page -- which reads as
    # the page freezing, and leaves the reader on a view of the Atlantic. The
    # +/- buttons and double-click still zoom.
    world = folium.Map(location=GHANA_CENTRE, tiles=None, zoom_start=7,
                       prefer_canvas=True, control_scale=True,
                       scrollWheelZoom=False, min_zoom=5, max_zoom=12)
    folium.TileLayer("OpenStreetMap", control=False).add_to(world)
    world.fit_bounds(GHANA_BOUNDS)

    size_keys: List[str] = []

    for layer in LAYERS:
        key = layer["key"]
        # Each layer gets its own scale, because a percentage and a count are
        # not comparable and a shared scale would flatten one of them.
        radius_for, marks = _sizer(values_for(key), from_zero=key is None)
        size_keys.append(_size_key(marks, "%" if key else "", radius_for))
        # overlay=False makes each a *base* layer, so Leaflet renders the
        # control as radio buttons: one result at a time, which is what a
        # comparison between regions needs.
        group = folium.FeatureGroup(name=str(layer["name"]), overlay=False,
                                    show=bool(layer["default"]))

        for row in regions:
            name = str(row.get("region", ""))
            centroid = GHANA_REGIONS.get(name)
            if not centroid:
                continue
            lat, lon = centroid

            isolates = row.get("isolates")
            isolates = (float(isolates)
                        if isinstance(isolates, (int, float)) else None)
            if isolates is None:
                folium.CircleMarker(
                    location=[lat, lon], radius=6, color="#6b7378", weight=1,
                    dash_array="3", fill=False,
                    tooltip=f"{name}: not published").add_to(group)
                continue

            percent = row.get(f"percent_{key}") if key else None
            percent = (float(percent)
                       if isinstance(percent, (int, float)) else None)
            step = _step(percent) if key else len(BAND_EDGES)
            ramp = layer["ramp"]                       # type: ignore[index]
            fill = "#ffffff" if step < 0 else ramp[step]

            radius = radius_for(percent if key else isolates)
            folium.CircleMarker(
                location=[lat, lon], radius=radius, color="#16181a", weight=1,
                opacity=0.45, fill=True, fill_color=fill, fill_opacity=0.85,
                tooltip=_tooltip(name, row), popup=_popup(name, row),
            ).add_to(group)

            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(html=(
                    '<div style="font:11px/1 system-ui,sans-serif;'
                    'font-weight:700;color:#16181a;'
                    'text-shadow:0 0 3px #fff,0 0 3px #fff;white-space:nowrap;'
                    f'transform:translate(-50%,-{radius + 10:.0f}px)">'
                    f'{name}</div>'))
            ).add_to(group)

        group.add_to(world)

    folium.LayerControl(collapsed=False, position="topright").add_to(world)
    # The key for the layer shown first. Each layer has its own scale, and a
    # legend that changed on click would need scripting the saved page does
    # not carry; the tooltip gives the exact figure on every circle either way.
    world.get_root().html.add_child(
        folium.Element(_legend_html(size_keys[0] if size_keys else "")))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    world.save(out_path)
    return out_path


__all__ = ["build_region_map", "GHANA_CENTRE", "GHANA_BOUNDS", "LAYERS"]
