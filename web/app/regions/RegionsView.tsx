"use client";

import { useMemo, useState } from "react";
import { Column, DataTable } from "@/components/DataTable";
import { Caption, Section, StatStrip, SuppressionNote } from "@/components/Chrome";
import {
  FilterBar,
  ThresholdControl,
  sectorOptions,
} from "@/components/FilterBar";
import { FoliumMap } from "@/components/FoliumMap";
import type { RegionsData } from "@/lib/data";
import { count, interval, isWithheld, numeric, titleCase } from "@/lib/format";

type RegionRow = RegionsData["regions"][number];

export function RegionsView({ data }: { data: RegionsData }) {
  // Sector here switches the *counts* only. The per-region rate is published
  // pooled across sectors, and a per-sector regional rate would rest on a few
  // dozen isolates -- too few to publish, and misleading if it were.
  const [sector, setSector] = useState("all");
  const [minIsolates, setMinIsolates] = useState(0);

  const sectors = useMemo(
    () => [...new Set(data.bySector.map((row) => row.sector))].sort(),
    [data],
  );

  const bySector = useMemo(() => {
    const index = new Map<string, Map<string, number | string | null>>();
    for (const row of data.bySector) {
      if (!index.has(row.region)) index.set(row.region, new Map());
      index.get(row.region)!.set(row.sector, row.isolates);
    }
    return index;
  }, [data]);

  const visible = useMemo(() => {
    let out = data.regions;
    if (sector !== "all") {
      out = out.filter((row) => {
        const value = bySector.get(row.region)?.get(sector);
        return typeof value === "number" ? value > 0 : value !== undefined;
      });
    }
    if (minIsolates > 0) {
      out = out.filter((row) => (numeric(row.isolates) ?? 0) >= minIsolates);
    }
    return out;
  }, [data.regions, bySector, sector, minIsolates]);

  const reporting = data.regions.filter(
    (row) => numeric(row.isolates) !== null,
  ).length;
  const withRate = data.regions.filter(
    (row) => row.percent_non_susceptible !== null,
  );
  const highest = [...withRate].sort(
    (a, b) =>
      (b.percent_non_susceptible ?? 0) - (a.percent_non_susceptible ?? 0),
  )[0];

  const columns: Column<RegionRow>[] = [
    { key: "region", header: "Region", format: "text" },
    { key: "isolates", header: "Isolates", align: "right" },
    { key: "organisms", header: "Organisms", align: "right" },
    { key: "laboratories", header: "Laboratories", align: "right" },
    {
      key: "percent_non_susceptible",
      header: "% non-susceptible",
      align: "right",
      format: "percent",
    },
    {
      key: "ci",
      header: "95% CI",
      align: "right",
      format: "text",
      value: (row) => interval(row.ci_low, row.ci_high),
    },
    ...sectors.map((sector) => ({
      key: sector,
      header: titleCase(sector),
      align: "right" as const,
      value: (row: RegionRow) => bySector.get(row.region)?.get(sector) ?? 0,
    })),
  ];

  return (
    <>
      <FilterBar
        controls={[
          {
            key: "sector",
            label: "Sector",
            value: sector,
            options: sectorOptions(["all", ...sectors]),
            note: "Switches the counts. The published rate stays pooled across sectors.",
            onChange: setSector,
          },
        ]}
        canReset={sector !== "all" || minIsolates > 0}
        onReset={() => {
          setSector("all");
          setMinIsolates(0);
        }}
        summary={`${count(visible.length)} of ${count(
          data.regions.length,
        )} regions shown.`}
      />

      <div className="flex flex-wrap gap-x-5 gap-y-3">
        <ThresholdControl
          label="Minimum isolates shown"
          value={minIsolates}
          min={0}
          max={500}
          step={10}
          onChange={setMinIsolates}
          note="Hides regions reporting fewer."
        />
      </div>

      <StatStrip
        stats={[
          { value: count(reporting), label: "Regions reporting" },
          { value: count(data.regions.length), label: "Regions in the data" },
          {
            value: highest ? highest.region : "—",
            label: "Highest non-susceptibility",
            hint: highest
              ? `${highest.percent_non_susceptible?.toFixed(1)}% — see the caveat below`
              : undefined,
          },
          { value: count(sectors.length), label: "Sectors" },
        ]}
      />

      <Section title="Isolates by region">
        <FoliumMap />
      </Section>

      <Section title="The figures">
        <DataTable
          columns={columns}
          rows={visible}
          searchKeys={["region"]}
          searchLabel="Search region"
          initialSort={{ key: "isolates", direction: "desc" }}
          pageSize={20}
        />
        <SuppressionNote suppression={data.suppression} />
        <SuppressionNote suppression={data.bySectorSuppression} />
      </Section>

      <Caption>
        A map of where specimens were collected and sent, not of where
        resistance is.
      </Caption>
    </>
  );
}
