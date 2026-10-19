"use client";

import { useMemo, useState } from "react";
import { count, isWithheld, percent } from "@/lib/format";

/**
 * A table the reader can search and sort.
 *
 * This is the interactivity that was worth having, and it is safe in a way
 * that a live filter is not: every row here was already published by the
 * export, which ran disclosure control before writing the file. Searching and
 * sorting cannot reveal a cell that was not already on the page -- unlike a
 * query against a database, where each additional filter is another attribute
 * narrowed onto fewer people.
 *
 * Sorting has to handle a column holding both numbers and the word "withheld".
 * Withheld values sort to the end regardless of direction, because they are
 * not small numbers: treating "withheld" as zero would put the suppressed
 * rows at the bottom of an ascending sort and imply they were the lowest.
 */

export type Align = "left" | "right";

export interface Column<Row> {
  key: string;
  header: string;
  align?: Align;
  /** How to render it. Defaults to a count. */
  format?: "count" | "percent" | "decimal" | "text" | "interval";
  /** Pull the value out of the row, if it is not simply `row[key]`. */
  value?: (row: Row) => unknown;
  /** Secondary text under the main value, e.g. a mechanism under a gene. */
  sub?: (row: Row) => string | null;
  width?: string;
}

function cellText<Row>(column: Column<Row>, row: Row): string {
  const raw =
    column.value !== undefined
      ? column.value(row)
      : (row as Record<string, unknown>)[column.key];
  if (isWithheld(raw)) return "withheld";
  switch (column.format) {
    case "percent":
      return percent(raw);
    case "decimal": {
      // A rate that is not a percentage -- DDD per 1,000 patient-days, mg per
      // kg of biomass. It keeps one decimal place and a thousands separator,
      // and an unmeasurable rate prints as a dash rather than as nought.
      if (raw === null || raw === undefined || raw === "") return "—";
      const value = Number(raw);
      if (!Number.isFinite(value)) return "—";
      return value.toLocaleString("en-GB", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      });
    }
    case "text":
      return raw === null || raw === undefined || raw === ""
        ? "—"
        : String(raw);
    default:
      return count(raw);
  }
}

function sortValue<Row>(column: Column<Row>, row: Row): number | string | null {
  const raw =
    column.value !== undefined
      ? column.value(row)
      : (row as Record<string, unknown>)[column.key];
  if (raw === null || raw === undefined || raw === "") return null;
  if (isWithheld(raw)) return null;
  if (typeof raw === "number") return raw;
  const asNumber = Number(raw);
  return Number.isFinite(asNumber) ? asNumber : String(raw).toLowerCase();
}

export function DataTable<Row>({
  columns,
  rows,
  searchKeys,
  searchLabel = "Search",
  initialSort,
  pageSize = 25,
  emptyMessage = "Nothing to show.",
}: {
  columns: Column<Row>[];
  rows: Row[];
  /** Columns the search box looks in. Omit to hide the box. */
  searchKeys?: string[];
  searchLabel?: string;
  initialSort?: { key: string; direction: "asc" | "desc" };
  pageSize?: number;
  emptyMessage?: string;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState(initialSort ?? null);
  const [expanded, setExpanded] = useState(false);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle || !searchKeys?.length) return rows;
    return rows.filter((row) =>
      searchKeys.some((key) =>
        String((row as Record<string, unknown>)[key] ?? "")
          .toLowerCase()
          .includes(needle),
      ),
    );
  }, [rows, query, searchKeys]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const column = columns.find((c) => c.key === sort.key);
    if (!column) return filtered;
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const left = sortValue(column, a);
      const right = sortValue(column, b);
      // Withheld and missing values go last in both directions: they are the
      // absence of a measurement, not a low one.
      if (left === null && right === null) return 0;
      if (left === null) return 1;
      if (right === null) return -1;
      if (typeof left === "number" && typeof right === "number") {
        return (left - right) * factor;
      }
      return String(left).localeCompare(String(right)) * factor;
    });
  }, [filtered, sort, columns]);

  const visible = expanded ? sorted : sorted.slice(0, pageSize);
  const hidden = sorted.length - visible.length;

  function toggleSort(key: string) {
    setSort((current) => {
      if (current?.key !== key) return { key, direction: "desc" };
      if (current.direction === "desc") return { key, direction: "asc" };
      return null;
    });
  }

  return (
    <div className="space-y-2.5">
      {searchKeys?.length ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-[0.8rem] text-ink-soft">
            <span className="sr-only">{searchLabel}</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchLabel}
              className="w-56 rounded border border-rule-strong bg-paper px-2.5 py-1.5 text-[0.84rem] text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
            />
          </label>
          <span className="text-[0.76rem] tabular-nums text-ink-faint">
            {sorted.length === rows.length
              ? `${rows.length.toLocaleString("en-GB")} rows`
              : `${sorted.length.toLocaleString("en-GB")} of ${rows.length.toLocaleString("en-GB")} rows`}
          </span>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-rule">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((column) => {
                const active = sort?.key === column.key;
                return (
                  <th
                    key={column.key}
                    style={column.width ? { width: column.width } : undefined}
                    className={column.align === "right" ? "num" : undefined}
                    aria-sort={
                      active
                        ? sort!.direction === "asc"
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(column.key)}
                      className="inline-flex items-center gap-1 uppercase tracking-[0.06em] hover:text-brand"
                    >
                      {column.header}
                      <span aria-hidden="true" className="text-[0.6rem]">
                        {active ? (sort!.direction === "asc" ? "▲" : "▼") : "⇅"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="text-ink-faint">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              visible.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => {
                    const raw =
                      column.value !== undefined
                        ? column.value(row)
                        : (row as Record<string, unknown>)[column.key];
                    const sub = column.sub?.(row);
                    return (
                      <td
                        key={column.key}
                        className={column.align === "right" ? "num" : undefined}
                      >
                        {isWithheld(raw) ? (
                          <span className="withheld">withheld</span>
                        ) : (
                          <span>{cellText(column, row)}</span>
                        )}
                        {sub ? (
                          <span className="block text-[0.74rem] text-ink-faint">
                            {sub}
                          </span>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {hidden > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="text-[0.82rem] font-semibold text-brand hover:underline"
        >
          Show {hidden.toLocaleString("en-GB")} more rows
        </button>
      ) : null}
      {expanded && sorted.length > pageSize ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="text-[0.82rem] font-semibold text-brand hover:underline"
        >
          Show fewer
        </button>
      ) : null}
    </div>
  );
}
