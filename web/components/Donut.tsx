"use client";

import { useId, useState } from "react";
import { count, percent } from "@/lib/format";
import { ramp } from "@/lib/palette";

/**
 * A ring for a composition of a few parts — route of administration, purpose
 * of use, sector share. The old consumption and prescribing pages used these
 * and they read well for three or four categories.
 *
 * Only for small sets. Past about six slices an eye cannot rank arcs and a bar
 * chart answers the same question better, so the component keeps the six
 * largest and groups the rest rather than drawing something unreadable. Every
 * slice is named in the legend with its count and share, so nothing depends on
 * telling two colours apart.
 */
export function Donut({
  parts,
  colours,
  size = 180,
  centreLabel,
  centreValue,
}: {
  parts: { label: string; value: number }[];
  colours?: string[];
  size?: number;
  centreLabel?: string;
  centreValue?: string;
}) {
  const [active, setActive] = useState<string | null>(null);
  const titleId = useId();

  const sorted = [...parts]
    .filter((part) => part.value > 0)
    .sort((a, b) => b.value - a.value);
  const head = sorted.slice(0, 6);
  const tail = sorted.slice(6);
  const shown =
    tail.length > 0
      ? [
          ...head,
          {
            label: `Other (${tail.length})`,
            value: tail.reduce((sum, part) => sum + part.value, 0),
          },
        ]
      : head;

  const total = shown.reduce((sum, part) => sum + part.value, 0);
  if (!total) return null;

  const palette = colours ?? ramp(shown.length);
  const radius = size / 2;
  const inner = radius - size * 0.22;

  let angle = -Math.PI / 2;
  const arcs = shown.map((part, index) => {
    const sweep = (part.value / total) * Math.PI * 2;
    const start = angle;
    const end = angle + sweep - 0.004; // a hairline between slices
    angle += sweep;
    const large = sweep > Math.PI ? 1 : 0;
    const at = (r: number, a: number) =>
      `${radius + r * Math.cos(a)},${radius + r * Math.sin(a)}`;
    return {
      ...part,
      colour: palette[index % palette.length],
      d:
        `M ${at(radius, start)} A ${radius} ${radius} 0 ${large} 1 ${at(radius, end)} ` +
        `L ${at(inner, end)} A ${inner} ${inner} 0 ${large} 0 ${at(inner, start)} Z`,
    };
  });

  return (
    <figure className="flex flex-wrap items-center gap-5">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
        role="img"
        aria-labelledby={titleId}
        className="shrink-0"
      >
        <title id={titleId}>{`${shown.length} parts of ${count(total)}`}</title>
        {arcs.map((arc) => (
          <path
            key={arc.label}
            d={arc.d}
            fill={arc.colour}
            opacity={active === null || active === arc.label ? 1 : 0.35}
            onMouseEnter={() => setActive(arc.label)}
            onMouseLeave={() => setActive(null)}
          >
            <title>{`${arc.label}: ${count(arc.value)}`}</title>
          </path>
        ))}
        {centreValue ? (
          <>
            <text
              x={radius}
              y={radius}
              textAnchor="middle"
              fontSize={size * 0.16}
              fontWeight={700}
              fill="#16181a"
            >
              {centreValue}
            </text>
            <text
              x={radius}
              y={radius + size * 0.115}
              textAnchor="middle"
              fontSize={size * 0.075}
              fill="#6b7378"
            >
              {centreLabel ?? ""}
            </text>
          </>
        ) : null}
      </svg>

      <ul className="min-w-[170px] flex-1 space-y-1">
        {arcs.map((arc) => (
          <li key={arc.label}>
            <button
              type="button"
              onMouseEnter={() => setActive(arc.label)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(arc.label)}
              onBlur={() => setActive(null)}
              className="flex w-full items-center gap-2 text-left text-[0.82rem]"
            >
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ background: arc.colour }}
              />
              <span className="flex-1 text-ink">{arc.label}</span>
              <span className="tabular-nums text-ink-soft">
                {count(arc.value >= 100 ? Math.round(arc.value) : arc.value)}
              </span>
              <span className="w-11 text-right tabular-nums text-ink-faint">
                {percent((100 * arc.value) / total, 0)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </figure>
  );
}
