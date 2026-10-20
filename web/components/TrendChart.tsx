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

/** Round an axis top up to something a reader can divide by four. */
function niceCeiling(value: number): number {
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  for (const step of [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10]) {
    if (value <= step * magnitude) return step * magnitude;
  }
  return 10 * magnitude;
}

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
  /** Drawn as a broken line. Used for a projection, so a reader cannot take
   *  it for something that was measured. */
  dashed?: boolean;
}

export function TrendChart({
  series,
  unit,
  denominatorLabel = "tested",
  height = 235,
  axisMax,
  xLabel = "Period",
  yLabel,
}: {
  series: TrendSeries[];
  unit: string;
  denominatorLabel?: string;
  height?: number;
  /** The top of the y axis. Omitted means 100, for a percentage. `null`
   *  scales to the data, which is what a consumption rate needs — DDD per
   *  1,000 patient-days is not bounded at a hundred. */
  axisMax?: number | null;
  /** Drawn under the period labels and rotated down the left edge. */
  xLabel?: string;
  yLabel?: string;
}) {
  // A percentage axis prints a percentage; anything else prints a number.
  // Appending % to a consumption rate turned 100.2 mg/kg into "100.2%".
  const isPercentage = axisMax === undefined;
  const titleId = useId();
  const [active, setActive] = useState<string | null>(null);

  const periods = Array.from(
    new Set(series.flatMap((s) => s.points.map((p) => p.period))),
  ).sort();
  if (!periods.length) return null;

  const observed = series.flatMap((s) =>
    s.points
      .map((p) => Math.max(p.value ?? 0, p.high ?? 0))
      .filter((v) => Number.isFinite(v)),
  );
  const top =
    axisMax === undefined
      ? 100
      : axisMax === null
        ? niceCeiling(Math.max(1, ...observed))
        : axisMax;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);

  // Whether any series carries bounds at all. Consumption rates do not, and a
  // caption describing a band nobody drew is just noise.
  const hasBands = series.some((s) =>
    s.points.some((p) => p.low !== null && p.high !== null),
  );

  const width = 720;
  // Wider left gutter when a rotated axis label has to sit outside the ticks.
  const left = yLabel ? 58 : 42;
  const right = 14;
  const topPad = 10;
  const bottom = xLabel ? 50 : 34;
  const plotWidth = width - left - right;
  const plotHeight = height - topPad - bottom;

  const x = (period: string) => {
    const index = periods.indexOf(period);
    if (periods.length === 1) return left + plotWidth / 2;
    return left + (index / (periods.length - 1)) * plotWidth;
  };
  const y = (value: number) => topPad + (1 - value / top) * plotHeight;

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

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={left}
              x2={width - right}
              y1={y(tick)}
              y2={y(tick)}
              stroke={tick === 0 ? AXIS : GRID}
              strokeWidth={1}
            />
            <text
              x={left - 7}
              y={y(tick) + 3.5}
              fontSize={9.5}
              fill={LABEL}
              textAnchor="end"
            >
              {top > 1000 ? Math.round(tick).toLocaleString("en-GB") : Number(tick.toFixed(top < 10 ? 1 : 0))}
            </text>
          </g>
        ))}

        {yLabel ? (
          <text
            x={14}
            y={topPad + plotHeight / 2}
            fontSize={10}
            fontWeight={700}
            fill={LABEL}
            textAnchor="middle"
            transform={`rotate(-90 14 ${topPad + plotHeight / 2})`}
          >
            {yLabel}
          </text>
        ) : null}
        {xLabel ? (
          <text
            x={left + plotWidth / 2}
            y={height - 6}
            fontSize={10}
            fontWeight={700}
            fill={LABEL}
            textAnchor="middle"
          >
            {xLabel}
          </text>
        ) : null}

        {periods.map((period, index) =>
          index % labelEvery === 0 ? (
            <text
              key={period}
              x={x(period)}
              y={height - (xLabel ? 26 : 12)}
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
                  strokeDasharray={line.dashed ? "5 4" : undefined}
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
                  style={
                    line.dashed
                      ? {
                          backgroundImage:
                            `repeating-linear-gradient(to right, ${line.colour} 0 4px, transparent 4px 7px)`,
                        }
                      : { background: line.colour }
                  }
                />
                <span className="text-ink">{line.label}</span>
                {last ? (
                  <span className="tabular-nums text-ink-faint">
                    {isPercentage
                      ? percent(last.value)
                      : (last.value ?? 0).toLocaleString("en-GB", {
                          maximumFractionDigits: 1,
                        })}{" "}
                    ({count(last.denominator)} {denominatorLabel})
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>

      {hasBands ? (
        <figcaption className="mt-1.5 text-[0.74rem] text-ink-faint">
          Shaded band: 95% confidence interval. Overlapping bands mean the
          change is within the uncertainty.
        </figcaption>
      ) : null}
    </figure>
  );
}
