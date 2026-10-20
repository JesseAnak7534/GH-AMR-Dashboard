"use client";

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
import { TrendChart } from "@/components/TrendChart";
import type { HaiData, HaiGroupRow } from "@/lib/clinical";
import { count, percent } from "@/lib/format";
import { OKABE_ITO } from "@/lib/palette";

/**
 * Hospital-acquired infection.
 *
 * Human clinical specimens only, and there is no sector switch for that
 * reason: a river sample cannot be healthcare-associated. The organisms that
 * usually are -- ESKAPE and the wider nosocomial list -- are flagged rather
 * than filtered to, so the page can report what share of the hospital burden
 * they account for instead of assuming it.
 *
 * Sentinel laboratories are named. Attribution is the point of sentinel
 * surveillance and they are named everywhere else on this site. The facility a
 * patient attended is not published anywhere, and does not reach this page.
 */

const GROUP_COLUMNS: Column<HaiGroupRow>[] = [
  { key: "group", header: "Reporting unit", format: "text" },
  { key: "isolates", header: "Isolates", align: "right" },
  { key: "observations", header: "Results", align: "right" },
  {
    key: "resistancePercent",
    header: "% resistant",
    align: "right",
    format: "percent",
  },
  { key: "mdrIsolates", header: "MDR isolates", align: "right" },
];

export function HaiView({ data }: { data: HaiData }) {
  if (
    !data.available ||
    !data.headline ||
    !data.eskape ||
    !data.profile ||
    !data.split ||
    !data.mdr ||
    !data.trend
  ) {
    return (
      <Empty>
        No human clinical isolates are in scope, so healthcare-associated
        infection cannot be reported.
      </Empty>
    );
  }

  const { headline, eskape, profile, split, mdr, trend } = data;

  const eskapeColumns: Column<(typeof eskape.rows)[number]>[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "isolates", header: "Isolates", align: "right" },
    { key: "observations", header: "Results", align: "right" },
    {
      key: "resistancePercent",
      header: "% resistant",
      align: "right",
      format: "percent",
    },
    { key: "mdrIsolates", header: "MDR isolates", align: "right" },
    {
      key: "mdrPercent",
      header: "% MDR",
      align: "right",
      format: "percent",
    },
  ];

  const profileColumns: Column<(typeof profile.rows)[number]>[] = [
    { key: "organism", header: "Organism", format: "text" },
    {
      key: "nosocomial",
      header: "Nosocomial",
      format: "text",
      value: (row) => (row.nosocomial ? "Yes" : "No"),
    },
    { key: "isolates", header: "Isolates", align: "right" },
    { key: "observations", header: "Results", align: "right" },
    {
      key: "resistancePercent",
      header: "% resistant",
      align: "right",
      format: "percent",
    },
  ];

  const series = [
    {
      label: "All results resistant",
      colour: OKABE_ITO.vermillion,
      key: "resistancePercent" as const,
    },
    {
      label: "Isolates multidrug resistant",
      colour: OKABE_ITO.purple,
      key: "mdrPercent" as const,
    },
    {
      label: "Isolates of a nosocomial organism",
      colour: OKABE_ITO.orange,
      key: "nosocomialPercent" as const,
    },
  ].map((line) => ({
    label: line.label,
    colour: line.colour,
    points: trend.points.map((point) => ({
      period: point.period,
      value: point[line.key],
      low: null,
      high: null,
      denominator: point.observations,
    })),
  }));

  return (
    <>
      <StatStrip
        stats={[
          { value: count(headline.isolates), label: "Hospital isolates" },
          {
            value: percent(headline.nosocomialPercent),
            label: "Nosocomial organisms",
            hint: `${count(headline.nosocomialIsolates)} isolates`,
          },
          {
            value: percent(headline.mdrPercent),
            label: "Multidrug resistant",
            hint: `${count(headline.mdrIsolates)} of ${count(
              headline.classifiable,
            )} classifiable`,
          },
          {
            value: percent(headline.resistancePercent),
            label: "Results resistant",
            hint: `${count(headline.observations)} results`,
          },
        ]}
      />

      <Note tone="method">
        One isolate per patient per organism, following CLSI M39. Multidrug
        resistance is the Magiorakos definition, applied with the category set
        for each organism.
      </Note>

      <Section
        title="ESKAPE organisms"
        intro="Enterococcus faecium, Staphylococcus aureus, Klebsiella pneumoniae, Acinetobacter baumannii, Pseudomonas aeruginosa and Enterobacter — the organisms behind most healthcare-associated infection worldwide."
      >
        <Figure title="ESKAPE organisms — resistance and multidrug resistance" hideTitle>
          <BarChart
            rows={eskape.rows.map((row) => ({
              label: row.organism,
              value: row.resistancePercent,
              denominator: row.isolates,
            }))}
            unit=""
            suffix="%"
            max={100}
            colour={OKABE_ITO.vermillion}
            xLabel="% of results resistant"
            yLabel="Organism"
            labelWidth={210}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={eskapeColumns}
          rows={eskape.rows}
          searchKeys={["organism"]}
          searchLabel="Search organism"
          initialSort={{ key: "resistancePercent", direction: "desc" }}
        />
        <SuppressionNote suppression={eskape.suppression} />
      </Section>

      <Section
        title="Hospital resistance profile"
        intro="The fifteen organisms with the most evidence behind them. Nosocomial organisms are marked, so the two groups can be read apart."
      >
        <Figure title="Hospital resistance profile by organism" hideTitle>
          <BarChart
            rows={profile.rows.map((row) => ({
              label: row.organism,
              value: row.resistancePercent,
              denominator: row.observations,
              colour: row.nosocomial ? OKABE_ITO.vermillion : OKABE_ITO.grey,
              note: row.nosocomial ? "Nosocomial" : "Other",
            }))}
            unit=""
            suffix="%"
            max={100}
            xLabel="% of results resistant"
            yLabel="Organism"
            labelWidth={210}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={profileColumns}
          rows={profile.rows}
          searchKeys={["organism"]}
          searchLabel="Search organism"
          initialSort={{ key: "resistancePercent", direction: "desc" }}
        />
        <SuppressionNote suppression={profile.suppression} />
      </Section>

      <Section title="Nosocomial against other organisms">
        <Figure title="Resistance in nosocomial and other organisms" hideTitle>
          <BarChart
            rows={split.rows.map((row) => ({
              label: row.group,
              value: row.resistancePercent,
              denominator: row.observations,
              colour:
                row.group === "Nosocomial organisms"
                  ? OKABE_ITO.vermillion
                  : OKABE_ITO.green,
            }))}
            unit=""
            suffix="%"
            max={100}
            xLabel="% of results resistant"
            yLabel="Organism group"
            labelWidth={180}
          />
        </Figure>
        <SuppressionNote suppression={split.suppression} />
      </Section>

      <Section
        title="Multidrug resistance in hospital"
        intro="Isolates non-susceptible across three or more antimicrobial categories, by organism."
      >
        {mdr.rows.length ? (
          <>
            <Figure title="Multidrug-resistant isolates by organism" hideTitle>
              <BarChart
                rows={mdr.rows.map((row) => ({
                  label: row.organism,
                  value: row.isolates,
                }))}
                unit=""
                colour={OKABE_ITO.purple}
                xLabel="Multidrug-resistant isolates"
                yLabel="Organism"
                labelWidth={210}
              />
            </Figure>
            <SuppressionNote suppression={mdr.suppression} />
          </>
        ) : (
          <Empty>No isolate met the multidrug-resistance definition.</Empty>
        )}

        {mdr.classes && mdr.topOrganism ? (
          <>
            <h3 className="mt-6 text-[0.98rem] font-semibold">
              Agent categories behind {mdr.topOrganism}
            </h3>
            <Figure
              title={`Resistance by agent category — ${mdr.topOrganism}`}
              hideTitle
            >
              <BarChart
                rows={mdr.classes.rows.map((row) => ({
                  label: row.antibioticClass,
                  value: row.resistancePercent,
                  denominator: row.observations,
                }))}
                unit=""
                suffix="%"
                max={100}
                colour={OKABE_ITO.vermillion}
                xLabel="% of results resistant"
                yLabel="Antimicrobial category"
                labelWidth={210}
              />
            </Figure>
            <SuppressionNote suppression={mdr.classes.suppression} />
          </>
        ) : null}
      </Section>

      <Section
        title="By sentinel laboratory"
        intro="Laboratories are named: attribution is the point of sentinel surveillance. The facility a patient attended is not published."
      >
        <Figure title="Hospital resistance by sentinel laboratory" hideTitle>
          <BarChart
            rows={(data.laboratories?.rows ?? []).map((row) => ({
              label: row.group,
              value: row.resistancePercent,
              denominator: row.observations,
            }))}
            unit=""
            suffix="%"
            max={100}
            colour={OKABE_ITO.blue}
            xLabel="% of results resistant"
            yLabel="Sentinel laboratory"
            labelWidth={240}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={GROUP_COLUMNS}
          rows={data.laboratories?.rows ?? []}
          searchKeys={["group"]}
          searchLabel="Search laboratory"
          initialSort={{ key: "resistancePercent", direction: "desc" }}
        />
        <SuppressionNote suppression={data.laboratories?.suppression ?? null} />
      </Section>

      <Section title="By region">
        <Figure title="Hospital resistance by region" hideTitle>
          <BarChart
            rows={(data.regions?.rows ?? []).map((row) => ({
              label: row.group,
              value: row.resistancePercent,
              denominator: row.observations,
            }))}
            unit=""
            suffix="%"
            max={100}
            colour={OKABE_ITO.green}
            xLabel="% of results resistant"
            yLabel="Region"
            labelWidth={190}
          />
        </Figure>
        <div className="mt-5" />
        <DataTable
          columns={GROUP_COLUMNS}
          rows={data.regions?.rows ?? []}
          searchKeys={["group"]}
          searchLabel="Search region"
          initialSort={{ key: "resistancePercent", direction: "desc" }}
        />
        <SuppressionNote suppression={data.regions?.suppression ?? null} />
      </Section>

      <Section
        title="Hospital infection trends"
        intro={`Quarterly. A quarter holding fewer than ${trend.minObservations} results is not plotted, and the line breaks there rather than bridging a value nobody measured.`}
      >
        <Figure title="Hospital infection trends, by quarter" hideTitle>
          <TrendChart
            series={series}
            unit="%"
            xLabel="Quarter of specimen collection"
            yLabel="Percentage"
            denominatorLabel="results"
          />
        </Figure>
      </Section>
    </>
  );
}
