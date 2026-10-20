"use client";

import { useMemo, useState } from "react";
import { ProportionBar, StackedBars } from "@/components/Charts";
import { Column, DataTable } from "@/components/DataTable";
import {
  Caption,
  Empty,
  Note,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import { FilterBar, sectorOptions } from "@/components/FilterBar";
import type { MdrData } from "@/lib/data";
import { count, isWithheld, percent, titleCase } from "@/lib/format";
import { OKABE_ITO } from "@/lib/palette";

const CLASSIFICATION_COLOUR: Record<string, string> = {
  XDR: OKABE_ITO.black,
  MDR: OKABE_ITO.vermillion,
  "Not MDR": OKABE_ITO.blue,
  "Insufficient testing": OKABE_ITO.grey,
};

export function MdrView({ data }: { data: MdrData }) {
  const names = data.slices.map((s) => s.name);
  const [name, setName] = useState(names[0] ?? "all");
  const slice = data.slices.find((s) => s.name === name) ?? data.slices[0];

  const grid = useMemo(() => {
    if (!slice) return { organisms: [], classes: [], cells: new Map() };
    const classes = ["MDR", "XDR", "Not MDR", "Insufficient testing"];
    const cells = new Map<string, number | string | null>();
    const totals = new Map<string, number>();
    for (const row of slice.byOrganism) {
      cells.set(`${row.organism}||${row.classification}`, row.isolates);
      if (typeof row.isolates === "number") {
        totals.set(row.organism, (totals.get(row.organism) ?? 0) + row.isolates);
      }
    }
    const organisms = [...new Set(slice.byOrganism.map((r) => r.organism))].sort(
      (a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0),
    );
    return { organisms, classes, cells };
  }, [slice]);

  if (!slice) {
    return <Empty>No isolates could be classified yet.</Empty>;
  }


  const parts = slice.counts
    .filter((row) => typeof row.isolates === "number")
    .map((row) => ({
      label: row.classification,
      value: row.isolates as number,
      colour: CLASSIFICATION_COLOUR[row.classification] ?? OKABE_ITO.grey,
    }));

  const organismColumns: Column<{ organism: string }>[] = [
    { key: "organism", header: "Organism", format: "text" },
    ...grid.classes.map((classification) => ({
      key: classification,
      header: classification,
      align: "right" as const,
      value: (row: { organism: string }) =>
        grid.cells.get(`${row.organism}||${classification}`) ?? 0,
    })),
  ];

  return (
    <>
      <FilterBar
        controls={[
          {
            key: "sector",
            label: "Sector",
            value: name,
            options: sectorOptions(names),
            note: "Classification is per isolate, so sectors can be shown together.",
            onChange: setName,
          },
        ]}
        summary={`${
          name === "all" ? "All sectors" : titleCase(name)
        } \u2014 ${count(slice.classifiable)} of ${count(
          slice.isolates,
        )} isolates had enough categories tested to classify.`}
      />

      <StatStrip
        stats={[
          { value: count(slice.isolates), label: "Isolates" },
          {
            value: count(slice.classifiable),
            label: "Classifiable",
            hint: "three or more categories tested",
          },
          {
            value: percent(slice.percent?.MDR ?? null),
            label: "MDR",
            hint: "of classifiable isolates",
          },
          {
            value: percent(slice.percent?.XDR ?? null),
            label: "XDR",
            hint: "of classifiable isolates",
          },
        ]}
      />

      <Note tone="limit">
        {count(slice.insufficient)} isolates were tested against too few
        categories to answer the question and are counted as{" "}
        <strong>insufficient testing</strong>, not as &ldquo;not MDR&rdquo;.
        Calling them not-MDR would make a laboratory with a small panel look
        like one with little resistance.
      </Note>

      <Section title="How the isolates classify">
        <ProportionBar parts={parts} />
        <SuppressionNote suppression={slice.countsSuppression} />
      </Section>

      <Section title="By organism">
        <StackedBars
          rows={grid.organisms.map((organism) => ({
            label: organism,
            parts: Object.fromEntries(
              grid.classes.map((c) => [
                c,
                grid.cells.get(`${organism}||${c}`) ?? 0,
              ]),
            ),
          }))}
          series={grid.classes}
          colours={CLASSIFICATION_COLOUR}
          labelWidth={200}
        />
        <div className="mt-5" />
        <DataTable
          columns={organismColumns}
          rows={grid.organisms.map((organism) => ({ organism }))}
          searchKeys={["organism"]}
          searchLabel="Search organism"
          initialSort={{ key: "MDR", direction: "desc" }}
        />
        <SuppressionNote suppression={slice.byOrganismSuppression} />
      </Section>

      <Section title="The definitions">
        <dl className="divide-y divide-rule rounded-lg border border-rule">
          {Object.entries(data.definitions).map(([term, meaning]) => (
            <div key={term} className="flex flex-wrap gap-x-4 px-4 py-2.5">
              <dt className="w-40 shrink-0 text-[0.85rem] font-semibold">
                {term}
              </dt>
              <dd className="flex-1 text-[0.85rem] text-ink-soft">{meaning}</dd>
            </div>
          ))}
        </dl>
      </Section>

    </>
  );
}
