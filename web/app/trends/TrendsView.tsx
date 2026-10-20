"use client";

import { useState } from "react";
import { Figure } from "@/components/Figure";
import {
  Empty,
  Note,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import { FilterBar, sectorOptions } from "@/components/FilterBar";
import { TrendChart } from "@/components/TrendChart";
import type { TrendsData } from "@/lib/data";
import { count, numeric, percent, titleCase } from "@/lib/format";
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

  return (
    <>
      <FilterBar
        controls={[
          {
            key: "sector",
            label: "Sector",
            value: sector,
            options: sectorOptions(sectors),
            note: "Each sector has its own series; they are never pooled.",
            onChange: setSector,
          },
        ]}
        summary={`${titleCase(sector)} \u2014 ${drawn.length} of ${
          slice.periods.length
        } quarters hold enough results to plot.`}
      />

      <StatStrip
        stats={[
          {
            value: count(drawn.length),
            label: "Quarters plotted",
            href: "#pooled",
          },
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
            href: "/risk",
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

      <Section id="pooled" title="All organism–antibiotic pairs pooled">
        <Figure
          title={`Non-susceptibility by quarter — ${titleCase(sector)}`}
          hideTitle
        >
          <TrendChart
            series={overall}
            unit="% non-susceptible"
            xLabel="Quarter of specimen collection"
            yLabel="% of results non-susceptible"
            denominatorLabel="observations"
          />
        </Figure>
      </Section>

      {pairs.length ? (
        <Section title="The most-tested pairs (susceptibility)">
          <Figure title={`Most-tested pairs — ${titleCase(sector)}`} hideTitle>
            <TrendChart
              series={pairs}
              unit="% susceptible"
              xLabel="Quarter of specimen collection"
              yLabel="% of isolates susceptible"
            />
          </Figure>
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

      <SuppressionNote suppression={slice.suppression} />

    </>
  );
}
