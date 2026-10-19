"""
The Ghana map, built with Folium as the platform has always built it.

Folium writes a self-contained Leaflet page, so the export produces an HTML
file and the site embeds it. That keeps one map implementation rather than two,
and it is the same OpenStreetMap basemap and the same region centroids the
Streamlit pages use.

Circles, not shading. No specimen in the platform carries usable coordinates
and there are no boundary polygons here, so each region is a circle at its
centroid. Area is proportional to isolates -- scaling the radius instead makes
a region with four times the isolates look sixteen times the size.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import folium

from src.ghana_map import GHANA_REGIONS

#: Ghana's extent. The map is fitted to these rather than opened at a fixed
#: zoom, because zoom_start depends on the size of the container and the
#: container here is an iframe whose width the page decides. Fitting bounds
#: gets the same frame at any size.
GHANA_BOUNDS = [[4.5, -3.35], [11.25, 1.25]]
GHANA_CENTRE = [7.95, -1.05]

#: Non-susceptibility bands. Sequential blues rather than red-to-green, which
#: is the pair that disappears under the commonest colour vision deficiency.
BANDS = [
    (20.0, "#dbeafe", "under 20%"),
    (35.0, "#93c5fd", "20-35%"),
    (50.0, "#60a5fa", "35-50%"),
    (65.0, "#2563eb", "50-65%"),
    (float("inf"), "#1e3a8a", "65% and over"),
]


def _band(percent: Optional[float]) -> str:
    if percent is None:
        return "#bdc3c7"
    for limit, colour, _ in BANDS:
        if percent < limit:
            return colour
    return BANDS[-1][1]


def _legend_html() -> str:
    rows = "".join(
        f'<div style="margin:2px 0"><span style="display:inline-block;width:12px;'
        f'height:12px;background:{colour};border:1px solid rgba(0,0,0,.25);'
        f'margin-right:6px;vertical-align:-1px"></span>{label}</div>'
        for _, colour, label in BANDS)
    return f"""
    <div style="position:fixed;bottom:18px;left:12px;z-index:9999;
                background:rgba(255,255,255,.94);border:1px solid #c9ced1;
                border-radius:6px;padding:8px 10px;font:12px/1.4 system-ui,
                -apple-system,'Segoe UI',sans-serif;color:#16181a">
      <div style="font-weight:700;margin-bottom:4px">Non-susceptible</div>
      {rows}
      <div style="margin-top:5px;color:#6b7378">Circle area = isolates</div>
    </div>
    """


def build_region_map(regions: List[Dict[str, object]], out_path: str) -> str:
    """Write the region map and return the path it was written to.

    ``regions`` is the already-suppressed export payload, so nothing reaches
    the map that was not cleared for publication.
    """
    counts = [float(r["isolates"]) for r in regions
              if isinstance(r.get("isolates"), (int, float))]
    largest = max(counts) if counts else 1.0

    world = folium.Map(location=GHANA_CENTRE, tiles="OpenStreetMap",
                       prefer_canvas=True, control_scale=True,
                       min_zoom=5, max_zoom=12)
    world.fit_bounds(GHANA_BOUNDS)

    for row in regions:
        name = str(row.get("region", ""))
        centroid = GHANA_REGIONS.get(name)
        if not centroid:
            continue
        lat, lon = centroid

        value = row.get("isolates")
        isolates = float(value) if isinstance(value, (int, float)) else None
        percent = row.get("percent_non_susceptible")
        percent = float(percent) if isinstance(percent, (int, float)) else None

        if isolates is None:
            # Withheld or absent: an outline, never a filled circle, so it
            # cannot be read as a small count.
            folium.CircleMarker(
                location=[lat, lon], radius=6, color="#6b7378", weight=1,
                dash_array="3", fill=False,
                tooltip=f"{name}: not published").add_to(world)
            continue

        radius = 5 + 13 * (isolates / largest) ** 0.5
        rate = f"{percent:.1f}%" if percent is not None else "not published"
        popup = folium.Popup(
            f"<div style=\"font:13px/1.5 system-ui,sans-serif\">"
            f"<strong>{name}</strong><br>"
            f"{int(isolates):,} isolates<br>"
            f"{rate} non-susceptible<br>"
            f"{row.get('organisms', '')} organisms &middot; "
            f"{row.get('laboratories', '')} laboratories</div>",
            max_width=260)

        folium.CircleMarker(
            location=[lat, lon], radius=radius, color="#16181a", weight=1,
            opacity=0.45, fill=True, fill_color=_band(percent),
            fill_opacity=0.82, popup=popup,
            tooltip=f"{name}: {int(isolates):,} isolates, {rate}",
        ).add_to(world)

        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(html=(
                '<div style="font:11px/1 system-ui,sans-serif;font-weight:700;'
                'color:#16181a;text-shadow:0 0 3px #fff,0 0 3px #fff;'
                'white-space:nowrap;transform:translate(-50%,-'
                f'{radius + 10:.0f}px)">{name}</div>'))
        ).add_to(world)

    world.get_root().html.add_child(folium.Element(_legend_html()))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    world.save(out_path)
    return out_path


__all__ = ["build_region_map", "GHANA_CENTRE", "GHANA_BOUNDS"]
