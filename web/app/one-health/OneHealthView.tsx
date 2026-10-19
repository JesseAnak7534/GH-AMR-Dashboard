"use client";

import { useMemo } from "react";
import { BarChart } from "@/components/Charts";
import {
  Caption,
  Empty,
  Note,
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
    const organisms = [...byOrganism.keys()].sort(
      (a, b) => total(b) - total(a),
    );
    return { sectors, organisms, byOrganism };
  }, [data]);

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
      <Note>
        Nothing on this page pools sectors into a single national percentage. A
        rate mixing hospital isolates with river water describes neither, and
        the platform refuses to compute one: each sector is counted on its own
        and compared side by side.
      </Note>

      <StatStrip
        stats={[
          { value: count(data.sectorsPresent.length), label: "Sectors" },
          { value: count(data.isolates), label: "Isolates" },
          { value: count(data.organismsTotal), label: "Organisms" },
          {
            value: count(data.organismsShared),
            label: "In more than one sector",
            hint: "a reason to look, not evidence of transmission",
          },
        ]}
      />

      <Section
        title="Isolates by sector"
        intro="Counted separately. The colours are fixed across every page on this site, so a sector keeps the same colour wherever it appears."
      >
        <BarChart rows={sectorRows} unit="Isolates" labelWidth={140} />
        <SuppressionNote suppression={data.sectorSuppression} />
      </Section>

      <Section
        title="Organisms found in more than one sector"
        intro="An organism appearing in people, animals and food is not evidence that it moved between them — that needs sequencing, and the genomics section is where it is attempted. It is the reason to look."
      >
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
        <Caption>
          Three states, kept apart deliberately. A count is a count.
          &ldquo;Withheld&rdquo; means the organism was found in that sector but
          by too few isolates to publish. &ldquo;None found&rdquo; means it was
          not isolated there at all. Reading the second as the third is the
          error this site works hardest to avoid.
        </Caption>
        <SuppressionNote suppression={data.sharedSuppression} />
      </Section>

      <Note tone="limit">
        <strong>What this cannot show.</strong> Shared presence is not shared
        transmission. Two sectors can carry the same species for entirely
        separate reasons, and establishing a link needs related genomes, dated
        sampling and a plausible route. The genomics section reports cluster
        membership where sequencing supports it, and says what that does and
        does not mean.
      </Note>

      <Note>
        <strong>Method.</strong> {data.deduplication} Sector counts are
        isolates. Where withholding one sector&rsquo;s count would let it be
        recovered by subtracting the others from an organism&rsquo;s total, a
        second count is withheld too.
      </Note>
    </>
  );
}
