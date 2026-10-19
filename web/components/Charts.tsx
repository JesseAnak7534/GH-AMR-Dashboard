"use client";

import { useId, useState } from "react";
import { count, interval, isWithheld, numeric, percent } from "@/lib/format";

/**
 * Charts, written as SVG rather than pulled from a charting library.
 *
 * Three reasons, in order of weight.
 *
 * A confidence interval has to be drawable. Most chart libraries treat error
 * bars as an afterthought, and on this site the interval is not decoration: a
 * susceptibility of 92% from 31 isolates and one from 900 are different claims,
 * and if the interval is hard to draw it ends up in a footnote nobody reads.
 *
 * A withheld value is not zero. A library plots a missing number as a gap at
 * the baseline, which reads as "none found". These charts omit the bar and say
 * so in the row instead.
 *
 * And the house style is thin rules and muted gridlines, which is easier to
 * write than to override.
 *
 * Every chart is also a table of the same numbers immediately below or beside
 * it, so nothing depends on seeing the picture -- or on seeing colour.
 */

const AXIS = "#c9ced1";
const GRID = "#eceff0";
const LABEL = "#6b7378";

function ticks(max: number, step: number): number[] {
  const out: number[] = [];
  for (let value = 0; value <= max + 0.001; value += step) out.push(value);
  return out;
}

// ---------------------------------------------------------------------------
// Horizontal bars
// ---------------------------------------------------------------------------

export interface BarRow {
  label: string;
  value: number | string | null;
  colour?: string;
  note?: string;
}

export function BarChart({
  rows,
  unit,
  labelWidth = 190,
  colour = "#0072b2",
}: {
  rows: BarRow[];
  unit: string;
  labelWidth?: number;
  colour?: string;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const titleId = useId();

  const drawable = rows.filter((row) => numeric(row.value) !== null);
  const max = Math.max(1, ...drawable.map((row) => numeric(row.value) as number));
  const rowHeight = 26;
  const chartWidth = 560;
  const barArea = chartWidth - labelWidth - 72;
  const height = rows.length * rowHeight + 26;
  const scale = (value: number) => (value / max) * barArea;

  const step = Math.pow(10, Math.floor(Math.log10(max))) * (max / Math.pow(10, Math.floor(Math.log10(max))) > 5 ? 2 : 1);

  return (
    <figure className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${chartWidth} ${height}`}
        className="h-auto w-full min-w-[460px]"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>{`${rows.length} values, in ${unit}`}</title>

        {ticks(max, step).map((tick) => (
          <g key={tick}>
            <line
              x1={labelWidth + scale(tick)}
              x2={labelWidth + scale(tick)}
              y1={0}
              y2={height - 22}
              stroke={GRID}
              strokeWidth={1}
            />
            <text
              x={labelWidth + scale(tick)}
              y={height - 8}
              fontSize={9.5}
              fill={LABEL}
              textAnchor="middle"
            >
              {tick.toLocaleString("en-GB")}
            </text>
          </g>
        ))}

        {rows.map((row, index) => {
          const value = numeric(row.value);
          const y = index * rowHeight + 4;
          const fill = row.colour ?? colour;
          const faded = hovered !== null && hovered !== index;
          return (
            <g
              key={`${row.label}-${index}`}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
              opacity={faded ? 0.45 : 1}
            >
              <text
                x={labelWidth - 8}
                y={y + 13}
                fontSize={11}
                fill="#16181a"
                textAnchor="end"
              >
                {row.label.length > 30 ? `${row.label.slice(0, 29)}…` : row.label}
              </text>
              {value === null ? (
                <text
                  x={labelWidth + 6}
                  y={y + 13}
                  fontSize={10}
                  fill={LABEL}
                  fontStyle="italic"
                >
                  {isWithheld(row.value) ? "withheld" : "not reported"}
                </text>
              ) : (
                <>
                  <rect
                    x={labelWidth}
                    y={y + 3}
                    width={Math.max(1, scale(value))}
                    height={rowHeight - 12}
                    fill={fill}
                    rx={1.5}
                  />
                  <text
                    x={labelWidth + scale(value) + 6}
                    y={y + 13}
                    fontSize={10.5}
                    fill="#4a5156"
                    fontVariant="tabular-nums"
                  >
                    {count(value)}
                  </text>
                </>
              )}
            </g>
          );
        })}

        <line
          x1={labelWidth}
          x2={labelWidth}
          y1={0}
          y2={height - 22}
          stroke={AXIS}
          strokeWidth={1}
        />
      </svg>
      <figcaption className="mt-1 text-[0.74rem] text-ink-faint">{unit}</figcaption>
    </figure>
  );
}

// ---------------------------------------------------------------------------
// Point with confidence interval
// ---------------------------------------------------------------------------

export interface IntervalRow {
  label: string;
  value: number | null;
  low: number | null;
  high: number | null;
  denominator: number | string | null;
  denominatorLabel?: string;
}

/**
 * A percentage with its interval, on a fixed 0–100 axis.
 *
 * The axis does not rescale to the data. A chart whose x-axis runs from 70 to
 * 95 makes a five-point difference look like a collapse, and this is a chart
 * people will quote.
 */
export function IntervalChart({
  rows,
  unit = "% susceptible",
  labelWidth = 230,
  colour = "#0072b2",
}: {
  rows: IntervalRow[];
  unit?: string;
  labelWidth?: number;
  colour?: string;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const titleId = useId();

  const rowHeight = 24;
  const chartWidth = 620;
  const plot = chartWidth - labelWidth - 58;
  const height = rows.length * rowHeight + 28;
  const x = (value: number) => labelWidth + (value / 100) * plot;

  return (
    <figure className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${chartWidth} ${height}`}
        className="h-auto w-full min-w-[520px]"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>{`${rows.length} values, ${unit}, with 95% confidence intervals`}</title>

        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line
              x1={x(tick)}
              x2={x(tick)}
              y1={0}
              y2={height - 24}
              stroke={tick === 0 ? AXIS : GRID}
              strokeWidth={1}
            />
            <text
              x={x(tick)}
              y={height - 9}
              fontSize={9.5}
              fill={LABEL}
              textAnchor="middle"
            >
              {tick}
            </text>
          </g>
        ))}

        {rows.map((row, index) => {
          const y = index * rowHeight + 13;
          const faded = hovered !== null && hovered !== index;
          const hasValue = row.value !== null && Number.isFinite(row.value);
          return (
            <g
              key={`${row.label}-${index}`}
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
              opacity={faded ? 0.4 : 1}
            >
              <text
                x={labelWidth - 8}
                y={y + 3.5}
                fontSize={10.5}
                fill="#16181a"
                textAnchor="end"
              >
                {row.label.length > 38 ? `${row.label.slice(0, 37)}…` : row.label}
              </text>

              {hasValue ? (
                <>
                  {row.low !== null && row.high !== null ? (
                    <>
                      <line
                        x1={x(row.low)}
                        x2={x(row.high)}
                        y1={y}
                        y2={y}
                        stroke={colour}
                        strokeWidth={1.4}
                        opacity={0.55}
                      />
                      <line
                        x1={x(row.low)}
                        x2={x(row.low)}
                        y1={y - 3.5}
                        y2={y + 3.5}
                        stroke={colour}
                        strokeWidth={1.4}
                        opacity={0.55}
                      />
                      <line
                        x1={x(row.high)}
                        x2={x(row.high)}
                        y1={y - 3.5}
                        y2={y + 3.5}
                        stroke={colour}
                        strokeWidth={1.4}
                        opacity={0.55}
                      />
                    </>
                  ) : null}
                  <circle cx={x(row.value as number)} cy={y} r={4} fill={colour} />
                  {hovered === index ? (
                    <text
                      x={x(100) + 6}
                      y={y + 3.5}
                      fontSize={10}
                      fill="#4a5156"
                    >
                      {percent(row.value)} ({interval(row.low, row.high)}),{" "}
                      {count(row.denominator)} {row.denominatorLabel ?? "tested"}
                    </text>
                  ) : (
                    <text
                      x={x(100) + 6}
                      y={y + 3.5}
                      fontSize={10}
                      fill={LABEL}
                      fontVariant="tabular-nums"
                    >
                      {percent(row.value)}
                    </text>
                  )}
                </>
              ) : (
                <text
                  x={labelWidth + 6}
                  y={y + 3.5}
                  fontSize={10}
                  fill={LABEL}
                  fontStyle="italic"
                >
                  not published — too few isolates
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1 text-[0.74rem] text-ink-faint">
        {unit}. The bar through each point is the 95% confidence interval: a long
        bar means few isolates, not a disputed figure.
      </figcaption>
    </figure>
  );
}

// ---------------------------------------------------------------------------
// Stacked proportion bar
// ---------------------------------------------------------------------------

/**
 * One bar split into named parts, for a composition that sums to a whole --
 * concordance verdicts, sector shares. Each part is labelled in the legend
 * with its own count, so the colours are a convenience rather than the key.
 */
export function ProportionBar({
  parts,
}: {
  parts: { label: string; value: number; colour: string }[];
}) {
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  if (!total) return null;
  return (
    <div className="space-y-3">
      <div className="flex h-7 w-full overflow-hidden rounded border border-rule">
        {parts.map((part) => (
          <div
            key={part.label}
            style={{
              width: `${(100 * part.value) / total}%`,
              background: part.colour,
            }}
            title={`${part.label}: ${count(part.value)}`}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-1.5">
        {parts.map((part) => (
          <li key={part.label} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: part.colour }}
            />
            <span className="text-[0.82rem] text-ink">
              {part.label}{" "}
              <span className="font-semibold tabular-nums">
                {count(part.value)}
              </span>
              <span className="text-ink-faint">
                {" "}
                ({percent((100 * part.value) / total, 0)})
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
