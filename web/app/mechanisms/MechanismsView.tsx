"use client";

import { useMemo, useState } from "react";
import { BarChart } from "@/components/Charts";
import {
  Empty,
  Note,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import { Column, DataTable } from "@/components/DataTable";
import { Figure } from "@/components/Figure";
import { FilterBar, sectorOptions } from "@/components/FilterBar";
import type {
  BreadthOrganismRow,
  CrossResistanceRow,
  MechanismOrganismRow,
  MechanismsData,
  MechanismTotalRow,
  SentinelRow,
} from "@/lib/clinical";
import { count, numeric, percent, titleCase } from "@/lib/format";
import { OKABE_ITO } from "@/lib/palette";

/**
 * Mechanisms, as a surveillance page can honestly report them.
 *
 * Every figure on this page is an inference from a susceptibility pattern. A
 * confirmed ESBL is a laboratory test or a gene; what is here is an isolate
 * non-susceptible to two or more third generation cephalosporins. The basis
 * for each one is printed beside its count rather than left in a footnote,
 * because "ESBL: 90 isolates" on a chart reads as ninety confirmed enzymes.
 *
 * The staff page prints the isolate list beside each chart -- isolate id,
 * organism, confidence. An isolate id is a patient's culture, so the counts
 * are here and the list is not.
 */

const TIER_COLOUR: Record<string, string> = {
  Critical: OKABE_ITO.vermillion,
  High: OKABE_ITO.orange,
  Medium: OKABE_ITO.blue,
};

export function MechanismsView({ data }: { data: MechanismsData }) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(sectors[0] ?? "human");
  const slice =
    data.slices.find((candidate) => candidate.sector === sector) ??
    data.slices[0];

  const organismGrid = useMemo(() => {
    if (!slice) return { organisms: [], mechanisms: [], cells: new Map() };
    const mechanisms = [
      ...new Set(slice.mechanisms.rows.map((row) => row.mechanism)),
    ];
    const cells = new Map<string, number | string | null>();
    const totals = new Map<string, number>();
    for (const row of slice.mechanisms.rows) {
      cells.set(`${row.organism}||${row.mechanism}`, row.isolates);
      const value = numeric(row.isolates);
      if (value !== null) {
        totals.set(row.organism, (totals.get(row.organism) ?? 0) + value);
      }
    }
    const organisms = [
      ...new Set(slice.mechanisms.rows.map((row) => row.organism)),
    ].sort((a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0));
    return { organisms, mechanisms, cells };
  }, [slice]);

  if (!slice) {
    return <Empty>No isolate carried a recognisable resistance pattern.</Empty>;
  }

  const sectorLabel = titleCase(slice.sector);

  const sentinelColumns: Column<SentinelRow>[] = [
    { key: "label", header: "Phenotype", format: "text" },
    { key: "code", header: "Code", format: "text" },
    { key: "whoTier", header: "WHO tier", format: "text" },
    { key: "positive", header: "Isolates", align: "right" },
    {
      key: "tested",
      header: "Tested for it",
      align: "right",
    },
    {
      key: "percent",
      header: "% of those tested",
      align: "right",
      format: "percent",
    },
  ];

  const mechanismColumns: Column<MechanismTotalRow>[] = [
    { key: "mechanism", header: "Mechanism", format: "text" },
    { key: "isolates", header: "Isolates", align: "right" },
    {
      key: "percent",
      header: "% of isolates screened",
      align: "right",
      format: "percent",
    },
    { key: "basis", header: "What the count rests on", format: "text" },
  ];

  const byOrganismColumns: Column<{ organism: string }>[] = [
    { key: "organism", header: "Organism", format: "text" },
    ...organismGrid.mechanisms.map((mechanism) => ({
      key: mechanism,
      header: mechanism,
      align: "right" as const,
      value: (row: { organism: string }) =>
        organismGrid.cells.get(`${row.organism}||${mechanism}`) ?? 0,
    })),
  ];

  const crossColumns: Column<CrossResistanceRow>[] = [
    { key: "antibioticClass", header: "Antibiotic class", format: "text" },
    { key: "isolates", header: "Cross-resistant", align: "right" },
    {
      key: "high",
      header: "Every agent tested",
      align: "right",
    },
    { key: "moderate", header: "Some agents", align: "right" },
    {
      key: "testedOnTwoOrMore",
      header: "Tested on 2 or more",
      align: "right",
    },
    {
      key: "percent",
      header: "% of those tested",
      align: "right",
      format: "percent",
    },
  ];

  const breadthColumns: Column<BreadthOrganismRow>[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "isolates", header: "Isolates resistant to 3+", align: "right" },
    { key: "medianAgents", header: "Median agents", align: "right", format: "decimal" },
    { key: "maxAgents", header: "Most agents", align: "right" },
  ];

  return (
    <>
      <FilterBar
        controls={[
          {
            key: "sector",
            label: "Sector",
            value: sector,
            options: sectorOptions(sectors),
            note: "Each sector is screened separately. A percentage pooling a blood culture with a river sample describes neither.",
            onChange: setSector,
          },
        ]}
        summary={`${sectorLabel} — ${count(
          slice.isolatesScreened,
        )} isolates screened against ${count(slice.observations)} results.`}
      />

      <StatStrip
        stats={[
          { value: count(slice.isolatesScreened), label: "Isolates screened" },
          {
            value: count(slice.mechanisms.totals.length),
            label: "Mechanisms inferred",
          },
          {
            value: percent(slice.breadth.percent ?? null),
            label: "Resistant to 3 or more agents",
            hint: `${count(slice.breadth.isolates ?? 0)} isolates`,
          },
          {
            value: count(slice.breadth.medianAgents ?? null),
            label: "Median agents resisted",
            hint: "among those resistant to three or more",
          },
        ]}
      />

      <Note tone="limit">
        Every figure here is inferred from a susceptibility pattern, not from a
        confirmatory test or a gene. What each count rests on is printed beside
        it.
      </Note>

      <Section title="WHO priority phenotypes">
        <Figure
          title={`WHO priority phenotypes — ${sectorLabel}`}
          caption="The denominator is the isolates tested against the agents that define the phenotype, not every isolate."
          hideTitle
        >
          <BarChart
            rows={slice.sentinel.rows.map((row) => ({
              label: row.label,
              value: row.percent,
              denominator: row.tested,
              colour: TIER_COLOUR[row.whoTier] ?? OKABE_ITO.grey,
            }))}
            unit=""
            suffix="%"
            max={100}
            xLabel="% of isolates tested for the phenotype"
            yLabel="Phenotype"
            labelWidth={250}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={sentinelColumns}
          rows={slice.sentinel.rows}
          searchKeys={["label", "code"]}
          searchLabel="Search phenotype"
          initialSort={{ key: "positive", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.sentinel.suppression} />
      </Section>

      <Section title="Inferred mechanisms">
        <Figure
          title={`Inferred resistance mechanisms — ${sectorLabel}`}
          hideTitle
        >
          <BarChart
            rows={slice.mechanisms.totals.map((row) => ({
              label: row.mechanism,
              value: row.isolates,
              denominator: slice.isolatesScreened,
            }))}
            unit=""
            colour={OKABE_ITO.purple}
            xLabel="Isolates carrying the pattern"
            yLabel="Mechanism"
            labelWidth={150}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={mechanismColumns}
          rows={slice.mechanisms.totals}
          initialSort={{ key: "isolates", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.mechanisms.totalSuppression} />
      </Section>

      <Section title="Which organisms carry them">
        <DataTable
          columns={byOrganismColumns}
          rows={organismGrid.organisms.map((organism) => ({ organism }))}
          searchKeys={["organism"]}
          searchLabel="Search organism"
        />
        <SuppressionNote suppression={slice.mechanisms.suppression} />
      </Section>

      <Section title="Cross-resistance within a class">
        <Figure
          title={`Cross-resistance within an antibiotic class — ${sectorLabel}`}
          caption="An isolate counts as cross-resistant when it resists two or more agents of the class. The denominator is the isolates tested against two or more of them."
          hideTitle
        >
          <BarChart
            rows={slice.crossResistance.rows.map((row) => ({
              label: row.antibioticClass,
              value: row.percent,
              denominator: row.testedOnTwoOrMore,
            }))}
            unit=""
            suffix="%"
            max={100}
            colour={OKABE_ITO.vermillion}
            xLabel="% of isolates tested on two or more agents of the class"
            yLabel="Antibiotic class"
            labelWidth={190}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={crossColumns}
          rows={slice.crossResistance.rows}
          searchKeys={["antibioticClass"]}
          searchLabel="Search class"
          initialSort={{ key: "percent", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.crossResistance.suppression} />
      </Section>

      <Section
        title="How many agents an isolate defeats"
        intro="Three agents is the Magiorakos floor for multidrug resistance. These bands say how far past it the isolates reach."
      >
        <Figure
          title={`Breadth of resistance per isolate — ${sectorLabel}`}
          hideTitle
        >
          <BarChart
            rows={slice.breadth.bands.map((row) => ({
              label: row.band,
              value: row.isolates,
              denominator: slice.isolatesScreened,
            }))}
            unit=""
            colour={OKABE_ITO.black}
            xLabel="Isolates"
            yLabel="Agents resisted"
            labelWidth={140}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={breadthColumns}
          rows={slice.breadth.rows}
          searchKeys={["organism"]}
          searchLabel="Search organism"
          initialSort={{ key: "isolates", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.breadth.suppression} />
      </Section>
    </>
  );
}
