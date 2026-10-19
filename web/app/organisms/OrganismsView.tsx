"use client";

import { useState } from "react";
import { BarChart } from "@/components/Charts";
import { Column, DataTable } from "@/components/DataTable";
import {
  Caption,
  Empty,
  Note,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import { Segmented } from "@/components/Segmented";
import type { OrganismData } from "@/lib/data";
import { count, numeric, percent, titleCase } from "@/lib/format";

type OrganismRow = { organism: string; isolates: number | string | null; percent: number | null };
type SpecimenRow = { specimenType: string; isolates: number | string | null };

/**
 * The organisms section.
 *
 * Counts, not rates, which is why this page offers an "all sectors" view where
 * the resistance page does not: an animal isolate plus a human isolate is two
 * isolates, whereas their susceptibility percentages do not average into
 * anything.
 *
 * The counts are isolates. The page this replaced ran a value count over a
 * susceptibility table, so an organism tested against more agents outranked one
 * tested against fewer and every figure was inflated by the size of the panel.
 */
export function OrganismsView({ data }: { data: OrganismData }) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(sectors[0] ?? "all");
  const slice = data.slices.find((s) => s.sector === sector) ?? data.slices[0];

  const colours = Object.fromEntries(
    data.slices.map((s) => [s.sector, s.colour]),
  );

  if (!slice) {
    return (
      <Empty>
        No isolates have been published yet. When they are, this page will show
        which organisms are being identified and the specimens they came from.
      </Empty>
    );
  }

  const chartRows = slice.rows
    .filter((row) => numeric(row.isolates) !== null)
    .slice(0, 15)
    .map((row) => ({
      label: row.organism,
      value: row.isolates,
      colour: slice.colour,
    }));

  const organismColumns: Column<OrganismRow>[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "isolates", header: "Isolates", align: "right" },
    { key: "percent", header: "% of isolates", align: "right", format: "percent" },
  ];

  const specimenColumns: Column<SpecimenRow>[] = [
    { key: "specimenType", header: "Specimen type", format: "text" },
    { key: "isolates", header: "Isolates", align: "right" },
  ];

  return (
    <>
      <Segmented
        label="Sector"
        options={sectors}
        value={sector}
        onChange={setSector}
        colours={colours}
      />

      <StatStrip
        stats={[
          { value: count(slice.organisms), label: "Distinct organisms" },
          { value: count(slice.isolates), label: "Isolates" },
          { value: count(slice.laboratories), label: "Laboratories" },
          {
            value:
              slice.sterileSitePercent === null
                ? "—"
                : percent(slice.sterileSitePercent),
            label: "From a sterile site",
            hint: "blood, CSF and other normally sterile sites",
          },
        ]}
      />

      <Section
        title={
          sector === "all"
            ? "Most frequently isolated"
            : `Most frequently isolated — ${titleCase(sector)}`
        }
        intro="Each patient's first isolate of an organism is counted once, following CLSI M39, so repeat sampling of one patient does not weight the ranking."
      >
        <BarChart rows={chartRows} unit="Isolates" colour={slice.colour} />
      </Section>

      <Section title="Every organism">
        <DataTable
          columns={organismColumns}
          rows={slice.rows}
          searchKeys={["organism"]}
          searchLabel="Search organism"
          initialSort={{ key: "isolates", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.suppression} />
      </Section>

      <Section
        title="Specimen types behind these isolates"
        intro="What the isolate was grown from changes what it means."
      >
        <DataTable
          columns={specimenColumns}
          rows={slice.specimenTypes}
          searchKeys={["specimenType"]}
          searchLabel="Search specimen type"
          initialSort={{ key: "isolates", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.specimenTypeSuppression} />
        {slice.sterileSitePercent !== null ? (
          <Caption>
            {percent(slice.sterileSitePercent)} of these isolates came from a
            normally sterile site. That share matters when reading any
            resistance figure: an isolate from blood or cerebrospinal fluid is
            almost certainly causing disease, while one from a wound swab may be
            colonising it.
          </Caption>
        ) : null}
      </Section>

      <Note>
        <strong>Method.</strong> {data.deduplication} Counts are isolates, not
        susceptibility results, so an organism tested against more agents does
        not outrank one tested against fewer.
      </Note>
    </>
  );
}
