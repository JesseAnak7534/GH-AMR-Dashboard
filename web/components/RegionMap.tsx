"use client";

import { useId, useState } from "react";
import { count, numeric, percent } from "@/lib/format";

/**
 * Regions as proportional symbols, not as shading.
 *
 * No specimen in the platform carries usable coordinates and the repository
 * holds no boundary polygons, so there is nothing to shade. Each region is
 * drawn at its centroid, sized by isolates. A circle at a point claims less
 * than a filled district: it says "this many isolates were reported from
 * somewhere in this region", which is exactly what the data supports.
 *
 * Area, not radius, is proportional to the count. Scaling the radius makes a
 * region with four times the isolates look sixteen times the size.
 *
 * Colour carries the non-susceptibility, and never alone: the percentage is
 * printed beside every symbol, and the table below the map holds the same
 * numbers.
 */

const SEA = "#f6f7f8";
const OUTLINE = "#c9ced1";

/** Ghana's extent, with a margin. Fixed so the projection does not shift when
 *  a region with no isolates drops out of the data. */
const BOUNDS = { minLat: 4.5, maxLat: 11.3, minLon: -3.4, maxLon: 1.3 };

export interface RegionPoint {
  region: string;
  isolates: number | string | null;
  percentNonSusceptible: number | null;
  lat: number;
  lon: number;
}

/** A five-step sequential ramp. Deliberately not red-to-green. */
const RAMP = ["#dbeafe", "#93c5fd", "#60a5fa", "#2563eb", "#1e3a8a"];

function band(value: number | null): number {
  if (value === null) return -1;
  if (value < 20) return 0;
  if (value < 35) return 1;
  if (value < 50) return 2;
  if (value < 65) return 3;
  return 4;
}

const BAND_LABELS = ["under 20%", "20–35%", "35–50%", "50–65%", "65% and over"];

export function RegionMap({ points }: { points: RegionPoint[] }) {
  const titleId = useId();
  const [hovered, setHovered] = useState<string | null>(null);

  const width = 560;
  const height = 620;
  const pad = 26;

  const x = (lon: number) =>
    pad +
    ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) *
      (width - 2 * pad);
  const y = (lat: number) =>
    pad +
    (1 - (lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat)) *
      (height - 2 * pad);

  const drawable = points.filter((p) => numeric(p.isolates) !== null);
  const max = Math.max(1, ...drawable.map((p) => numeric(p.isolates) as number));
  // Area-proportional: r = rMax * sqrt(v / vMax).
  const radius = (value: number) => 5 + 17 * Math.sqrt(value / max);

  return (
    <figure>
      <div className="overflow-x-auto rounded-lg border border-rule">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto w-full min-w-[380px]"
          style={{ background: SEA }}
          role="img"
          aria-labelledby={titleId}
        >
          <title id={titleId}>
            {`${drawable.length} regions, sized by isolates and shaded by non-susceptibility`}
          </title>

          <rect
            x={pad / 2}
            y={pad / 2}
            width={width - pad}
            height={height - pad}
            fill="none"
            stroke={OUTLINE}
            strokeWidth={1}
            strokeDasharray="3 4"
          />

          {points.map((point) => {
            const value = numeric(point.isolates);
            const index = band(point.percentNonSusceptible);
            const cx = x(point.lon);
            const cy = y(point.lat);
            const faded = hovered !== null && hovered !== point.region;
            return (
              <g
                key={point.region}
                opacity={faded ? 0.35 : 1}
                onMouseEnter={() => setHovered(point.region)}
                onMouseLeave={() => setHovered(null)}
              >
                {value === null ? (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={6}
                    fill="none"
                    stroke={OUTLINE}
                    strokeWidth={1.5}
                    strokeDasharray="2 2"
                  />
                ) : (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={radius(value)}
                    fill={index < 0 ? "#ffffff" : RAMP[index]}
                    stroke="#16181a"
                    strokeOpacity={0.35}
                    strokeWidth={1}
                  />
                )}
                {/* A white halo under the label, so a name that falls over a
                    neighbouring circle stays readable. Ghana's regions are not
                    evenly spaced and several centroids sit close together. */}
                <text
                  x={cx}
                  y={cy - (value === null ? 10 : radius(value) + 4)}
                  fontSize={9.5}
                  fill="#16181a"
                  stroke={SEA}
                  strokeWidth={2.6}
                  paintOrder="stroke"
                  textAnchor="middle"
                  fontWeight={600}
                >
                  {point.region}
                </text>
                <text
                  x={cx}
                  y={cy + 3.5}
                  fontSize={9}
                  fill={index >= 3 ? "#ffffff" : "#16181a"}
                  textAnchor="middle"
                  fontVariant="tabular-nums"
                >
                  {value === null ? "—" : count(value)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="text-[0.76rem] font-semibold text-ink-soft">
          Non-susceptible
        </span>
        {RAMP.map((colour, index) => (
          <span key={colour} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-3 w-3 rounded-sm border border-black/20"
              style={{ background: colour }}
            />
            <span className="text-[0.76rem] text-ink-soft">
              {BAND_LABELS[index]}
            </span>
          </span>
        ))}
      </div>


    </figure>
  );
}

export function regionTooltip(point: RegionPoint): string {
  return `${point.region}: ${count(point.isolates)} isolates, ${percent(
    point.percentNonSusceptible,
  )} non-susceptible`;
}
