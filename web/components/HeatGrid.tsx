"use client";

import { useMemo, useState } from "react";
import { count, interval, isWithheld, percent } from "@/lib/format";

/**
 * The antibiogram as a matrix.
 *
 * The classic view, and the one most likely to be misread, so two rules are
 * enforced in the markup rather than in a caption.
 *
 * **Every cell prints its number.** The shade is a scan aid; the value is the
 * data. A reader who sees no colour loses speed and nothing else.
 *
 * **A blank cell is never ambiguous.** Three states are kept visibly apart: a
 * published percentage, a pair tested but below the reporting floor, and a
 * pair never tested. Collapsing the last two would let a laboratory that does
 * not test an agent look like one whose isolates are susceptible to it.
 */

/** Susceptibility, low to high. Not red-to-green: that pair is the one that
 *  disappears under deuteranopia, and this is the platform's most
 *  consequential distinction. */
const RAMP = ["#8c2d04", "#cc4c02", "#ec7014", "#fe9929", "#a6bddb", "#3690c0", "#0570b0"];

function shade(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  if (value < 20) return RAMP[0];
  if (value < 35) return RAMP[1];
  if (value < 50) return RAMP[2];
  if (value < 65) return RAMP[3];
  if (value < 80) return RAMP[4];
  if (value < 90) return RAMP[5];
  return RAMP[6];
}

export interface HeatCell {
  organism: string;
  antibiotic: string;
  percent: number | null;
  tested: number | string | null;
  low: number | null;
  high: number | null;
}

export function HeatGrid({
  cells,
  highlightOrganisms,
}: {
  cells: HeatCell[];
  /** Organisms on a priority list, marked rather than filtered. */
  highlightOrganisms?: Set<string>;
}) {
  const [focus, setFocus] = useState<HeatCell | null>(null);

  const { organisms, antibiotics, index } = useMemo(() => {
    const byOrganism = new Map<string, number>();
    const byAntibiotic = new Map<string, number>();
    const index = new Map<string, HeatCell>();
    for (const cell of cells) {
      index.set(`${cell.organism}||${cell.antibiotic}`, cell);
      byOrganism.set(cell.organism, (byOrganism.get(cell.organism) ?? 0) + 1);
      byAntibiotic.set(
        cell.antibiotic,
        (byAntibiotic.get(cell.antibiotic) ?? 0) + 1,
      );
    }
    return {
      organisms: [...byOrganism.keys()].sort(),
      antibiotics: [...byAntibiotic.keys()].sort(),
      index,
    };
  }, [cells]);

  if (!organisms.length) return null;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-rule">
        <table className="w-full border-collapse text-[0.76rem]">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-paper px-2 py-2 text-left font-semibold">
                Organism
              </th>
              {antibiotics.map((antibiotic) => (
                <th
                  key={antibiotic}
                  className="px-1 py-2 align-bottom font-medium text-ink-faint"
                  style={{ minWidth: 42 }}
                >
                  <span
                    className="block whitespace-nowrap"
                    style={{
                      writingMode: "vertical-rl",
                      transform: "rotate(180deg)",
                    }}
                  >
                    {antibiotic}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {organisms.map((organism) => (
              <tr key={organism}>
                <th className="sticky left-0 z-10 whitespace-nowrap bg-paper px-2 py-1 text-left font-medium">
                  {organism}
                  {highlightOrganisms?.has(organism) ? (
                    <span
                      className="ml-1.5 rounded bg-brand px-1 py-0.5 text-[0.58rem] font-bold tracking-wide text-white"
                      title="On a priority pathogen list"
                    >
                      PRIORITY
                    </span>
                  ) : null}
                </th>
                {antibiotics.map((antibiotic) => {
                  const cell = index.get(`${organism}||${antibiotic}`);
                  const colour = shade(cell?.percent ?? null);
                  const tested = cell?.tested;
                  const label = !cell
                    ? "not tested"
                    : isWithheld(tested)
                      ? "withheld"
                      : cell.percent === null
                        ? "too few"
                        : percent(cell.percent, 0);
                  return (
                    <td
                      key={antibiotic}
                      onMouseEnter={() => cell && setFocus(cell)}
                      onMouseLeave={() => setFocus(null)}
                      title={
                        cell
                          ? `${organism} / ${antibiotic}: ${label}`
                          : `${organism} / ${antibiotic}: not tested`
                      }
                      className="border border-rule px-1 py-1 text-center tabular-nums"
                      style={{
                        background: colour ?? (cell ? "#f1f3f4" : "#ffffff"),
                        color:
                          colour && cell && (cell.percent ?? 100) < 65
                            ? "#ffffff"
                            : "#16181a",
                      }}
                    >
                      {!cell ? (
                        <span className="text-ink-faint">·</span>
                      ) : cell.percent === null ? (
                        <span className="text-[0.62rem] italic text-ink-faint">
                          {isWithheld(tested) ? "wh" : "<30"}
                        </span>
                      ) : (
                        Math.round(cell.percent)
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[0.74rem] text-ink-soft">
        <span className="font-semibold">% susceptible</span>
        {[
          ["<20", RAMP[0]],
          ["20–35", RAMP[1]],
          ["35–50", RAMP[2]],
          ["50–65", RAMP[3]],
          ["65–80", RAMP[4]],
          ["80–90", RAMP[5]],
          ["90+", RAMP[6]],
        ].map(([label, colour]) => (
          <span key={label} className="flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block h-3 w-3 rounded-sm border border-black/15"
              style={{ background: colour }}
            />
            {label}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-sm border border-black/15 bg-[#f1f3f4]"
          />
          tested, under 30 isolates
        </span>
        <span className="flex items-center gap-1">
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-sm border border-rule bg-white"
          />
          not tested
        </span>
      </div>

      <p className="min-h-[1.2rem] text-[0.8rem] text-ink-soft">
        {focus ? (
          <>
            <strong>
              {focus.organism} / {focus.antibiotic}
            </strong>{" "}
            — {percent(focus.percent)} susceptible ({interval(focus.low, focus.high)}
            ), {count(focus.tested)} isolates tested.
          </>
        ) : (
          "Hover a cell for its denominator and interval."
        )}
      </p>
    </div>
  );
}
