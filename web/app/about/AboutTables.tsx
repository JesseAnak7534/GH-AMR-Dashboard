"use client";

import { Column, DataTable } from "@/components/DataTable";
import type { Cell } from "@/lib/data";
import { numeric, percent } from "@/lib/format";

type Row = Record<string, Cell>;

/**
 * Field completeness.
 *
 * The one table on the site where a low number is the finding. It is shown as
 * a proportion with the counts beside it, and with the platform's own verdict
 * in the last column, because "complete" and "sparse" are judgements the
 * analysis layer makes against stated thresholds rather than something the
 * reader should have to infer from a percentage.
 */
export function CompletenessTable({ rows }: { rows: Row[] }) {
  if (!rows.length) {
    return (
      <p className="text-[0.86rem] text-ink-faint">
        No completeness report is available for this data.
      </p>
    );
  }

  const columns: Column<Row>[] = [
    { key: "Field", header: "Field", format: "text" },
    { key: "Scope", header: "Scope", format: "text" },
    { key: "Recorded", header: "Recorded", align: "right" },
    { key: "Of", header: "Of", align: "right" },
    {
      key: "Percent",
      header: "Complete",
      align: "right",
      format: "text",
      value: (row) => {
        const value = numeric(row.Percent);
        return value === null ? "—" : percent(value);
      },
    },
    { key: "Status", header: "Verdict", format: "text" },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      searchKeys={["Field", "Scope", "Status"]}
      searchLabel="Search field"
      initialSort={{ key: "Percent", direction: "asc" }}
      pageSize={20}
    />
  );
}

/**
 * The metric dictionary.
 *
 * Each row names a metric's numerator, denominator, period, deduplication rule
 * and standard, and then two things most dashboards leave out: what the metric
 * is for, and what it must not be used for. The second is the useful one. A
 * cumulative antibiogram is a stewardship instrument, not a prescription for a
 * patient in front of you, and a figure published without that line will be
 * used as one.
 */
export function MetricTable({ rows }: { rows: Row[] }) {
  const columns: Column<Row>[] = [
    {
      key: "Metric",
      header: "Metric",
      format: "text",
      sub: (row) => (row.Unit ? String(row.Unit) : null),
    },
    { key: "Numerator", header: "Numerator", format: "text" },
    { key: "Denominator", header: "Denominator", format: "text" },
    { key: "Deduplication", header: "Deduplication", format: "text" },
    { key: "Suppression", header: "Suppression", format: "text" },
    {
      key: "Not to be used for",
      header: "Not to be used for",
      format: "text",
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      searchKeys={["Metric"]}
      searchLabel="Search metric"
      pageSize={10}
    />
  );
}
