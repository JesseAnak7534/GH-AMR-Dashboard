"use client";

import { useId, useState } from "react";
import { count, percent } from "@/lib/format";

/**
 * A time series with its confidence band.
 *
 * The band is the point. A line joining four quarterly points looks like a
 * trend whether or not the movement exceeds the uncertainty in each point, and
 * reading a rise into overlapping intervals is the most common way a
 * surveillance chart misleads. So the interval is drawn as a shaded band
 * behind the line rather than offered as a tooltip.
 *
 * A period with too few observations is not plotted at all, and the line
 * breaks there rather than bridging the gap — a bridged gap asserts a value
 * that was never measured.
 */

const AXIS = "#c9ced1";
const GRID = "#eceff0";
const LABEL = "#6b7378";

export interface TrendPoint {
  period: string;
  value: number | null;
  low: number | null;
  high: number | null;
  denominator: number | string | null;
}

export interface TrendSeries {
  label: string;
  colour: string;
  points: TrendPoint[];
}

export function TrendChart({
  series,
  unit,
  denominatorLabel = "tested",
  height = 290,
}: {
  series: TrendSeries[];
  unit: string;
  denominatorLabel?: string;
  height?: number;
}) {
  const titleId = useId();
  const [active, setActive] = useState<string | null>(null);

  const periods = Array.from(
    new Set(series.flatMap((s) => s.points.map((p) => p.period))),
  ).sort();
  if (!periods.length) return null;

  const width = 720;
  const left = 42;
  const right = 14;
  const top = 10;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const x = (period: string) => {
    const index = periods.indexOf(period);
    if (periods.length === 1) return left + plotWidth / 2;
    return left + (index / (periods.length - 1)) * plotWidth;
  };
  const y = (value: number) => top + (1 - value / 100) * plotHeight;

  // One label in four when the series is long, so the axis does not turn into
  // a smear of overlapping text.
  const labelEvery = Math.max(1, Math.ceil(periods.length / 8));

  return (
    <figure className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full min-w-[520px]"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          {`${series.length} series over ${periods.length} periods, ${unit}`}
        </title>

        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line
              x1={left}
              x2={width - right}
              y1={y(tick)}
              y2={y(tick)}
              stroke={tick === 0 ? AXIS : GRID}
              strokeWidth={1}
            />
            <text x={left - 7} y={y(tick) + 3.5} fontSize={9.5} fill={LABEL} textAnchor="end">
              {tick}
            </text>
          </g>
        ))}

        {periods.map((period, index) =>
          index % labelEvery === 0 ? (
            <text
              key={period}
              x={x(period)}
              y={height - 12}
              fontSize={9.5}
              fill={LABEL}
              textAnchor="middle"
            >
              {period}
            </text>
          ) : null,
        )}

        {series.map((line) => {
          const faded = active !== null && active !== line.label;
          const drawable = line.points.filter(
            (p) => p.value !== null && Number.isFinite(p.value),
          );
          if (!drawable.length) return null;

          // Bands are drawn for one or two series. Beyond that they overlap
          // into a wash that hides the very lines they belong to, so the band
          // appears only for the series the reader is pointing at -- which is
          // also the only one they are reading an interval off.
          const showBand = series.length <= 2 || active === line.label;

          // The band, where both bounds exist.
          const banded = showBand
            ? drawable.filter((p) => p.low !== null && p.high !== null)
            : [];
          const bandPath =
            banded.length > 1
              ? `M ${banded.map((p) => `${x(p.period)},${y(p.high as number)}`).join(" L ")} L ${[...banded]
                  .reverse()
                  .map((p) => `${x(p.period)},${y(p.low as number)}`)
                  .join(" L ")} Z`
              : null;

          // Segments, broken wherever a period was not plotted.
          const segments: TrendPoint[][] = [];
          let current: TrendPoint[] = [];
          for (const period of periods) {
            const point = line.points.find((p) => p.period === period);
            if (point && point.value !== null && Number.isFinite(point.value)) {
              current.push(point);
            } else if (current.length) {
              segments.push(current);
              current = [];
            }
          }
          if (current.length) segments.push(current);

          return (
            <g
              key={line.label}
              opacity={faded ? 0.18 : 1}
              onMouseEnter={() => setActive(line.label)}
              onMouseLeave={() => setActive(null)}
            >
              {bandPath ? (
                <path
                  d={bandPath}
                  fill={line.colour}
                  opacity={series.length <= 2 ? 0.13 : 0.22}
                />
              ) : null}
              {segments.map((segment, index) => (
                <polyline
                  key={index}
                  points={segment
                    .map((p) => `${x(p.period)},${y(p.value as number)}`)
                    .join(" ")}
                  fill="none"
                  stroke={line.colour}
                  strokeWidth={2}
                  strokeLinejoin="round"
                />
              ))}
              {drawable.map((point) => (
                <circle
                  key={point.period}
                  cx={x(point.period)}
                  cy={y(point.value as number)}
                  r={3}
                  fill={line.colour}
                />
              ))}
            </g>
          );
        })}
      </svg>

      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5">
        {series.map((line) => {
          const last = [...line.points]
            .reverse()
            .find((p) => p.value !== null);
          return (
            <li key={line.label}>
              <button
                type="button"
                onMouseEnter={() => setActive(line.label)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(line.label)}
                onBlur={() => setActive(null)}
                className="flex items-center gap-1.5 text-[0.8rem]"
              >
                <span
                  aria-hidden="true"
                  className="inline-block h-0.5 w-4"
                  style={{ background: line.colour }}
                />
                <span className="text-ink">{line.label}</span>
                {last ? (
                  <span className="tabular-nums text-ink-faint">
                    {percent(last.value)} ({count(last.denominator)}{" "}
                    {denominatorLabel})
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>

      <figcaption className="mt-1.5 text-[0.74rem] text-ink-faint">
        {unit}. {series.length > 2
          ? "Point at a series to see its 95% confidence interval."
          : "The band is the 95% confidence interval."}{" "}
        Where intervals overlap between periods, the change is within the
        uncertainty. The line breaks where a period had too few results.
      </figcaption>
    </figure>
  );
}
