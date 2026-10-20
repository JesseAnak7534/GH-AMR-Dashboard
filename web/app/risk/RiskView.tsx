"use client";

import { useState } from "react";
import { BarChart, ProportionBar } from "@/components/Charts";
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
import { TrendChart } from "@/components/TrendChart";
import type { RiskData } from "@/lib/clinical";
import { count, interval, numeric, percent, titleCase } from "@/lib/format";
import { OKABE_ITO, RESULT_COLOUR } from "@/lib/palette";

/**
 * Risk, and the other attempts on this platform to say which way things are
 * going.
 *
 * The score is a composite indicator, not a validated measure of danger. It
 * adds points for resistance level, for how many agents were tested and for
 * how much evidence there is, and those weights were chosen for this dashboard
 * rather than derived from outcome data. So the rule travels with the score,
 * and the page says what the ranking is for: ordering a list for review.
 *
 * Because volume contributes, an organism tested often scores higher than an
 * equally resistant one tested rarely. That is deliberate -- it ranks what
 * there is evidence about -- and it means the score is not comparable between
 * laboratories with different testing practices.
 *
 * The forecast is a straight line through monthly points. It is drawn with the
 * history it was fitted to, because a projection shown on its own reads as a
 * measurement.
 */

const LEVEL_COLOUR: Record<string, string> = {
  CRITICAL: OKABE_ITO.black,
  HIGH: OKABE_ITO.vermillion,
  MODERATE: OKABE_ITO.orange,
  LOW: OKABE_ITO.blue,
};

const SEVERITY_COLOUR: Record<string, string> = {
  CRITICAL: OKABE_ITO.black,
  HIGH: OKABE_ITO.vermillion,
};

const DIRECTION_NOTE: Record<string, string> = {
  increasing:
    "The second half of the record is more than five points more resistant than the first.",
  decreasing:
    "The second half of the record is more than five points less resistant than the first.",
  stable:
    "The two halves of the record differ by less than five points, which this comparison treats as no movement.",
  insufficient_data: "Too few dated results to compare two halves.",
};

export function RiskView({ data }: { data: RiskData }) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(sectors[0] ?? "human");
  const [floor, setFloor] = useState(0);
  const slice =
    data.slices.find((candidate) => candidate.sector === sector) ??
    data.slices[0];

  if (!slice) {
    return <Empty>No sector holds results to assess.</Empty>;
  }

  const sectorLabel = titleCase(slice.sector);

  const scoreRows = slice.scores.rows.filter(
    (row) => (numeric(row.resistancePercent) ?? 0) >= floor,
  );

  const organismColumns: Column<
    (typeof slice.organismComparison.rows)[number]
  >[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "resistant", header: "R", align: "right" },
    { key: "intermediate", header: "I", align: "right" },
    { key: "susceptible", header: "S", align: "right" },
    { key: "observations", header: "Results", align: "right" },
    {
      key: "resistancePercent",
      header: "% resistant",
      align: "right",
      format: "percent",
    },
  ];

  const summaryColumns: Column<
    (typeof slice.susceptibilitySummary.rows)[number]
  >[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "antibiotic", header: "Antibiotic", format: "text" },
    { key: "tested", header: "Tested", align: "right" },
    { key: "susceptible", header: "Susceptible", align: "right" },
    {
      key: "susceptibilityPercent",
      header: "% susceptible",
      align: "right",
      format: "percent",
    },
    {
      key: "ci",
      header: "95% CI",
      align: "right",
      format: "text",
      value: (row) => interval(row.ciLow, row.ciHigh),
    },
    {
      key: "meetsThreshold",
      header: `At least ${data.minIsolates} isolates`,
      format: "text",
      value: (row) => (row.meetsThreshold ? "Yes" : "No"),
    },
    { key: "observation", header: "Observation", format: "text" },
  ];

  const history = slice.forecast.history;
  const forecastSeries = [
    {
      label: "Measured, by month",
      colour: OKABE_ITO.blue,
      points: history.map((point) => ({
        period: point.period,
        value: point.resistancePercent,
        low: null,
        high: null,
        denominator: point.observations,
      })),
    },
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
            note: "Each sector is assessed separately. A rate pooling a blood culture with a river sample describes neither.",
            onChange: setSector,
          },
        ]}
        summary={`${sectorLabel} — ${count(
          slice.statistics.observations,
        )} results on ${count(slice.statistics.isolates)} isolates across ${count(
          slice.statistics.organisms,
        )} organisms and ${count(slice.statistics.antibiotics)} agents.`}
      />

      <StatStrip
        stats={[
          {
            value: percent(slice.statistics.resistancePercent),
            label: "Results resistant",
          },
          {
            value: percent(slice.statistics.intermediatePercent),
            label: "Intermediate",
          },
          {
            value: percent(slice.statistics.susceptiblePercent),
            label: "Susceptible",
          },
          {
            value: count(slice.statistics.observations),
            label: "Results assessed",
          },
        ]}
      />

      <Section title="How the results fall">
        <ProportionBar
          parts={[
            {
              label: "Resistant",
              value: slice.statistics.resistant,
              colour: RESULT_COLOUR.R,
            },
            {
              label: "Intermediate",
              value: slice.statistics.intermediate,
              colour: RESULT_COLOUR.I,
            },
            {
              label: "Susceptible",
              value: slice.statistics.susceptible,
              colour: RESULT_COLOUR.S,
            },
          ]}
        />
      </Section>

      <Section
        title="Direction of travel"
        intro="The first half of the record against the second."
      >
        <StatStrip
          stats={[
            {
              value: titleCase(slice.trend.direction.replace(/_/g, " ")),
              label: "Direction",
            },
            {
              value: percent(slice.trend.firstHalfPercent),
              label: "First half resistant",
            },
            {
              value: percent(slice.trend.secondHalfPercent),
              label: "Second half resistant",
            },
            {
              value:
                slice.trend.changePoints === null
                  ? "—"
                  : `${slice.trend.changePoints >= 0 ? "+" : ""}${slice.trend.changePoints.toFixed(2)} points`,
              label: "Change",
            },
          ]}
        />
        <Note tone="limit">
          {DIRECTION_NOTE[slice.trend.direction] ??
            "The two halves could not be compared."}
        </Note>
      </Section>

      <Section
        title="Organism risk scores"
        intro="Which organisms carry the most resistance, on the most evidence, across the widest panel."
      >
        <Note tone="limit">
          A way of ordering a list for review, not a validated measure of
          danger.
        </Note>

        <div className="rounded-lg border border-rule bg-shell px-4 py-3.5">
          <label className="block max-w-[22rem]">
            <span className="mb-1 block text-[0.74rem] font-semibold text-ink-soft">
              Show organisms at or above this resistance rate
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={floor}
              onChange={(event) => setFloor(Number(event.target.value))}
              className="w-full accent-[#8c1d18]"
            />
          </label>
          <p className="mt-1 text-[0.72rem] text-ink-faint">
            {floor}% and above — {count(scoreRows.length)} of{" "}
            {count(slice.scores.rows.length)} organisms. A display filter, not a
            clinical or public-health threshold.
          </p>
        </div>

        {scoreRows.length ? (
          <>
            <Figure
              title={`Organism risk scores — ${sectorLabel}`}
              caption="Out of 100."
              hideTitle
            >
              <BarChart
                rows={scoreRows.map((row) => ({
                  label: row.organism,
                  value: row.riskScore,
                  denominator: row.observations,
                  colour: LEVEL_COLOUR[row.riskLevel ?? ""] ?? OKABE_ITO.grey,
                  note: row.riskLevel ?? undefined,
                }))}
                unit=""
                max={100}
                xLabel="Composite risk score, out of 100"
                yLabel="Organism"
                labelWidth={220}
              />
            </Figure>
            <SuppressionNote suppression={slice.scores.suppression} />
          </>
        ) : (
          <Empty>No organism reaches that resistance rate.</Empty>
        )}

        <p className="text-[0.78rem] text-ink-faint">
          Out of 100: 70 and above critical, 50 high, 30 moderate, below 30 low.
        </p>
      </Section>

      <Section
        title="Where the burden sits"
        intro="Which specimens the resistance is coming from."
      >
        <StatStrip
          stats={[
            {
              value: percent(slice.burden.resistancePercent),
              label: "Overall resistance",
            },
            {
              value: count(slice.burden.resistantObservations),
              label: "Resistant results",
            },
            {
              value: count(slice.burden.observations),
              label: "Results assessed",
            },
            { value: slice.burden.band, label: "Band on this indicator" },
          ]}
        />
        {slice.burden.rows.length ? (
          <>
            <Figure
              title={`Resistance by specimen type — ${sectorLabel}`}
              hideTitle
            >
              <BarChart
                rows={slice.burden.rows.map((row) => ({
                  label: row.group,
                  value: row.resistancePercent,
                  denominator: row.observations,
                }))}
                unit=""
                suffix="%"
                max={100}
                colour={OKABE_ITO.vermillion}
                xLabel="% of results resistant"
                yLabel="Specimen type"
                labelWidth={200}
              />
            </Figure>
            <SuppressionNote suppression={slice.burden.suppression} />
          </>
        ) : (
          <Empty>No specimen type is recorded for this sector.</Empty>
        )}
      </Section>

      <Section
        title="Emerging patterns"
        intro="Organism–agent pairs that were heavily resistant in the most recent three months. Read each one against its count."
      >
        {slice.emerging.rows.length ? (
          <>
            <Figure
              title={`Emerging organism–agent patterns — ${sectorLabel}`}
              hideTitle
            >
              <BarChart
                rows={slice.emerging.rows.map((row) => ({
                  label: `${row.organism} · ${row.antibiotic}`,
                  value: row.resistancePercent,
                  denominator: row.observations,
                  colour: SEVERITY_COLOUR[row.severity] ?? OKABE_ITO.orange,
                  note: row.severity,
                }))}
                unit=""
                suffix="%"
                max={100}
                xLabel="% of recent results resistant"
                yLabel="Organism · antibiotic"
                labelWidth={280}
              />
            </Figure>
            <SuppressionNote suppression={slice.emerging.suppression} />
          </>
        ) : (
          <Empty>No pattern met the emerging-resistance criteria.</Empty>
        )}
      </Section>

      <Section
        title="Where the trend is heading"
        intro="The monthly rate, and where its slope points."
      >
        {slice.forecast.error ? (
          <Note tone="limit">{slice.forecast.error}</Note>
        ) : (
          <>
            <Figure
              title={`Monthly resistance rate — ${sectorLabel}`}
              hideTitle
            >
              <TrendChart
                series={forecastSeries}
                unit="% of results resistant"
                xLabel="Month of specimen collection"
                yLabel="% of results resistant"
                denominatorLabel="results"
              />
            </Figure>
            <Note tone="limit">
              A straight line through the months so far. Not a prediction of
              resistance in Ghana.
            </Note>
          </>
        )}
      </Section>

      <Section title="Organisms compared">
        <DataTable
          columns={organismColumns}
          rows={slice.organismComparison.rows}
          searchKeys={["organism"]}
          searchLabel="Search organism"
          initialSort={{ key: "resistancePercent", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.organismComparison.suppression} />
      </Section>

      <Section
        title="Agents compared"
        intro="How each agent performed across every organism it was tested against."
      >
        <Figure title={`Susceptibility by agent — ${sectorLabel}`} hideTitle>
          <BarChart
            rows={slice.antibioticComparison.rows.map((row) => ({
              label: row.antibiotic,
              value: row.susceptibilityPercent,
              denominator: row.observations,
            }))}
            unit=""
            suffix="%"
            max={100}
            colour={OKABE_ITO.green}
            xLabel="% of results susceptible"
            yLabel="Antibiotic"
            labelWidth={220}
          />
        </Figure>
        <SuppressionNote suppression={slice.antibioticComparison.suppression} />
      </Section>

      <Section
        title="Susceptibility summary"
        intro="Susceptibility for each organism–agent pair, with its interval."
      >
        <Note tone="limit">
          Not prescribing guidance, and not a cumulative antibiogram.
        </Note>
        <StatStrip
          stats={[
            {
              value: count(slice.susceptibilitySummary.pairs),
              label: "Organism–agent pairs",
            },
            {
              value: count(slice.susceptibilitySummary.reportable),
              label: `At or above ${data.minIsolates} isolates`,
            },
            {
              value: count(slice.susceptibilitySummary.provisional),
              label: "Below that floor",
              hint: "shown, and to be read as provisional",
            },
            {
              value: count(slice.statistics.isolates),
              label: "Isolates behind the table",
            },
          ]}
        />
        <DataTable
          columns={summaryColumns}
          rows={slice.susceptibilitySummary.rows}
          searchKeys={["organism", "antibiotic"]}
          searchLabel="Search organism or antibiotic"
          initialSort={{ key: "tested", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.susceptibilitySummary.suppression} />
      </Section>
    </>
  );
}
