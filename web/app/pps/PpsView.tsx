"use client";

import { useState } from "react";
import { Column, DataTable } from "@/components/DataTable";
import { Caption, Empty, Note, Section, StatStrip } from "@/components/Chrome";
import { FilterBar } from "@/components/FilterBar";
import type { UseData } from "@/lib/data";
import { count, percent } from "@/lib/format";

type Row = { value: string; prescriptions: number | string | null };

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

  const columns: Column<Row>[] = [
    { key: "value", header: breakdown?.label ?? "Value", format: "text" },
    { key: "prescriptions", header: "Prescriptions", align: "right" },
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
              pps.indicationDocumentedPercent === null ||
              pps.indicationDocumentedPercent === undefined
                ? "—"
                : percent(pps.indicationDocumentedPercent),
            label: "Indication documented",
          },
        ]}
      />

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
          <div className="mt-4">
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

      <Caption>
        Prevalence is pooled across surveys, not averaged over them. The
        documentation figure is about the notes, not about whether a
        prescription was appropriate.
      </Caption>
    </>
  );
}
