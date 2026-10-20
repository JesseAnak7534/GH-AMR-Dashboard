"use client";

import { useMemo, useState } from "react";
import { BarChart } from "@/components/Charts";
import { HeatGrid } from "@/components/HeatGrid";
import { Figure } from "@/components/Figure";
import { Column, DataTable } from "@/components/DataTable";
import {
  Caption,
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
import { Segmented } from "@/components/Segmented";
import type {
  AntibiogramRow,
  PriorityData,
  ResistanceData,
  ResistanceSlice,
  StratumRow,
} from "@/lib/data";
import {
  FilterManifest,
  entriesFor,
  slugFor,
  useSlice,
} from "@/lib/slices";
import { count, humanise, interval, numeric, titleCase } from "@/lib/format";

/**
 * The resistance section.
 *
 * Two kinds of filter, and they are not interchangeable.
 *
 * **Slice filters** — sector, period, region, laboratory — select a view that
 * was computed and suppressed in Python. Changing one fetches a different
 * published file. The site cannot compose a combination nobody exported, which
 * is exactly what stops a reader narrowing onto a single person.
 *
 * **Row filters** — organism, antibiotic, minimum isolates — work on the rows
 * already on the page. They can only ever show less than was published, never
 * more, so they are safe to run in the browser.
 *
 * Sectors are never pooled into one rate: a percentage mixing hospital
 * isolates with river water describes neither.
 */
export function ResistanceView({
  data,
  priority,
  filters,
}: {
  data: ResistanceData;
  priority: PriorityData;
  filters: FilterManifest;
}) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(
    sectors.includes("human") ? "human" : (sectors[0] ?? ""),
  );
  const [dimension, setDimension] = useState("");
  const [value, setValue] = useState("");
  const [organism, setOrganism] = useState("");
  const [antibiotic, setAntibiotic] = useState("");
  const [minIsolates, setMinIsolates] = useState(0);
  const [view, setView] = useState<"chart" | "matrix">("chart");
  const [listName, setListName] = useState<"who" | "ghana" | "none">("who");
  const [stratum, setStratum] = useState("");

  const base = data.slices.find((s) => s.sector === sector) ?? data.slices[0];
  const fileSlug = slugFor(filters, sector, dimension, value);
  const { data: fetched, loading, error } = useSlice<ResistanceSlice | null>(
    "resistance",
    fileSlug,
    null,
  );

  // The fetched slice replaces the antibiogram but not the strata: those are
  // published once per sector, because repeating five breakdowns under every
  // filter value would multiply the site for views nobody asked for.
  const slice: ResistanceSlice | undefined =
    fileSlug && fetched ? { ...base, ...fetched, strata: [] } : base;

  const priorityOrganisms = useMemo(() => {
    if (listName === "none") return new Set<string>();
    const entries = listName === "who" ? priority.who : priority.ghana;
    return new Set(entries.flatMap((entry) => entry.matched));
  }, [priority, listName]);

  const organisms = useMemo(
    () => [...new Set((slice?.rows ?? []).map((r) => r.organism))].sort(),
    [slice],
  );
  const antibiotics = useMemo(
    () => [...new Set((slice?.rows ?? []).map((r) => r.antibiotic))].sort(),
    [slice],
  );

  const rows = useMemo(() => {
    let out = slice?.rows ?? [];
    if (organism) out = out.filter((r) => r.organism === organism);
    if (antibiotic) out = out.filter((r) => r.antibiotic === antibiotic);
    if (minIsolates > 0) {
      out = out.filter((r) => (numeric(r.tested) ?? 0) >= minIsolates);
    }
    return out;
  }, [slice, organism, antibiotic, minIsolates]);

  const lowest = useMemo(
    () =>
      [...rows]
        .filter((row) => row.percent_susceptible !== null)
        .sort(
          (a, b) => (a.percent_susceptible ?? 0) - (b.percent_susceptible ?? 0),
        )
        .slice(0, 18)
        .map((row) => ({
          label: `${row.organism} · ${row.antibiotic}`,
          value: row.percent_susceptible,
          low: row.ci_low,
          high: row.ci_high,
          denominator: row.tested,
          colour: "#2ca02c",
        })),
    [rows],
  );

  if (!base) {
    return (
      <Empty>
        No susceptibility results have been published yet. When they are, this
        page will show the proportion of tested isolates that remained
        susceptible, with the number of isolates behind every figure.
      </Empty>
    );
  }

  // ── the filter bar ───────────────────────────────────────────────────
  const dimensionEntries = dimension
    ? entriesFor(filters, sector, dimension)
    : [];

  const controls: FilterControl[] = [
    {
      key: "sector",
      label: "Sector",
      value: sector,
      options: sectorOptions(sectors),
      note: "Never pooled: resistance means something different in each.",
      onChange: (next) => {
        setSector(next);
        setValue("");
        setOrganism("");
        setAntibiotic("");
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
        { value: "", label: `All — whole sector` },
        ...dimensionEntries.map((entry) => ({
          value: entry.value,
          label: entry.value,
          hint:
            entry.pairsReported === undefined
              ? `${entry.isolates.toLocaleString("en-GB")} isolates`
              : `${entry.isolates.toLocaleString("en-GB")} isolates, ${entry.pairsReported} rates`,
        })),
      ],
      note: meta?.note,
      onChange: setValue,
    });
  }

  controls.push(
    {
      key: "organism",
      label: "Organism",
      value: organism,
      options: [
        { value: "", label: "All organisms" },
        ...organisms.map((o) => ({ value: o, label: o })),
      ],
      onChange: setOrganism,
    },
    {
      key: "antibiotic",
      label: "Antibiotic",
      value: antibiotic,
      options: [
        { value: "", label: "All antibiotics" },
        ...antibiotics.map((a) => ({ value: a, label: a })),
      ],
      onChange: setAntibiotic,
    },
  );

  const active =
    Boolean(dimension || value || organism || antibiotic || minIsolates > 0);

  const summary = `${titleCase(sector)}${
    value ? ` · ${value}` : ""
  } — ${count(rows.length)} of ${count(slice?.rows.length ?? 0)} published rows shown, from ${count(
    slice?.isolates,
  )} isolates.`;

  const antibiogramColumns: Column<AntibiogramRow>[] = [
    { key: "organism", header: "Organism", format: "text" },
    { key: "antibiotic", header: "Antibiotic", format: "text" },
    { key: "tested", header: "Isolates tested", align: "right" },
    {
      key: "percent_susceptible",
      header: "% susceptible",
      align: "right",
      format: "percent",
    },
  ];

  const activeStratum =
    (slice?.strata ?? []).find((s) => s.key === stratum) ??
    (slice?.strata ?? [])[0];

  const stratumColumns: Column<StratumRow>[] = [
    {
      key: "stratum",
      header: humanise(activeStratum?.key ?? ""),
      format: "text",
    },
    { key: "isolates", header: "Isolates", align: "right" },
    { key: "observations", header: "Observations", align: "right" },
    {
      key: "percent_non_susceptible",
      header: "% non-susceptible",
      align: "right",
      format: "percent",
    },
    { key: "distinct_pairs", header: "Distinct pairs", align: "right" },
  ];

  return (
    <>
      <FilterBar
        controls={controls}
        summary={summary}
        canReset={active}
        onReset={() => {
          setDimension("");
          setValue("");
          setOrganism("");
          setAntibiotic("");
          setMinIsolates(0);
        }}
      />

      <div className="flex flex-wrap gap-x-5 gap-y-3">
        <ThresholdControl
          label="Minimum isolates shown"
          value={minIsolates}
          min={0}
          max={500}
          step={10}
          onChange={setMinIsolates}
          note="Hides published rows resting on fewer. It can only show less than was published."
        />
      </div>

      {loading ? (
        <p className="text-[0.85rem] text-ink-soft">Loading that view…</p>
      ) : null}
      {error ? (
        <Note tone="limit">
          That filtered view could not be loaded ({error}). The figures below
          are the unfiltered sector. This is a loading failure, not an absence
          of data.
        </Note>
      ) : null}

      <StatStrip
        stats={[
          { value: count(slice?.isolates), label: "Isolates" },
          {
            value: count(slice?.pairsReported),
            label: "Published as a rate",
            hint: `of ${count(slice?.pairsTotal)} organism–antibiotic pairs`,
          },
          {
            value: count(slice?.pairsSuppressed),
            label: "Too few to publish",
            hint: `fewer than ${data.minIsolatesForReporting} isolates`,
          },
          {
            value: value || titleCase(sector),
            label: value ? humanise(dimension) : "Sector shown",
            hint: value ? titleCase(sector) : "sectors are never pooled",
          },
        ]}
      />

      {!rows.length ? (
        <Note tone="limit">
          {slice?.pairsReported === 0 ? (
            <>
              Nothing in this view reaches {data.minIsolatesForReporting}{" "}
              isolates, so no percentage can be published — {count(
                slice?.pairsSuppressed,
              )}{" "}
              organism–antibiotic pairs were tested but fall below the floor.
              That is a statement about how much data this view holds, not
              about how much resistance is in it. Widen the filter, or see the
              counts in the organisms section.
            </>
          ) : (
            <>No published row matches those filters. Try widening them.</>
          )}
        </Note>
      ) : (
        <>
          <Section title="Susceptibility">
            <div className="flex flex-wrap gap-x-8 gap-y-3">
              <Segmented
                label="View"
                options={["chart", "matrix"]}
                value={view}
                onChange={(next) => setView(next as "chart" | "matrix")}
              />
              <Segmented
                label="Priority list"
                options={["who", "ghana", "none"]}
                value={listName}
                onChange={(next) =>
                  setListName(next as "who" | "ghana" | "none")
                }
              />
            </div>
            <div className="mt-4">
              {view === "chart" ? (
                <Figure
                  title={`Susceptibility — ${titleCase(sector)}${value ? ` · ${value}` : ""}`}
                  hideTitle
                  csv={{
                    rows,
                    columns: [
                      { key: "organism", header: "Organism" },
                      { key: "antibiotic", header: "Antibiotic" },
                      { key: "tested", header: "Isolates tested" },
                      { key: "percent_susceptible", header: "% susceptible" },
                      { key: "ci_low", header: "95% CI low" },
                      { key: "ci_high", header: "95% CI high" },
                    ],
                  }}
                >
                  <BarChart
                    rows={lowest}
                    unit="% susceptible (95% CI, isolates tested in brackets)"
                    labelWidth={290}
                    max={100}
                    suffix="%"
                    colour="#2ca02c"
                  />
                </Figure>
              ) : (
                <Figure
                  title={`Susceptibility matrix — ${titleCase(sector)}`}
                  hideTitle
                  downloadable={false}
                  csv={{
                    rows,
                    columns: [
                      { key: "organism", header: "Organism" },
                      { key: "antibiotic", header: "Antibiotic" },
                      { key: "tested", header: "Isolates tested" },
                      { key: "percent_susceptible", header: "% susceptible" },
                    ],
                  }}
                >
                  <HeatGrid
                    cells={rows.map((row) => ({
                      organism: row.organism,
                      antibiotic: row.antibiotic,
                      percent: row.percent_susceptible,
                      tested: row.tested,
                      low: row.ci_low,
                      high: row.ci_high,
                    }))}
                    highlightOrganisms={priorityOrganisms}
                  />
                </Figure>
              )}
            </div>
          </Section>

          <Section title="Every published combination">
            <DataTable
              columns={antibiogramColumns}
              rows={rows}
              searchKeys={["organism", "antibiotic"]}
              searchLabel="Search organism or antibiotic"
              initialSort={{ key: "tested", direction: "desc" }}
              downloadName={`antibiogram ${sector}${value ? " " + value : ""}`}
            />
            <SuppressionNote suppression={slice?.suppression} />
          </Section>
        </>
      )}

      {activeStratum ? (
        <Section title="Resistance by setting">
          <Segmented
            label="Split by"
            options={(slice?.strata ?? []).map((s) => s.key)}
            value={activeStratum.key}
            onChange={setStratum}
            labels={Object.fromEntries(
              (slice?.strata ?? []).map((s) => [s.key, s.label]),
            )}
          />
          <div className="mt-4">
            <BarChart
              rows={[...activeStratum.rows]
                .filter((row) => row.percent_non_susceptible !== null)
                .sort(
                  (a, b) =>
                    (b.percent_non_susceptible ?? 0) -
                    (a.percent_non_susceptible ?? 0),
                )
                .map((row) => ({
                  label: row.stratum,
                  value: row.percent_non_susceptible,
                  low: row.ci_low,
                  high: row.ci_high,
                  denominator: row.observations,
                  colour: "#d62728",
                }))}
              unit="% non-susceptible (95% CI, results in brackets)"
              labelWidth={230}
              max={100}
              suffix="%"
              colour="#d62728"
            />
          </div>
        </Section>
      ) : null}

    </>
  );
}
