"use client";

import { useId } from "react";

/**
 * One indicator against a target, as the prescribing-quality page showed them.
 *
 * The number is the finding and is printed large; the arc exists to place it
 * against the target, which is drawn as a single tick rather than as a band of
 * red-amber-green. A traffic-light dial invites "we are in the green" when the
 * figure behind it is a point estimate from one survey day, and the colour
 * would be carrying a judgement the data cannot support.
 */
export function Gauge({
  value,
  label,
  hint,
  target = 80,
  colour = "#2ca02c",
}: {
  value: number | null;
  label: string;
  hint?: string;
  target?: number;
  colour?: string;
}) {
  const titleId = useId();
  const width = 210;
  const height = 124;
  const radius = 80;
  const cx = width / 2;
  const cy = height - 16;

  const at = (fraction: number, r = radius) => {
    const a = Math.PI * (1 - Math.max(0, Math.min(1, fraction)));
    return `${cx + r * Math.cos(a)},${cy - r * Math.sin(a)}`;
  };
  // The large-arc flag is for sweeps over 180 degrees. This is a semicircle,
  // so a sweep never reaches that and the flag is always 0; setting it on a
  // fraction above a half drew the arc the long way round the circle.
  const arc = (from: number, to: number) =>
    `M ${at(from)} A ${radius} ${radius} 0 0 1 ${at(to)}`;

  const fraction = value === null ? 0 : Math.max(0, Math.min(1, value / 100));
  const targetFraction = Math.max(0, Math.min(1, target / 100));
  const tickAngle = Math.PI * (1 - targetFraction);

  return (
    <figure className="rounded-lg border border-rule bg-paper px-4 py-3">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mx-auto h-auto w-full max-w-[230px]"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          {`${label}: ${value === null ? "not known" : `${value}%`}; target ${target}%`}
        </title>
        <path
          d={arc(0, 1)}
          stroke="#eceff0"
          strokeWidth={13}
          fill="none"
          strokeLinecap="round"
        />
        {value !== null && fraction > 0 ? (
          <path
            d={arc(0, fraction)}
            stroke={colour}
            strokeWidth={13}
            fill="none"
            strokeLinecap="round"
          />
        ) : null}
        <line
          x1={cx + (radius - 11) * Math.cos(tickAngle)}
          y1={cy - (radius - 11) * Math.sin(tickAngle)}
          x2={cx + (radius + 11) * Math.cos(tickAngle)}
          y2={cy - (radius + 11) * Math.sin(tickAngle)}
          stroke="#16181a"
          strokeWidth={2}
        />
        <text
          x={cx}
          y={cy - 16}
          textAnchor="middle"
          fontSize={29}
          fontWeight={700}
          fill="#16181a"
        >
          {value === null ? "—" : `${value.toFixed(1)}%`}
        </text>
        <text x={14} y={cy + 11} fontSize={9.5} fill="#6b7378">
          0
        </text>
        <text
          x={width - 14}
          y={cy + 11}
          fontSize={9.5}
          fill="#6b7378"
          textAnchor="end"
        >
          100
        </text>
      </svg>
      <figcaption className="mt-1 text-center">
        <span className="block text-[0.88rem] font-semibold">{label}</span>
        <span className="block text-[0.74rem] text-ink-faint">
          {hint ? `${hint} · ` : ""}target {target}%
        </span>
      </figcaption>
    </figure>
  );
}
