"use client";

import { useState } from "react";
import { Column, DataTable } from "@/components/DataTable";
import {
  Empty,
  Note,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import { Segmented } from "@/components/Segmented";
import { TrendChart } from "@/components/TrendChart";
import type { TrendPeriodRow, TrendsData } from "@/lib/data";
import { count, interval, numeric, percent } from "@/lib/format";
import { ramp } from "@/lib/palette";

export function TrendsView({ data }: { data: TrendsData }) {
  const sectors = data.slices.map((s) => s.sector);
  const [sector, setSector] = useState(
    sectors.includes("human") ? "human" : (sectors[0] ?? ""),
  );
  const slice = data.slices.find((s) => s.sector === sector) ?? data.slices[0];

  if (!slice) {
    return <Empty>Not enough dated results to show a trend yet.</Empty>;
  }

  const colours = Object.fromEntries(data.slices.map((s) => [s.sector, s.colour]));

  const overall = [
    {
      label: "All pairs pooled",
      colour: slice.colour,
      points: slice.periods.map((row) => ({
        period: row.period,
        value: row.percent_non_susceptible,
        low: row.ci_low,
        high: row.ci_high,
        denominator: row.observations,
      })),
    },
  ];

  const shownSeries = slice.series.slice(0, 5);
  const pairColours = ramp(shownSeries.length);
  const pairs = shownSeries.map((series, index) => ({
    label: `${series.organism} · ${series.antibiotic}`,
    colour: pairColours[index],
    points: series.points.map((point) => ({
      period: point.period,
      value: point.percent_susceptible,
      low: point.ci_low,
      high: point.ci_high,
      denominator: point.tested,
    })),
  }));

  const drawn = slice.periods.filter(
    (row) => numeric(row.percent_non_susceptible) !== null,
  );
  const first = drawn[0];
  const last = drawn[drawn.length - 1];
  const change =
    first && last && first !== last
      ? (last.percent_non_susceptible as number) -
        (first.percent_non_susceptible as number)
      : null;
  const overlapping =
    first && last && first.ci_high !== null && last.ci_low !== null
      ? (last.ci_low as number) <= (first.ci_high as number) &&
        (first.ci_low as number) <= (last.ci_high as number)
      : true;

  const columns: Column<TrendPeriodRow>[] = [
    { key: "period", header: "Quarter", format: "text" },
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
          { value: count(drawn.length), label: "Quarters plotted" },
          {
            value: first ? percent(first.percent_non_susceptible) : "—",
            label: `First (${first?.period ?? "—"})`,
          },
          {
            value: last ? percent(last.percent_non_susceptible) : "—",
            label: `Latest (${last?.period ?? "—"})`,
          },
          {
            value:
              change === null
                ? "—"
                : `${change > 0 ? "+" : ""}${change.toFixed(1)} pts`,
            label: "Change",
            hint: overlapping
              ? "within the uncertainty"
              : "beyond the uncertainty",
          },
        ]}
      />

      {change !== null && overlapping ? (
        <Note tone="limit">
          The first and latest intervals overlap. The change is within the
          uncertainty of the two measurements, so it should not be read as a
          trend.
        </Note>
      ) : null}

      <Section title="All organism–antibiotic pairs pooled">
        <TrendChart
          series={overall}
          unit="% non-susceptible"
          denominatorLabel="observations"
        />
      </Section>

      {pairs.length ? (
        <Section
          title="The most-tested pairs"
          intro="Susceptibility, not non-susceptibility, so a falling line is a worsening picture."
        >
          <TrendChart series={pairs} unit="% susceptible" />
        </Section>
      ) : (
        <Section title="The most-tested pairs">
          <Empty>
            No organism–antibiotic pair in this sector has two or more quarters
            above {data.minObservations} results. A line through fewer points is
            not a trend.
          </Empty>
        </Section>
      )}

      <Section title="The figures">
        <DataTable
          columns={columns}
          rows={slice.periods}
          initialSort={{ key: "period", direction: "asc" }}
          pageSize={20}
        />
        <SuppressionNote suppression={slice.suppression} />
      </Section>

      <Note>
        <strong>Method.</strong> Quarterly, and deduplicated inside each quarter
        rather than across the series — a patient&rsquo;s isolate a year later
        is next year&rsquo;s data point, not a repeat. A quarter with fewer than{" "}
        {data.minObservations} results is not plotted and the line breaks there.
      </Note>
    </>
  );
}
