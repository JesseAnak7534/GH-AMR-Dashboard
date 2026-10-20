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
import type { QualityData } from "@/lib/clinical";
import { count, percent, titleCase } from "@/lib/format";
import { OKABE_ITO } from "@/lib/palette";

/**
 * Data coverage and quality.
 *
 * The one page where a count of zero is the finding. A field nobody filled is
 * reported as a field nobody filled, not left off the chart, because a
 * breakdown by a field that is empty will draw one confident bar labelled "Not
 * recorded" and look like data.
 *
 * There is no sector switch. Coverage is a property of the collection as a
 * whole, and the sector split is itself one of the measures.
 */

const STATUS_COLOUR: Record<string, string> = {
  complete: OKABE_ITO.green,
  partial: OKABE_ITO.orange,
  sparse: OKABE_ITO.vermillion,
  "not collected": OKABE_ITO.black,
  "column absent": OKABE_ITO.grey,
  "no records in scope": OKABE_ITO.grey,
};

export function QualityView({ data }: { data: QualityData }) {
  if (!data.coverage.specimens) {
    return <Empty>No specimens are in the traceability chain yet.</Empty>;
  }

  const plausibilityColumns: Column<
    (typeof data.plausibility.rows)[number]
  >[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "antibiotic", header: "Antibiotic", format: "text" },
    {
      key: "kind",
      header: "Kind",
      format: "text",
      value: (row) =>
        row.kind === "error"
          ? "Not biologically possible"
          : "Not to be reported clinically",
    },
    { key: "results", header: "Results", align: "right" },
    { key: "recordedSusceptible", header: "Recorded S", align: "right" },
    { key: "reason", header: "Why", format: "text" },
  ];

  // What each metric is and what it must not be used for. The numerator,
  // denominator, conversion and calculation columns are dropped: they describe
  // how the figure is produced rather than what it says.
  const metricColumns: Column<Record<string, string>>[] = [
    "Metric",
    "Unit",
    "Intended use",
    "Not to be used for",
  ]
    .filter((key) => key in (data.denominators.metrics[0] ?? {}))
    .map((key) => ({ key, header: key, format: "text" as const }));

  return (
    <>
      <StatStrip
        stats={[
          {
            value: count(data.coverage.specimens),
            label: "Specimens",
            href: "#coverage",
          },
          {
            value: count(data.coverage.isolates),
            label: "Isolates",
            href: "#linkage",
          },
          {
            value: count(data.coverage.observations),
            label: "Susceptibility results",
            href: "#result-quality",
          },
          {
            value: count(data.coverage.laboratories),
            label: "Laboratories reporting",
            href: "#completeness",
          },
        ]}
      />

      <Section
        id="coverage"
        title="Reporting coverage"
        intro="How much material each sector contributes."
      >
        <Figure title="Specimens by sector" hideTitle>
          <BarChart
            rows={data.coverage.sectors.map((row) => ({
              label: titleCase(row.sector),
              value: row.specimens,
              colour: row.colour,
            }))}
            unit=""
            xLabel="Specimens"
            yLabel="Sector"
            labelWidth={150}
          />
        </Figure>
      </Section>

      <Section id="completeness" title="Completeness of core fields">
        {data.completeness.notCollected.length ? (
          <Note tone="limit">
            Not collected at all:{" "}
            <strong>{data.completeness.notCollected.join(", ")}</strong>.
          </Note>
        ) : null}

        <Figure title="Completeness of core fields" hideTitle>
          <BarChart
            rows={data.completeness.rows
              .filter((row) => row.percent !== null)
              .map((row) => ({
                label: row.field,
                value: row.percent,
                denominator: row.of,
                colour: STATUS_COLOUR[row.status] ?? OKABE_ITO.grey,
                note: row.status,
              }))}
            unit=""
            suffix="%"
            max={100}
            xLabel="% of records in scope with an informative value"
            yLabel="Core field"
            labelWidth={210}
          />
        </Figure>
      </Section>

      <Section id="timeliness" title="Timeliness">
        <StatStrip
          stats={[
            {
              value: data.timeliness.latest ?? "—",
              label: "Most recent specimen",
            },
            {
              value:
                data.timeliness.daysSinceLatest === null
                  ? "—"
                  : `${count(data.timeliness.daysSinceLatest)} days`,
              label: "Age of the most recent",
            },
            {
              value:
                data.timeliness.turnaroundMedianDays === null
                  ? "not recorded"
                  : `${data.timeliness.turnaroundMedianDays.toFixed(1)} days`,
              label: "Collection to laboratory receipt",
              hint: "median",
            },
            {
              value: count(data.timeliness.turnaroundMeasurable),
              label: "Specimens where it can be measured",
              hint: "both a collection and a receipt time",
            },
          ]}
        />
        <Note
          tone={
            data.timeliness.status === "current" ? "method" : "limit"
          }
        >
          {data.timeliness.note}
        </Note>
      </Section>

      <Section
        id="linkage"
        title="Chain linkage"
        intro="How much of the chain from specimen to sequence is joined up."
      >
        <StatStrip
          stats={[
            {
              value: percent(data.linkage.culturePositivityPercent),
              label: "Culture positivity",
              hint: `${count(data.linkage.specimensWithIsolate)} of ${count(
                data.linkage.specimensTotal,
              )} specimens yielded an isolate`,
            },
            {
              value: percent(data.linkage.specimensWithWardPercent),
              label: "Specimens with a ward",
              hint: "without one, healthcare-association cannot be assessed",
            },
            {
              value: percent(data.linkage.isolatesWithResultPercent),
              label: "Isolates with a result",
              hint: `${count(data.linkage.isolatesWithResult)} of ${count(
                data.linkage.isolatesTotal,
              )}`,
            },
            {
              value: percent(data.linkage.percentIsolatesSequenced),
              label: "Isolates sequenced",
              hint: `${count(data.linkage.genomicResults)} genomic results`,
            },
          ]}
        />
      </Section>

      <Section id="result-quality" title="Result quality and provenance">
        <StatStrip
          stats={[
            {
              value: percent(data.resultQuality.qcRecordedPercent),
              label: "Results with quality control recorded",
            },
            {
              value: count(data.resultQuality.qcFail),
              label: "Quality-control failures",
              hint: "excluded from cumulative reporting",
            },
            {
              value: count(data.resultQuality.resultsWithoutEdition),
              label: "Results with no breakpoint edition",
              hint: "breakpoints move between editions",
            },
            {
              value: count(data.resultQuality.qcPass),
              label: "Quality-control passes",
            },
          ]}
        />

        <Figure title="How each result arrived" hideTitle>
          <BarChart
            rows={data.resultQuality.sources.map((row) => ({
              label: row.source,
              value: row.results,
            }))}
            unit=""
            colour={OKABE_ITO.blue}
            xLabel="Results"
            yLabel="How the result arrived"
            labelWidth={180}
          />
        </Figure>
      </Section>

      <Section
        id="implausible"
        title="Implausible organism–agent combinations"
        intro="Results for pairs where the answer cannot be meaningful. Each one is a finding to correct at source."
      >
        {data.plausibility.rows.length ? (
          <>
            <StatStrip
              stats={[
                {
                  value: count(data.plausibility.impossiblePairs),
                  label: "Impossible pairs",
                },
                {
                  value: count(data.plausibility.observationsAffected),
                  label: "Results affected",
                  hint: `${percent(
                    data.plausibility.percentAffected,
                  )} of ${count(data.plausibility.resultsTotal)} results`,
                },
                {
                  value: count(data.plausibility.recordedSusceptible),
                  label: "Recorded susceptible",
                  hint: "each one a testing, identification or data-entry error",
                },
                {
                  value: count(data.plausibility.suppressPairs),
                  label: "Active in vitro, not reportable",
                  hint: "excluded from clinical reporting, valid for surveillance",
                },
              ]}
            />
            <DataTable
              columns={plausibilityColumns}
              rows={data.plausibility.rows}
              searchKeys={["organism", "antibiotic"]}
              searchLabel="Search organism or antibiotic"
              initialSort={{ key: "results", direction: "desc" }}
            />
            <SuppressionNote suppression={data.plausibility.suppression} />
          </>
        ) : (
          <Note tone="method">
            None found.
          </Note>
        )}
      </Section>

      <Section
        id="denominators"
        title="Denominators for use and consumption"
        intro="Whether use and consumption can be reported as rates rather than volumes."
      >
        {data.denominators.available ? (
          <>
            <Figure title="Records carrying a usable denominator" hideTitle>
              <BarChart
                rows={data.denominators.rows.map((row) => ({
                  label: row.dataset,
                  value: row.percent,
                  denominator: row.records,
                }))}
                unit=""
                suffix="%"
                max={100}
                colour={OKABE_ITO.orange}
                xLabel="% of records carrying their denominator"
                yLabel="Dataset"
                labelWidth={240}
              />
            </Figure>
            {data.denominators.metrics.length ? (
              <>
                <h3 className="mt-6 text-[0.98rem] font-semibold">
                  How each metric is defined
                </h3>
                <DataTable
                  columns={metricColumns}
                  rows={data.denominators.metrics}
                />
              </>
            ) : null}
          </>
        ) : (
          <Empty>
            No antimicrobial use or consumption records have been submitted yet.
          </Empty>
        )}
      </Section>
    </>
  );
}
