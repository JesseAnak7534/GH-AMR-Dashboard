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

  const scoreColumns: Column<(typeof slice.scores.rows)[number]>[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "riskScore", header: "Score", align: "right" },
    { key: "riskLevel", header: "Band", format: "text" },
    {
      key: "resistancePercent",
      header: "% resistant",
      align: "right",
      format: "percent",
    },
    { key: "observations", header: "Results", align: "right" },
    { key: "antibioticDiversity", header: "Agents tested", align: "right" },
    { key: "factors", header: "What contributed", format: "text" },
  ];

  const emergingColumns: Column<(typeof slice.emerging.rows)[number]>[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "antibiotic", header: "Antibiotic", format: "text" },
    {
      key: "resistancePercent",
      header: "% resistant",
      align: "right",
      format: "percent",
    },
    { key: "observations", header: "Results", align: "right" },
    { key: "severity", header: "Band", format: "text" },
  ];

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

  const antibioticColumns: Column<
    (typeof slice.antibioticComparison.rows)[number]
  >[] = [
    { key: "antibiotic", header: "Antibiotic", format: "text" },
    { key: "resistant", header: "R", align: "right" },
    { key: "intermediate", header: "I", align: "right" },
    { key: "susceptible", header: "S", align: "right" },
    { key: "observations", header: "Results", align: "right" },
    {
      key: "susceptibilityPercent",
      header: "% susceptible",
      align: "right",
      format: "percent",
    },
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

  const ruleColumns: Column<(typeof data.scoringRule)[number]>[] = [
    { key: "component", header: "Component", format: "text" },
    { key: "condition", header: "Condition", format: "text" },
    { key: "points", header: "Points", align: "right", format: "text" },
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
        intro="The first half of the dated record against the second. A crude comparison, and the quarterly series on the Trends page is the better one; this is the figure the staff tool reports and it is here for the same reading."
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
            "The two halves could not be compared."}{" "}
          It splits the record in half by row order, not by a fixed calendar
          period, so it cannot carry a confidence interval.
        </Note>
      </Section>

      <Section
        title="Organism risk scores"
        intro="A composite indicator for ordering a list for review, not a validated measure of danger. The scoring rule is below the table."
      >
        <Note tone="limit">
          The score adds points for resistance level, breadth of panel and
          volume of evidence. Those weights were chosen for this dashboard and
          have not been derived from outcome data or approved by any clinical
          governance group. Because volume contributes, an organism tested often
          scores higher than an equally resistant one tested rarely.
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
              caption="Score out of 100. The band is the score, not the resistance rate."
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
            <div className="mt-5" />
            <DataTable
              columns={scoreColumns}
              rows={scoreRows}
              searchKeys={["organism"]}
              searchLabel="Search organism"
              initialSort={{ key: "riskScore", direction: "desc" }}
            />
            <SuppressionNote suppression={slice.scores.suppression} />
          </>
        ) : (
          <Empty>No organism reaches that resistance rate.</Empty>
        )}

        <h3 className="mt-6 text-[0.98rem] font-semibold">
          How the score is calculated
        </h3>
        <DataTable columns={ruleColumns} rows={data.scoringRule} />
        <p className="text-[0.78rem] text-ink-faint">
          Maximum 100. Bands: 70 and above critical, 50 and above high, 30 and
          above moderate, below 30 low.
        </p>
      </Section>

      <Section
        title="Where the burden sits"
        intro="Resistant results as a share of all results, by specimen type. The sector is already fixed, so this is the split within it."
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
        intro={`Organism–agent pairs over 60% resistant in the last ${slice.emerging.windowDays} days of the record, on at least five results. Five results is a low floor, so the count beside each pair is the figure to read.`}
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
            <div className="mt-5" />
            <DataTable
              columns={emergingColumns}
              rows={slice.emerging.rows}
              searchKeys={["organism", "antibiotic"]}
              searchLabel="Search organism or antibiotic"
              initialSort={{ key: "resistancePercent", direction: "desc" }}
            />
            <SuppressionNote suppression={slice.emerging.suppression} />
          </>
        ) : (
          <Empty>No pattern met the emerging-resistance criteria.</Empty>
        )}
      </Section>

      <Section
        title="Where the trend is heading"
        intro="A straight line fitted to the monthly resistance rate, projected forward. Shown with the history it was fitted to."
      >
        {slice.forecast.error ? (
          <Note tone="limit">{slice.forecast.error}</Note>
        ) : (
          <>
            <Figure
              title={`Monthly resistance rate — ${sectorLabel}`}
              caption={`A month holding fewer results than the reporting floor is not plotted. Fit confidence: ${
                slice.forecast.confidence ?? "unknown"
              }.`}
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
            <div className="mt-5" />
            <Figure
              title={`Projected resistance rate — ${sectorLabel}`}
              hideTitle
            >
              <BarChart
                rows={slice.forecast.points.map((point) => ({
                  label: `${point.monthsAhead} month${
                    point.monthsAhead === 1 ? "" : "s"
                  } ahead`,
                  value: point.percent,
                }))}
                unit=""
                suffix="%"
                max={100}
                colour={OKABE_ITO.sky}
                xLabel="Projected % of results resistant"
                yLabel="Months ahead"
                labelWidth={150}
              />
            </Figure>
            <Note tone="limit">
              A linear extrapolation of{" "}
              {count(slice.forecast.history.length)} monthly points, with a
              slope of {slice.forecast.slope ?? "—"} points a month. It carries
              no interval and assumes nothing changes — not the panel, not the
              submitting laboratories, not the case mix. It is not a prediction
              of resistance in Ghana.
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
        intro="Pooled across every organism tested against the agent, so this says how the agent performed in this collection and not how it would perform against one organism."
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
        <div className="mt-5" />
        <DataTable
          columns={antibioticColumns}
          rows={slice.antibioticComparison.rows}
          searchKeys={["antibiotic"]}
          searchLabel="Search antibiotic"
          initialSort={{ key: "susceptibilityPercent", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.antibioticComparison.suppression} />
      </Section>

      <Section
        title="Susceptibility summary"
        intro="One row per organism–agent pair, with the number tested and a 95% Wilson interval. Descriptive, organism-specific, and carrying no advice."
      >
        <Note tone="limit">
          Not prescribing guidance. These are descriptive counts pooled across
          facilities, specimen types and time. They take no account of infection
          site, patient factors, local formulary or breakpoint version, and they
          are not a cumulative antibiogram. Treatment decisions need a CLSI M39
          antibiogram for the specific facility and period.
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
