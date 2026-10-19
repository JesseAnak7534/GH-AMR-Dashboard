"use client";

import { useMemo, useState } from "react";
import { IntervalChart } from "@/components/Charts";
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
import type {
  AntibiogramRow,
  ResistanceData,
  StratumRow,
} from "@/lib/data";
import { count, humanise, interval, percent, titleCase } from "@/lib/format";

/**
 * The resistance section.
 *
 * The reader switches sector, and the page swaps between slices that were each
 * computed and suppressed separately in Python. It does not compose a slice of
 * its own, which is the whole safety argument: no combination of controls here
 * can produce a figure the export did not decide to publish.
 *
 * Sectors are never pooled. A percentage mixing hospital isolates with river
 * water describes neither, so there is no "all sectors" option -- unlike the
 * organism counts, where adding an animal isolate to a human one does give two
 * isolates.
 */
export function ResistanceView({ data }: { data: ResistanceData }) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(
    sectors.includes("human") ? "human" : (sectors[0] ?? ""),
  );
  const slice = data.slices.find((s) => s.sector === sector) ?? data.slices[0];
  const [stratum, setStratum] = useState(slice?.strata[0]?.key ?? "");

  const colours = Object.fromEntries(
    data.slices.map((s) => [s.sector, s.colour]),
  );

  const lowest = useMemo(() => {
    if (!slice) return [];
    return [...slice.rows]
      .filter((row) => row.percent_susceptible !== null)
      .sort(
        (a, b) =>
          (a.percent_susceptible ?? 0) - (b.percent_susceptible ?? 0),
      )
      .slice(0, 18)
      .map((row) => ({
        label: `${row.organism} · ${row.antibiotic}`,
        value: row.percent_susceptible,
        low: row.ci_low,
        high: row.ci_high,
        denominator: row.tested,
      }));
  }, [slice]);

  if (!slice) {
    return (
      <Empty>
        No susceptibility results have been published yet. When they are, this
        page will show the proportion of tested isolates that remained
        susceptible, with the number of isolates behind every figure.
      </Empty>
    );
  }

  const activeStratum =
    slice.strata.find((s) => s.key === stratum) ?? slice.strata[0];

  const antibiogramColumns: Column<AntibiogramRow>[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "antibiotic", header: "Antibiotic", format: "text" },
    { key: "tested", header: "Isolates tested", align: "right" },
    {
      key: "percent_susceptible",
      header: "% susceptible",
      align: "right",
      format: "percent",
    },
    {
      key: "ci",
      header: "95% CI",
      align: "right",
      format: "text",
      value: (row) => interval(row.ci_low, row.ci_high),
    },
    { key: "breakpoints", header: "Breakpoints", format: "text" },
  ];

  const stratumColumns: Column<StratumRow>[] = [
    { key: "stratum", header: humanise(activeStratum?.key ?? ""), format: "text" },
    { key: "isolates", header: "Isolates", align: "right" },
    { key: "observations", header: "Observations", align: "right" },
    {
      key: "percent_non_susceptible",
      header: "% non-susceptible",
      align: "right",
      format: "percent",
    },
    {
      key: "ci",
      header: "95% CI",
      align: "right",
      format: "text",
      value: (row) => interval(row.ci_low, row.ci_high),
    },
    { key: "distinct_pairs", header: "Distinct pairs", align: "right" },
  ];

  return (
    <>
      <Segmented
        label="Sector"
        options={sectors}
        value={sector}
        onChange={(next) => {
          setSector(next);
          const nextSlice = data.slices.find((s) => s.sector === next);
          setStratum(nextSlice?.strata[0]?.key ?? "");
        }}
        colours={colours}
      />

      <StatStrip
        stats={[
          { value: count(slice.isolates), label: "Isolates" },
          {
            value: count(slice.pairsReported),
            label: "Published as a rate",
            hint: `of ${count(slice.pairsTotal)} organism–antibiotic pairs`,
          },
          {
            value: count(slice.pairsSuppressed),
            label: "Too few to publish",
            hint: `fewer than ${data.minIsolatesForReporting} isolates`,
          },
          {
            value: titleCase(slice.sector),
            label: "Sector shown",
            hint: "sectors are never pooled into one rate",
          },
        ]}
      />

      {slice.pairsReported === 0 ? (
        <Note tone="limit">
          No organism–antibiotic combination in the {slice.sector} sector
          reaches {data.minIsolatesForReporting} isolates, which is the minimum
          this platform will put a percentage on. A percentage over a handful of
          results is not a measurement, so none is shown. The counts are in the
          organisms section, where they are large enough to publish.
        </Note>
      ) : (
        <>
          <Section
            title="Where susceptibility is lowest"
            intro="The combinations in this sector with the smallest proportion of susceptible isolates. The axis is fixed from 0 to 100% rather than scaled to the data, because a chart running from 70 to 95 makes a five-point difference look like a collapse."
          >
            <IntervalChart rows={lowest} colour={slice.colour} />
          </Section>

          <Section
            title="Every published combination"
            intro="Search by organism or antibiotic, and sort any column. Every row here was published by the export, so narrowing the view cannot reveal anything that was withheld."
          >
            <DataTable
              columns={antibiogramColumns}
              rows={slice.rows}
              searchKeys={["organism", "antibiotic"]}
              searchLabel="Search organism or antibiotic"
              initialSort={{ key: "tested", direction: "desc" }}
            />
            <SuppressionNote suppression={slice.suppression} />
          </Section>
        </>
      )}

      {activeStratum ? (
        <Section
          title="Resistance by setting"
          intro="The same results split by where the specimen came from. The unit here is one isolate against one agent, not the isolate: an isolate tested against twelve agents cannot be the denominator for twelve results."
        >
          <Segmented
            label="Split by"
            options={slice.strata.map((s) => s.key)}
            value={activeStratum.key}
            onChange={setStratum}
          />
          <div className="mt-4">
            <DataTable
              columns={stratumColumns}
              rows={activeStratum.rows}
              searchKeys={["stratum"]}
              searchLabel="Search"
              initialSort={{ key: "observations", direction: "desc" }}
            />
          </div>
          <Caption>
            Two settings are only comparable when similar panels were tested,
            which is why the number of distinct organism–antibiotic pairs is
            shown beside each. A ward that tests four agents and one that tests
            fourteen will differ for that reason alone.
          </Caption>
          <SuppressionNote suppression={activeStratum.suppression} />
        </Section>
      ) : null}

      <Note>
        <strong>Method.</strong> {slice.method.deduplication} Percentages are
        not published below {slice.method.minIsolates} isolates, following CLSI
        M39. Intervals are Wilson intervals, which stay inside 0–100% near the
        extremes where the ordinary normal approximation does not.
        Quality-control failures excluded: {count(slice.method.qcExcluded)}.
      </Note>
    </>
  );
}
