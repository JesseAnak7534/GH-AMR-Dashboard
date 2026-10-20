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

  const completenessColumns: Column<
    (typeof data.completeness.rows)[number]
  >[] = [
    { key: "field", header: "Field", format: "text" },
    { key: "scope", header: "Scope", format: "text" },
    { key: "recorded", header: "Recorded", align: "right" },
    { key: "of", header: "Records in scope", align: "right" },
    {
      key: "percent",
      header: "% informative",
      align: "right",
      format: "percent",
    },
    { key: "status", header: "Status", format: "text" },
  ];

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

  const denominatorColumns: Column<
    (typeof data.denominators.rows)[number]
  >[] = [
    { key: "dataset", header: "Dataset", format: "text" },
    { key: "denominator", header: "Denominator", format: "text" },
    { key: "withDenominator", header: "Records with one", align: "right" },
    { key: "records", header: "Records", align: "right" },
    { key: "percent", header: "% with one", align: "right", format: "percent" },
    { key: "consequence", header: "What is lost without it", format: "text" },
  ];

  const metricColumns: Column<Record<string, string>>[] = Object.keys(
    data.denominators.metrics[0] ?? {},
  ).map((key) => ({ key, header: key, format: "text" as const }));

  return (
    <>
      <StatStrip
        stats={[
          { value: count(data.coverage.specimens), label: "Specimens" },
          { value: count(data.coverage.isolates), label: "Isolates" },
          {
            value: count(data.coverage.observations),
            label: "Susceptibility results",
          },
          {
            value: count(data.coverage.laboratories),
            label: "Laboratories reporting",
          },
        ]}
      />

      <Note tone="method">
        A field counts as recorded only when it holds an informative value. A
        stored &ldquo;Unknown&rdquo; counts as missing: it is a placeholder, not
        an observation.
      </Note>

      <Section
        title="Reporting coverage"
        intro="A sector with few specimens cannot support a national statement about it, however confident a percentage elsewhere on this site looks."
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

      <Section title="Completeness of core fields">
        {data.completeness.notCollected.length ? (
          <Note tone="limit">
            Not collected at all:{" "}
            <strong>{data.completeness.notCollected.join(", ")}</strong>. These
            fields exist in the data model and are on the upload template, but
            no submission has populated them. Any breakdown by them shows a
            single &ldquo;Not recorded&rdquo; group.
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
        <div className="mt-5" />
        <DataTable
          columns={completenessColumns}
          rows={data.completeness.rows}
          searchKeys={["field"]}
          searchLabel="Search field"
          initialSort={{ key: "percent", direction: "asc" }}
        />
      </Section>

      <Section title="Timeliness">
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
        title="Chain linkage"
        intro="The traceability chain is only useful where it is joined up. These are the joins, measured."
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

      <Section title="Result quality and provenance">
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
        <Note tone="limit">
          Measured results were read from a plate or an instrument;
          rule-interpreted results were derived from a measurement; imported
          results arrived already interpreted, with provenance unknown.
        </Note>
      </Section>

      <Section
        title="Implausible organism–agent combinations"
        intro="Results recording susceptibility where it is not biologically possible, or where CLSI directs that the agent not be reported for that organism. These are data-quality findings, and the response is to correct them at source."
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
            No implausible organism–agent combination was found. Every result is
            for a pair where susceptibility testing is meaningful.
          </Note>
        )}
      </Section>

      <Section
        title="Denominators for use and consumption"
        intro="A rate needs a denominator. These are the records that carry one, and what is lost where they do not."
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
            <div className="mt-5" />
            <DataTable
              columns={denominatorColumns}
              rows={data.denominators.rows}
            />
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
