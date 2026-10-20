"use client";

import { useState } from "react";
import { BarChart } from "@/components/Charts";
import { Donut } from "@/components/Donut";
import { Gauge } from "@/components/Gauge";
import { Figure } from "@/components/Figure";
import { Column, DataTable } from "@/components/DataTable";
import { Caption, Empty, Section, StatStrip } from "@/components/Chrome";
import { FilterBar } from "@/components/FilterBar";
import type { UseData } from "@/lib/data";
import { count, numeric, percent } from "@/lib/format";
import { OKABE_ITO } from "@/lib/palette";

type Row = { value: string; prescriptions: number | string | null };
type WardRow = {
  ward: string;
  prescriptions: number | string | null;
  median_duration: number | null;
};

/**
 * Point prevalence surveys.
 *
 * Prevalence is pooled across surveys rather than averaged over them, so a
 * 400-bed hospital does not count the same as a 40-bed one.
 */
export function PpsView({ data }: { data: UseData }) {
  const pps = data.pps;
  const breakdowns = pps.breakdowns ?? [];
  const [key, setKey] = useState(breakdowns[0]?.key ?? "");

  if (!pps.surveys) {
    return <Empty>No point-prevalence surveys have been published yet.</Empty>;
  }

  const breakdown = breakdowns.find((b) => b.key === key) ?? breakdowns[0];
  const route = breakdowns.find((b) => b.key === "route");

  const columns: Column<Row>[] = [
    { key: "value", header: breakdown?.label ?? "Value", format: "text" },
    { key: "prescriptions", header: "Prescriptions", align: "right" },
  ];

  const wardColumns: Column<WardRow>[] = [
    { key: "ward", header: "Ward", format: "text" },
    { key: "prescriptions", header: "Prescriptions", align: "right" },
    {
      key: "median_duration",
      header: "Median days",
      align: "right",
      format: "decimal",
    },
  ];

  return (
    <>
      <StatStrip
        stats={[
          { value: count(pps.surveys), label: "Surveys" },
          { value: count(pps.patients), label: "Patients surveyed" },
          {
            value:
              pps.prevalencePercent === null ||
              pps.prevalencePercent === undefined
                ? "—"
                : percent(pps.prevalencePercent),
            label: "On an antibiotic",
          },
          {
            value:
              pps.durationMedianDays === null ||
              pps.durationMedianDays === undefined
                ? "—"
                : `${pps.durationMedianDays} days`,
            label: "Median course length",
          },
        ]}
      />

      <Section title="Prescribing quality">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Gauge
            value={pps.guidelineCompliantPercent ?? null}
            label="Guideline compliance"
            hint="of prescriptions"
            colour={OKABE_ITO.green}
          />
          <Gauge
            value={pps.indicationDocumentedPercent ?? null}
            label="Indication documented"
            hint="in the notes"
            colour={OKABE_ITO.blue}
          />
          {route ? (
            <div className="rounded-lg border border-rule bg-paper px-4 py-3">
              <p className="mb-1 text-[0.88rem] font-semibold">
                Route of administration
              </p>
              <Donut
                size={132}
                parts={route.rows
                  .map((row) => ({
                    label: row.value,
                    value: numeric(row.prescriptions) ?? 0,
                  }))
                  .filter((part) => part.value > 0)}
                colours={[OKABE_ITO.blue, OKABE_ITO.orange, OKABE_ITO.sky]}
              />
            </div>
          ) : null}
        </div>
      </Section>

      {breakdown ? (
        <Section title="What was prescribed">
          <FilterBar
            controls={[
              {
                key: "breakdown",
                label: "Break down by",
                value: breakdown.key,
                options: breakdowns.map((b) => ({
                  value: b.key,
                  label: b.label,
                })),
                onChange: setKey,
              },
            ]}
          />
          <div className="mt-4 space-y-5">
            <Figure
              title={`Prescribing by ${breakdown.label.toLowerCase()}`}
              hideTitle
            >
              <BarChart
                rows={[...breakdown.rows]
                  .sort(
                    (a, b) =>
                      (numeric(b.prescriptions) ?? 0) -
                      (numeric(a.prescriptions) ?? 0),
                  )
                  .slice(0, 14)
                  .map((row) => ({
                    label: row.value,
                    value: row.prescriptions,
                    colour: "#8a6a22",
                  }))}
                unit=""
                xLabel="Prescriptions"
                yLabel={breakdown.label}
                labelWidth={230}
              />
            </Figure>
            <DataTable
              columns={columns}
              rows={breakdown.rows}
              searchKeys={["value"]}
              searchLabel="Search"
              initialSort={{ key: "prescriptions", direction: "desc" }}
            />
          </div>
        </Section>
      ) : null}

      {pps.wards?.length ? (
        <Section title="By ward">
          <BarChart
            rows={pps.wards.map((ward) => ({
              label: ward.ward,
              value: ward.prescriptions,
              colour: OKABE_ITO.purple,
            }))}
            unit=""
            xLabel="Prescriptions"
            yLabel="Ward"
            labelWidth={200}
          />
          <DataTable
            columns={wardColumns}
            rows={pps.wards}
          />
        </Section>
      ) : null}

      {pps.duration?.length ? (
        <Section title="Length of course">
          <BarChart
            rows={pps.duration.map((row) => ({
              label: `${row.days} day${row.days === 1 ? "" : "s"}`,
              value: row.prescriptions,
              colour: OKABE_ITO.vermillion,
            }))}
            unit=""
            xLabel="Prescriptions"
            yLabel="Course length"
            labelWidth={90}
          />
        </Section>
      ) : null}

    </>
  );
}
