"use client";

import { useState } from "react";
import { BarChart } from "@/components/Charts";
import { Column, DataTable } from "@/components/DataTable";
import { Caption, Empty, Section } from "@/components/Chrome";
import { FilterBar } from "@/components/FilterBar";
import type { PooledBlock } from "@/lib/data";
import { humanise, numeric } from "@/lib/format";

type Row = Record<string, number | string | null>;

/**
 * A pooled consumption rate: numerators summed, denominators summed, one
 * divided by the other. Averaging each facility's own rate would weight a
 * ten-bed clinic like a teaching hospital.
 */
export function PooledSection({
  title,
  blocks,
  valueKey,
  unit,
  colour,
  note,
}: {
  title: string;
  blocks: PooledBlock[];
  valueKey: string;
  unit: string;
  colour: string;
  note?: string;
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
    { key: valueKey, header: unit, align: "right", format: "decimal" },
  ];

  return (
    <Section title={title}>
      {blocks.length > 1 ? (
        <FilterBar
          controls={[
            {
              key: "by",
              label: "Split by",
              value: block.by,
              options: blocks.map((b) => ({
                value: b.by,
                label: humanise(b.by),
              })),
              onChange: setBy,
            },
          ]}
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
        {note ? <Caption>{note}</Caption> : null}
      </div>
    </Section>
  );
}
