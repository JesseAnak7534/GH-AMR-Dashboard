"use client";

import { useMemo, useState } from "react";
import { BarChart } from "@/components/Charts";
import { Figure } from "@/components/Figure";
import { Column, DataTable } from "@/components/DataTable";
import {
  Empty,
  Note,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import {
  FilterBar,
  FilterControl,
  ThresholdControl,
  sectorOptions,
} from "@/components/FilterBar";
import type { OrganismData, OrganismSlice } from "@/lib/data";
import { FilterManifest, entriesFor, slugFor, useSlice } from "@/lib/slices";
import { count, numeric, percent, titleCase } from "@/lib/format";

type SpecimenRow = { specimenType: string; isolates: number | string | null };

/**
 * The organisms section.
 *
 * Counts, not rates — which is why filtering works here where it barely does
 * on the resistance page. A region holding 150 isolates cannot support a
 * published percentage, but it can perfectly well report which organisms those
 * 150 were. It is also why this page offers an "all sectors" view: an animal
 * isolate plus a human isolate is genuinely two isolates, whereas their
 * susceptibility percentages do not average into anything.
 */
export function OrganismsView({
  data,
  filters,
}: {
  data: OrganismData;
  filters: FilterManifest;
}) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(sectors[0] ?? "all");
  const [dimension, setDimension] = useState("");
  const [value, setValue] = useState("");
  const [minIsolates, setMinIsolates] = useState(0);

  const base = data.slices.find((s) => s.sector === sector) ?? data.slices[0];
  const fileSlug = slugFor(filters, sector, dimension, value);
  const { data: fetched, loading, error } = useSlice<OrganismSlice | null>(
    "organisms",
    fileSlug,
    null,
  );
  const slice = fileSlug && fetched ? fetched : base;

  const rows = useMemo(() => {
    const all = slice?.rows ?? [];
    if (minIsolates <= 0) return all;
    return all.filter((row) => (numeric(row.isolates) ?? 0) >= minIsolates);
  }, [slice, minIsolates]);

  if (!base) {
    return (
      <Empty>
        No isolates have been published yet. When they are, this page will show
        which organisms are being identified and the specimens they came from.
      </Empty>
    );
  }

  const controls: FilterControl[] = [
    {
      key: "sector",
      label: "Sector",
      value: sector,
      options: sectorOptions(sectors),
      note: "Counts may be pooled across sectors; rates never are.",
      onChange: (next) => {
        setSector(next);
        setValue("");
      },
    },
    {
      key: "dimension",
      label: "Narrow by",
      value: dimension,
      options: [
        { value: "", label: "Whole sector" },
        ...filters.dimensions.map((d) => ({
          value: d.key,
          label: d.label,
          disabled: entriesFor(filters, sector, d.key).length === 0,
        })),
      ],
      note: "One at a time — each combination is a published file.",
      onChange: (next) => {
        setDimension(next);
        setValue("");
      },
    },
  ];

  if (dimension) {
    const meta = filters.dimensions.find((d) => d.key === dimension);
    controls.push({
      key: "value",
      label: meta?.label ?? "Value",
      value,
      options: [
        { value: "", label: "All — whole sector" },
        ...entriesFor(filters, sector, dimension).map((entry) => ({
          value: entry.value,
          label: entry.value,
          hint: `${entry.isolates.toLocaleString("en-GB")} isolates`,
        })),
      ],
      note: meta?.note,
      onChange: setValue,
    });
  }

  const chartRows = rows
    .filter((row) => numeric(row.isolates) !== null)
    .map((row) => ({
      label: row.organism,
      value: row.isolates,
      colour: slice?.colour,
    }));

  const specimenColumns: Column<SpecimenRow>[] = [
    { key: "specimenType", header: "Specimen type", format: "text" },
    { key: "isolates", header: "Isolates", align: "right" },
  ];

  return (
    <>
      <FilterBar
        controls={controls}
        canReset={Boolean(dimension || value || minIsolates > 0)}
        onReset={() => {
          setDimension("");
          setValue("");
          setMinIsolates(0);
        }}
        summary={`${sector === "all" ? "All sectors" : titleCase(sector)}${
          value ? ` · ${value}` : ""
        } — ${count(rows.length)} of ${count(slice?.rows.length ?? 0)} organisms shown.`}
      />

      <div className="flex flex-wrap gap-x-5 gap-y-3">
        <ThresholdControl
          label="Minimum isolates shown"
          value={minIsolates}
          min={0}
          max={500}
          step={10}
          onChange={setMinIsolates}
          note="Hides published rows resting on fewer."
        />
      </div>

      {loading ? (
        <p className="text-[0.85rem] text-ink-soft">Loading that view…</p>
      ) : null}
      {error ? (
        <Note tone="limit">
          That filtered view could not be loaded ({error}). The figures below
          are the unfiltered sector.
        </Note>
      ) : null}

      <StatStrip
        stats={[
          { value: count(slice?.organisms), label: "Distinct organisms" },
          { value: count(slice?.isolates), label: "Isolates" },
          { value: count(slice?.laboratories), label: "Laboratories" },
          {
            value:
              slice?.sterileSitePercent === null ||
              slice?.sterileSitePercent === undefined
                ? "—"
                : percent(slice.sterileSitePercent),
            label: "From a sterile site",
            hint: "blood, CSF and other normally sterile sites",
          },
        ]}
      />

      {!rows.length ? (
        <Empty>No organism in this view matches those filters.</Empty>
      ) : (
        <>
          <Section title="Most frequently isolated">
            <Figure
              title={`Most frequently isolated — ${sector === "all" ? "all sectors" : titleCase(sector)}`}
              hideTitle
            >
              <BarChart
                rows={chartRows}
                unit=""
                xLabel="Isolates"
                yLabel="Organism"
                colour={slice?.colour}
              />
            </Figure>
          </Section>

          <SuppressionNote suppression={slice?.suppression} />
        </>
      )}

      <Section title="Specimen types behind these isolates">
        <DataTable
          columns={specimenColumns}
          rows={slice?.specimenTypes ?? []}
          searchKeys={["specimenType"]}
          searchLabel="Search specimen type"
          initialSort={{ key: "isolates", direction: "desc" }}
        />
        <SuppressionNote suppression={slice?.specimenTypeSuppression} />
      </Section>

    </>
  );
}
