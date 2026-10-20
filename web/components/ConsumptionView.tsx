"use client";

import { useMemo, useState } from "react";
import { BarChart } from "@/components/Charts";
import { Donut } from "@/components/Donut";
import { TrendChart } from "@/components/TrendChart";
import { Column, DataTable } from "@/components/DataTable";
import { Caption, Empty, Section, StatStrip } from "@/components/Chrome";
import { FilterBar } from "@/components/FilterBar";
import type { PooledBlock } from "@/lib/data";
import { count, humanise, numeric } from "@/lib/format";

type Row = Record<string, number | string | null>;

/**
 * Consumption, shared by the human (AMU) and veterinary (AMC) pages.
 *
 * Three views of the same pooled figures, because the old pages had three and
 * each answers a different question: how much is used where, how it has moved
 * over the reporting periods, and what the mix is between a handful of named
 * categories.
 *
 * Every rate is pooled -- numerators summed, denominators summed, one divided
 * by the other. Averaging each facility's own rate would weight a ten-bed
 * clinic like a teaching hospital, which is the commonest way a consumption
 * figure goes wrong.
 */
export function ConsumptionView({
  blocks,
  valueKey,
  unit,
  colour,
  volumeKey,
  volumeUnit,
  volumeShort,
  note,
  compositionKeys = [],
}: {
  blocks: PooledBlock[];
  valueKey: string;
  unit: string;
  colour: string;
  /** The raw volume behind the rate, shown beside it. */
  volumeKey?: string;
  volumeUnit?: string;
  /** Short form of the unit, for places with no room — a ring's centre. */
  volumeShort?: string;
  note?: string;
  /** Dimensions worth drawing as a ring rather than as bars. */
  compositionKeys?: string[];
}) {
  const comparable = blocks.filter((b) => b.by !== "report_period");
  const period = blocks.find((b) => b.by === "report_period");
  const [by, setBy] = useState(comparable[0]?.by ?? "");
  const block = comparable.find((b) => b.by === by) ?? comparable[0];

  const compositions = useMemo(
    () => blocks.filter((b) => compositionKeys.includes(b.by)),
    [blocks, compositionKeys],
  );

  if (!blocks.length) {
    return <Empty>No records of this kind have been published yet.</Empty>;
  }

  const totalRecords = block
    ? block.rows.reduce((sum, row) => sum + (numeric(row.records) ?? 0), 0)
    : 0;
  const withDenominator = block
    ? block.rows.reduce(
        (sum, row) => sum + (numeric(row.records_with_denominator) ?? 0),
        0,
      )
    : 0;
  const totalVolume =
    volumeKey && block
      ? block.rows.reduce((sum, row) => sum + (numeric(row[volumeKey]) ?? 0), 0)
      : null;

  const columns: Column<Row>[] = [
    { key: "group", header: humanise(block?.by ?? ""), format: "text" },
    { key: "records", header: "Records", align: "right" },
    { key: valueKey, header: unit, align: "right", format: "decimal" },
  ];
  if (volumeKey) {
    columns.splice(2, 0, {
      key: volumeKey,
      header: volumeUnit ?? humanise(volumeKey),
      align: "right",
      format: "decimal",
    });
  }

  return (
    <>
      <StatStrip
        stats={[
          {
            value: totalVolume === null ? "—" : count(Math.round(totalVolume)),
            label: volumeUnit ?? "Total quantity",
          },
          { value: count(totalRecords), label: "Reports" },
          {
            value: count(withDenominator),
            label: "With a usable denominator",
            hint: "the rest are excluded from the rate, not counted as zero",
          },
          {
            value: count(period?.rows.length ?? 0),
            label: "Reporting periods",
          },
        ]}
      />

      {block ? (
        <Section title={unit}>
          {comparable.length > 1 ? (
            <FilterBar
              controls={[
                {
                  key: "by",
                  label: "Split by",
                  value: block.by,
                  options: comparable.map((b) => ({
                    value: b.by,
                    label: humanise(b.by),
                  })),
                  note: "Each split is pooled separately; they do not combine.",
                  onChange: setBy,
                },
              ]}
            />
          ) : null}
          <div className="mt-4 space-y-5">
            <BarChart
              rows={[...block.rows]
                .filter((row) => numeric(row[valueKey]) !== null)
                .sort(
                  (a, b) =>
                    (numeric(b[valueKey]) ?? 0) - (numeric(a[valueKey]) ?? 0),
                )
                .slice(0, 14)
                .map((row) => ({
                  label: String(row.group ?? ""),
                  value: numeric(row[valueKey]),
                  denominator: volumeKey ? row[volumeKey] : row.records,
                  colour,
                }))}
              unit={`${unit}${
                volumeUnit ? ` (${volumeUnit.toLowerCase()} in brackets)` : ""
              }`}
              labelWidth={220}
              decimals={1}
            />
            <DataTable
              columns={columns}
              rows={block.rows}
              searchKeys={["group"]}
              searchLabel="Search"
              initialSort={{ key: valueKey, direction: "desc" }}
            />
            <Caption>{block.caveat}</Caption>
          </div>
        </Section>
      ) : null}

      {period && period.rows.length > 1 ? (
        <Section title="Over the reporting periods">
          <TrendChart
            series={[
              {
                label: unit,
                colour,
                points: [...period.rows]
                  .sort((a, b) =>
                    String(a.group ?? "").localeCompare(String(b.group ?? "")),
                  )
                  .map((row) => ({
                    period: String(row.group ?? ""),
                    value: numeric(row[valueKey]),
                    low: null,
                    high: null,
                    denominator: row.records,
                  })),
              },
            ]}
            unit={unit}
            denominatorLabel="records"
            axisMax={null}
          />
        </Section>
      ) : null}

      {compositions.map((composition) => {
        const total = composition.rows.reduce(
          (sum, row) =>
            sum + (numeric(volumeKey ? row[volumeKey] : row.records) ?? 0),
          0,
        );
        return (
          <Section key={composition.by} title={humanise(composition.by)}>
            <Donut
              parts={composition.rows
                .map((row) => ({
                  label: String(row.group ?? ""),
                  value:
                    numeric(volumeKey ? row[volumeKey] : row.records) ?? 0,
                }))
                .filter((part) => part.value > 0)}
              centreValue={count(Math.round(total))}
              centreLabel={volumeShort ?? volumeUnit ?? "records"}
            />
          </Section>
        );
      })}

      {note ? <Caption>{note}</Caption> : null}
    </>
  );
}
