"use client";

import { useMemo, useState } from "react";
import { IntervalChart } from "@/components/Charts";
import { HeatGrid } from "@/components/HeatGrid";
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
  PriorityData,
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
export function ResistanceView({
  data,
  priority,
}: {
  data: ResistanceData;
  priority: PriorityData;
}) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(
    sectors.includes("human") ? "human" : (sectors[0] ?? ""),
  );
  const slice = data.slices.find((s) => s.sector === sector) ?? data.slices[0];
  const [stratum, setStratum] = useState(slice?.strata[0]?.key ?? "");
  const [view, setView] = useState<"chart" | "matrix">("chart");
  const [listName, setListName] = useState<"none" | "who" | "ghana">("who");

  // Organisms on the chosen priority list, matched by the export rather than
  // re-derived here: an order such as Enterobacterales covers several genera,
  // and that mapping belongs beside the list it interprets.
  const priorityOrganisms = useMemo(() => {
    if (listName === "none") return new Set<string>();
    const entries = listName === "who" ? priority.who : priority.ghana;
    return new Set(entries.flatMap((entry) => entry.matched));
  }, [priority, listName]);

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
          No combination in the {slice.sector} sector reaches{" "}
          {data.minIsolatesForReporting} isolates, so no percentage is shown.
          The counts are in the organisms section.
        </Note>
      ) : (
        <>
          <Section title="Susceptibility">
            <div className="flex flex-wrap gap-x-8 gap-y-3">
              <Segmented
                label="View"
                options={["chart", "matrix"]}
                value={view}
                onChange={(next) => setView(next as "chart" | "matrix")}
              />
              <Segmented
                label="Priority list"
                options={["who", "ghana", "none"]}
                value={listName}
                onChange={(next) =>
                  setListName(next as "none" | "who" | "ghana")
                }
              />
            </div>
            <div className="mt-4">
              {view === "chart" ? (
                <IntervalChart rows={lowest} colour={slice.colour} />
              ) : (
                <HeatGrid
                  cells={slice.rows.map((row) => ({
                    organism: row.organism,
                    antibiotic: row.antibiotic,
                    percent: row.percent_susceptible,
                    tested: row.tested,
                    low: row.ci_low,
                    high: row.ci_high,
                  }))}
                  highlightOrganisms={priorityOrganisms}
                />
              )}
            </div>
          </Section>

          <Section
            title="Every published combination"
            intro="Search and sort. Every row shown has already passed disclosure control."
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
          intro="The unit is one isolate against one agent, not the isolate."
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
            Comparable only where similar panels were tested — the
            distinct-pair count beside each says how similar.
          </Caption>
          <SuppressionNote suppression={activeStratum.suppression} />
        </Section>
      ) : null}

      <Note>
        <strong>Method.</strong> {slice.method.deduplication} No percentage
        below {slice.method.minIsolates} isolates (CLSI M39); Wilson intervals.
        QC failures excluded: {count(slice.method.qcExcluded)}.
      </Note>
    </>
  );
}
