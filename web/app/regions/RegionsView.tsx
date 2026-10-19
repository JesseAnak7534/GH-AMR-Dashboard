"use client";

import { useMemo } from "react";
import { Column, DataTable } from "@/components/DataTable";
import { Note, Section, StatStrip, SuppressionNote } from "@/components/Chrome";
import { RegionMap } from "@/components/RegionMap";
import type { RegionsData } from "@/lib/data";
import { count, interval, isWithheld, numeric, titleCase } from "@/lib/format";

type RegionRow = RegionsData["regions"][number];

export function RegionsView({ data }: { data: RegionsData }) {
  const points = useMemo(
    () =>
      data.regions
        .map((row) => {
          const centroid = data.centroids[row.region];
          if (!centroid) return null;
          return {
            region: row.region,
            isolates: row.isolates,
            percentNonSusceptible: row.percent_non_susceptible,
            lat: centroid.lat,
            lon: centroid.lon,
          };
        })
        .filter((p): p is NonNullable<typeof p> => p !== null),
    [data],
  );

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

      <Note tone="limit">
        A map of where specimens were collected and sent, not of where
        resistance is. A region with a large laboratory reports more isolates
        whatever is happening there.
      </Note>

      <Section title="Isolates by region">
        <RegionMap points={points} />
      </Section>

      <Section title="The figures">
        <DataTable
          columns={columns}
          rows={data.regions}
          searchKeys={["region"]}
          searchLabel="Search region"
          initialSort={{ key: "isolates", direction: "desc" }}
          pageSize={20}
        />
        <SuppressionNote suppression={data.suppression} />
        <SuppressionNote suppression={data.bySectorSuppression} />
      </Section>

      <Note>
        <strong>Method.</strong> {data.deduplication} The per-region rate pools
        every organism and agent, so it compares regions only where similar
        panels were tested.
      </Note>
    </>
  );
}
