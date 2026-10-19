"use client";

import { useState } from "react";
import { BarChart } from "@/components/Charts";
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
import type { PooledBlock, UseData } from "@/lib/data";
import { count, humanise, numeric, percent } from "@/lib/format";
import { OKABE_ITO } from "@/lib/palette";

type Row = Record<string, number | string | null>;

/**
 * The antimicrobial use section.
 *
 * Every rate here is pooled: numerators summed, denominators summed, one
 * divided by the other. Averaging each facility's own rate instead would give a
 * ten-bed clinic the same weight as a teaching hospital, and it is the most
 * common way a consumption figure goes wrong -- the rates-of-rates error.
 *
 * A record carrying no usable denominator is excluded from the rate and
 * reported as excluded, never counted as zero use. Zero use and unmeasured use
 * are different claims.
 */
function PooledSection({
  title,
  intro,
  blocks,
  valueKey,
  unit,
  colour,
  note,
}: {
  title: string;
  intro: string;
  blocks: PooledBlock[];
  valueKey: string;
  unit: string;
  colour: string;
  note: string;
}) {
  const [by, setBy] = useState(blocks[0]?.by ?? "");
  const block = blocks.find((b) => b.by === by) ?? blocks[0];

  if (!block) {
    return (
      <Section title={title}>
        <Empty>No records of this kind have been published yet.</Empty>
      </Section>
    );
  }

  const chartRows = [...block.rows]
    .filter((row) => numeric(row[valueKey]) !== null)
    .sort((a, b) => (numeric(b[valueKey]) ?? 0) - (numeric(a[valueKey]) ?? 0))
    .slice(0, 14)
    .map((row) => ({
      label: String(row.group ?? ""),
      value: numeric(row[valueKey]),
      colour,
    }));

  const columns: Column<Row>[] = [
    { key: "group", header: humanise(block.by), format: "text" },
    { key: "records", header: "Records", align: "right" },
    {
      key: "records_with_denominator",
      header: "With a denominator",
      align: "right",
    },
    { key: valueKey, header: unit, align: "right", format: "decimal" },
  ];

  return (
    <Section title={title} intro={intro}>
      {blocks.length > 1 ? (
        <Segmented
          label="Split by"
          options={blocks.map((b) => b.by)}
          value={block.by}
          onChange={setBy}
        />
      ) : null}
      <div className="mt-4 space-y-4">
        <BarChart rows={chartRows} unit={unit} labelWidth={170} colour={colour} />
        <DataTable
          columns={columns}
          rows={block.rows}
          searchKeys={["group"]}
          searchLabel="Search"
          initialSort={{ key: valueKey, direction: "desc" }}
        />
        <Caption>{block.caveat}</Caption>
        <SuppressionNote suppression={block.suppression} />
        <Caption>{note}</Caption>
      </div>
    </Section>
  );
}

export function UseView({ data }: { data: UseData }) {
  const pps = data.pps;
  const breakdowns = pps.breakdowns ?? [];

  // Every hook runs before the early return below. A hook after a conditional
  // return changes the hook order between renders, which React cannot recover
  // from -- it is not a style rule.
  const [breakdownKey, setBreakdownKey] = useState(breakdowns[0]?.key ?? "");

  const hasAnything =
    data.amu.length > 0 || data.amc.length > 0 || pps.surveys > 0;
  if (!hasAnything) {
    return (
      <Empty>
        No consumption or prescribing data has been published yet. When it is,
        this page will show human and veterinary use as pooled rates with their
        denominators, and the prescribing picture from point-prevalence surveys.
      </Empty>
    );
  }

  const breakdown =
    breakdowns.find((b) => b.key === breakdownKey) ?? breakdowns[0];

  const breakdownColumns: Column<{
    value: string;
    prescriptions: number | string | null;
  }>[] = [
    { key: "value", header: breakdown?.label ?? "Value", format: "text" },
    { key: "prescriptions", header: "Prescriptions", align: "right" },
  ];

  return (
    <>
      <Note>
        Every rate here is <strong>pooled</strong>: numerators summed,
        denominators summed. Averaging facility rates would weight a clinic
        like a teaching hospital.
      </Note>

      <PooledSection
        title="Human use"
        intro="Defined daily doses per 1,000 patient-days."
        blocks={data.amu}
        valueKey="ddd_per_1000_patient_days"
        unit="DDD per 1,000 patient-days"
        colour={OKABE_ITO.blue}
        note="A defined daily dose is an assumed average adult dose, not one anyone was given. It makes volumes comparable; it does not describe any patient."
      />

      <PooledSection
        title="Veterinary use"
        intro="Milligrams of active ingredient per kilogram of biomass."
        blocks={data.amc}
        valueKey="mg_per_kg_biomass"
        unit="mg per kg biomass"
        colour={OKABE_ITO.orange}
        note="Biomass is the denominator: the same tonnage means something different across poultry than across cattle."
      />

      <Section
        title="Prescribing"
        intro="Point prevalence: how many of the patients present on the survey day were on an antibiotic, and what was prescribed."
      >
        {pps.surveys === 0 ? (
          <Empty>No point-prevalence surveys have been published yet.</Empty>
        ) : (
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
                  hint: "pooled across surveys, not averaged over them",
                },
                {
                  value:
                    pps.indicationDocumentedPercent === null ||
                    pps.indicationDocumentedPercent === undefined
                      ? "—"
                      : percent(pps.indicationDocumentedPercent),
                  label: "Indication documented",
                  hint: "about the notes, not about appropriateness",
                },
              ]}
            />

            {breakdown ? (
              <div className="mt-6 space-y-4">
                <Segmented
                  label="Break down by"
                  options={breakdowns.map((b) => b.key)}
                  value={breakdown.key}
                  onChange={setBreakdownKey}
                />
                <DataTable
                  columns={breakdownColumns}
                  rows={breakdown.rows}
                  searchKeys={["value"]}
                  searchLabel="Search"
                  initialSort={{ key: "prescriptions", direction: "desc" }}
                />
                <SuppressionNote suppression={breakdown.suppression} />
              </div>
            ) : null}

            <Caption>
              Prevalence is pooled across surveys, not averaged over them.
            </Caption>
          </>
        )}
      </Section>

      <Note>
        <strong>Method.</strong> Rates are pooled, never averaged. A record
        with no usable denominator is excluded and reported as excluded, not
        counted as zero — zero use and unmeasured use are different claims.
      </Note>
    </>
  );
}
