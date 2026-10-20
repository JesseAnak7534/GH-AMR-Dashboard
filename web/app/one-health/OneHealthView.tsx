"use client";

import { Figure } from "@/components/Figure";
import { useMemo, useState } from "react";
import { BarChart, StackedBars } from "@/components/Charts";
import { FilterBar, ThresholdControl } from "@/components/FilterBar";
import {
  Caption,
  Empty,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import type { OneHealthData } from "@/lib/data";
import { count, isWithheld, titleCase } from "@/lib/format";

/**
 * The One Health section.
 *
 * The one page where the platform's refusal to pool sectors is the subject
 * rather than a caveat. Each sector is counted on its own and compared side by
 * side; nothing here divides a numerator by a denominator that mixes them.
 *
 * The organism-by-sector grid has to keep three states apart, which is why it
 * is built as a table of text rather than a numeric matrix: a count, "withheld"
 * where the count was too small to publish, and "none found" where the organism
 * genuinely did not appear in that sector. Collapsing the last two is exactly
 * the error the suppression exists to prevent.
 */
export function OneHealthView({ data }: { data: OneHealthData }) {
  const [minIsolates, setMinIsolates] = useState(0);
  const [onlyShared, setOnlyShared] = useState("all");

  const sectorRows = data.sectors.map((row) => ({
    label: titleCase(row.sector),
    value: row.isolates,
    colour: row.colour,
  }));

  const grid = useMemo(() => {
    const sectors = data.sectorsPresent;
    const byOrganism = new Map<string, Map<string, number | string | null>>();
    for (const row of data.sharedOrganisms) {
      if (!byOrganism.has(row.organism)) byOrganism.set(row.organism, new Map());
      byOrganism.get(row.organism)!.set(row.sector, row.isolates);
    }
    // Ordered by published isolates. A withheld cell contributes nothing to
    // the ordering, which is the right behaviour: it is an unknown quantity,
    // not a zero, and guessing at it to sort by would be inventing a number.
    const total = (name: string) =>
      [...(byOrganism.get(name)?.values() ?? [])].reduce(
        (sum: number, value) => sum + (typeof value === "number" ? value : 0),
        0,
      );
    const organisms = [...byOrganism.keys()]
      .filter((name) => {
        const row = byOrganism.get(name);
        if (!row) return false;
        const counted = [...row.values()].filter(
          (value) => typeof value === "number" && value >= minIsolates,
        );
        if (minIsolates > 0 && counted.length === 0) return false;
        return onlyShared === "three" ? row.size >= 3 : true;
      })
      .sort((a, b) => total(b) - total(a));
    return { sectors, organisms, byOrganism };
  }, [data, minIsolates, onlyShared]);

  if (!data.sectors.length) {
    return (
      <Empty>
        No isolates have been published yet. When they are, this page will
        compare the sectors side by side.
      </Empty>
    );
  }

  return (
    <>
      <FilterBar
        controls={[
          {
            key: "shared",
            label: "Organisms shown",
            value: onlyShared,
            options: [
              { value: "all", label: "Found in more than one sector" },
              { value: "three", label: "Found in three or more sectors" },
            ],
            note: "Shared presence is a reason to look, not evidence of transmission.",
            onChange: setOnlyShared,
          },
        ]}
        canReset={onlyShared !== "all" || minIsolates > 0}
        onReset={() => {
          setOnlyShared("all");
          setMinIsolates(0);
        }}
      />

      <div className="flex flex-wrap gap-x-5 gap-y-3">
        <ThresholdControl
          label="Minimum isolates per cell"
          value={minIsolates}
          min={0}
          max={200}
          step={5}
          onChange={setMinIsolates}
          note="Hides published cells resting on fewer."
        />
      </div>

      <StatStrip
        stats={[
          {
            value: count(data.sectorsPresent.length),
            label: "Sectors",
            href: "#by-sector",
          },
          {
            value: count(data.isolates),
            label: "Isolates",
            href: "/resistance",
          },
          {
            value: count(data.organismsTotal),
            label: "Organisms",
            href: "/organisms",
          },
          {
            value: count(data.organismsShared),
            label: "In more than one sector",
            hint: "a reason to look, not evidence of transmission",
            href: "#shared",
          },
        ]}
      />

      <Section id="by-sector" title="Isolates by sector">
        <Figure
          title="Isolates by sector"
          hideTitle
        >
          <BarChart
            rows={sectorRows}
            unit=""
            xLabel="Isolates"
            yLabel="Sector"
            labelWidth={140}
          />
        </Figure>
        <SuppressionNote suppression={data.sectorSuppression} />
      </Section>

      <Section id="shared" title="Organisms found in more than one sector">
        {grid.organisms.length > 0 ? (
          <div className="mb-5">
            <StackedBars
              rows={grid.organisms.map((organism) => ({
                label: organism,
                parts: Object.fromEntries(
                  grid.sectors.map((sector) => [
                    sector,
                    grid.byOrganism.get(organism)?.get(sector) ?? 0,
                  ]),
                ),
              }))}
              series={grid.sectors}
              colours={data.palette}
              xLabel="Share of the organism's isolates, by sector"
              yLabel="Organism"
              labelWidth={180}
            />
          </div>
        ) : null}
        {grid.organisms.length === 0 ? (
          <Empty>
            No organism in this data was isolated from more than one sector.
          </Empty>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-rule">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Organism</th>
                  {grid.sectors.map((sector) => (
                    <th key={sector} className="num">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          aria-hidden="true"
                          className="inline-block h-2 w-2 rounded-full"
                          style={{
                            background: data.palette[sector] ?? "#999999",
                          }}
                        />
                        {titleCase(sector)}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grid.organisms.map((organism) => (
                  <tr key={organism}>
                    <td className="font-medium">{organism}</td>
                    {grid.sectors.map((sector) => {
                      const value = grid.byOrganism.get(organism)?.get(sector);
                      return (
                        <td key={sector} className="num">
                          {value === undefined ? (
                            <span className="text-ink-faint">none found</span>
                          ) : isWithheld(value) ? (
                            <span className="withheld">withheld</span>
                          ) : (
                            count(value)
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <SuppressionNote suppression={data.sharedSuppression} />
      </Section>

      <Caption>
        Shared presence is a reason to look, not evidence of transmission.
      </Caption>


    </>
  );
}
