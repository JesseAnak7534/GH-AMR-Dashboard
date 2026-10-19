"use client";

import { useMemo, useState } from "react";
import { BarChart, ProportionBar } from "@/components/Charts";
import { FilterBar, ThresholdControl } from "@/components/FilterBar";
import { Column, DataTable } from "@/components/DataTable";
import {
  Caption,
  Empty,
  Note,
  Section,
  StatStrip,
  SuppressionNote,
} from "@/components/Chrome";
import { CustodyChain } from "@/components/CustodyChain";
import type { CustodyData, GenomicsData } from "@/lib/data";
import { count, numeric, percent } from "@/lib/format";
import { OKABE_ITO } from "@/lib/palette";

type DeterminantRow = GenomicsData["determinants"][number];
type AgentRow = { antibiotic: string; pairs: number | string | null };
type ClusterRow = GenomicsData["clusters"][number];

/**
 * The genomics section.
 *
 * The hardest page to write honestly, because the obvious framing is wrong.
 * Agreement between a gene call and a laboratory result is not an accuracy
 * score: absence of a known determinant is not absence of a mechanism. Efflux,
 * porin loss, a promoter change or a determinant outside the panel all produce
 * resistance with nothing to find. So unexplained resistance is reported as its
 * own category rather than counted as an error, and the proportion bar shows
 * all four outcomes instead of one headline percentage.
 */
export function GenomicsView({
  data,
  custody,
}: {
  data: GenomicsData;
  custody: CustodyData;
}) {
  const [mechanism, setMechanism] = useState("");
  const [minGenomes, setMinGenomes] = useState(0);

  const mechanisms = useMemo(
    () => [...new Set(data.determinants.map((row) => row.mechanism))].sort(),
    [data.determinants],
  );

  const sequenced = Number(data.coverage?.sequenced ?? 0);

  if (!sequenced) {
    return (
      <Empty>
        No sequencing results have been published yet. When they are, this page
        will show which resistance determinants were found, how often they
        explain the measured resistance, and how much of the collection has been
        sequenced.
      </Empty>
    );
  }

  const percentSequenced = numeric(data.coverage?.percent_sequenced);

  const determinants = useMemo(() => {
    let out = data.determinants;
    if (mechanism) out = out.filter((row) => row.mechanism === mechanism);
    if (minGenomes > 0) {
      out = out.filter((row) => (numeric(row.isolates) ?? 0) >= minGenomes);
    }
    return out;
  }, [data.determinants, mechanism, minGenomes]);

  const determinantChart = determinants
    .filter((row) => numeric(row.isolates) !== null)
    .slice(0, 15)
    .map((row) => ({
      label: row.determinant,
      value: row.isolates,
      colour: OKABE_ITO.purple,
    }));

  const determinantColumns: Column<DeterminantRow>[] = [
    {
      key: "determinant",
      header: "Determinant",
      format: "text",
      sub: (row) => row.mechanism,
    },
    { key: "isolates", header: "Genomes carrying it", align: "right" },
    { key: "genomes_examined", header: "Genomes examined", align: "right" },
    { key: "percent", header: "% of genomes", align: "right", format: "percent" },
    { key: "database", header: "Database", format: "text" },
  ];

  const agentColumns: Column<AgentRow>[] = [
    { key: "antibiotic", header: "Antibiotic", format: "text" },
    { key: "pairs", header: "Pairs compared", align: "right" },
  ];

  const clusterColumns: Column<ClusterRow>[] = [
    { key: "cluster_id", header: "Cluster", format: "text" },
    { key: "isolates", header: "Genomes", align: "right" },
    { key: "organism", header: "Organism(s)", format: "text" },
    { key: "sector_mix", header: "Sectors", format: "text" },
    { key: "sequence_types", header: "Sequence type(s)", format: "text" },
    { key: "labs", header: "Laboratories", align: "right" },
    { key: "span_days", header: "Days spanned", align: "right" },
  ];

  const verdictColours: Record<string, string> = {
    [data.verdictLabels?.explained ?? "explained resistance"]: OKABE_ITO.blue,
    [data.verdictLabels?.susceptibleNoGene ?? "no determinant, susceptible"]:
      OKABE_ITO.sky,
    [data.verdictLabels?.geneNotExpressed ??
    "determinant found, tested susceptible"]: OKABE_ITO.orange,
    [data.verdictLabels?.unexplained ??
    "resistance with no determinant identified"]: OKABE_ITO.vermillion,
  };

  return (
    <>
      <CustodyChain data={custody} />

      <StatStrip
        stats={[
          { value: count(sequenced), label: "Genomes" },
          {
            value: count(data.coverage?.passed_qc),
            label: "Passed quality control",
          },
          { value: count(data.coverage?.typed), label: "Typed" },
          {
            value:
              percentSequenced === null ? "—" : percent(percentSequenced),
            label: "Of all isolates",
            hint: "the limit on every figure on this page",
          },
        ]}
      />

      <FilterBar
        controls={[
          {
            key: "mechanism",
            label: "Mechanism",
            value: mechanism,
            options: [
              { value: "", label: "All mechanisms" },
              ...mechanisms.map((m) => ({ value: m, label: m })),
            ],
            note: "Markers that are not resistance determinants are labelled as such.",
            onChange: setMechanism,
          },
        ]}
        canReset={Boolean(mechanism) || minGenomes > 0}
        onReset={() => {
          setMechanism("");
          setMinGenomes(0);
        }}
        summary={`${determinants.length} of ${data.determinants.length} determinants shown.`}
      />

      <div className="flex flex-wrap gap-x-5 gap-y-3">
        <ThresholdControl
          label="Minimum genomes carrying it"
          value={minGenomes}
          min={0}
          max={1000}
          step={10}
          onChange={setMinGenomes}
          note="Hides published determinants found on fewer."
        />
      </div>

      <Section title="Resistance determinants found">
        <BarChart
          rows={determinantChart}
          unit="Genomes carrying the determinant"
          labelWidth={160}
          colour={OKABE_ITO.purple}
        />
        <DataTable
          columns={determinantColumns}
          rows={determinants}
          searchKeys={["determinant", "mechanism"]}
          searchLabel="Search gene or mechanism"
          initialSort={{ key: "isolates", direction: "desc" }}
        />
        <SuppressionNote suppression={data.determinantSuppression} />
      </Section>

      {data.concordance ? (
        <Section title="Do the genes explain the laboratory result?">
          <ProportionBar
            parts={data.concordance.verdicts.map((verdict) => ({
              label: verdict.verdict,
              value: verdict.pairs,
              colour: verdictColours[verdict.verdict] ?? OKABE_ITO.grey,
            }))}
          />

          <div className="mt-6">
            <StatStrip
              stats={[
                {
                  value: percent(
                    data.concordance.summary.agreement_percent as number,
                  ),
                  label: "Agreement",
                  hint: "across pairs the panel can speak to at all",
                },
                {
                  value: count(data.concordance.summary.explained_resistance),
                  label: "Resistance explained",
                },
                {
                  value: count(data.concordance.summary.resistance_unexplained),
                  label: "Resistance unexplained",
                  hint: "a mechanism the panel does not carry",
                },
                {
                  value: count(
                    data.concordance.summary.determinant_but_susceptible,
                  ),
                  label: "Gene present, tested susceptible",
                  hint: "not expressed, or below the breakpoint",
                },
              ]}
            />
          </div>

          <Note tone="limit">
            <strong>Absence of a gene is not absence of a mechanism.</strong>{" "}
            Efflux, porin loss or a determinant outside the panel all produce
            resistance with nothing to find. A gene on a susceptible isolate is
            the mirror image: not expressed, or below the breakpoint.
          </Note>

          <DataTable
            columns={agentColumns}
            rows={data.concordance.agents}
            searchKeys={["antibiotic"]}
            searchLabel="Search antibiotic"
            initialSort={{ key: "pairs", direction: "desc" }}
          />
          <SuppressionNote suppression={data.concordance.agentSuppression} />
        </Section>
      ) : (
        <Section title="Do the genes explain the laboratory result?">
          <Empty>
            No isolate has both a sequencing result and a susceptibility result
            for an agent the determinant panel covers, so there is nothing to
            compare.
          </Empty>
        </Section>
      )}

      <Section title="Sequence types, plasmids and virulence">
        <div className="grid gap-6 lg:grid-cols-3">
          {data.sequenceTypes?.length ? (
            <div>
              <h3 className="mb-2 text-[0.95rem] font-semibold">
                Sequence types
              </h3>
              <DataTable
                columns={[
                  { key: "sequence_type", header: "ST", format: "text" },
                  { key: "genomes", header: "Genomes", align: "right" },
                ]}
                rows={data.sequenceTypes}
                initialSort={{ key: "genomes", direction: "desc" }}
                pageSize={8}
              />
              <SuppressionNote suppression={data.sequenceTypeSuppression} />
            </div>
          ) : null}
          {[data.plasmids, data.virulence].map((block) =>
            block?.rows?.length ? (
              <div key={block.label}>
                <h3 className="mb-2 text-[0.95rem] font-semibold">
                  {block.label}
                </h3>
                <DataTable
                  columns={[
                    { key: "name", header: block.label, format: "text" },
                    { key: "genomes", header: "Genomes", align: "right" },
                    {
                      key: "percent",
                      header: "%",
                      align: "right",
                      format: "percent",
                    },
                  ]}
                  rows={block.rows}
                  initialSort={{ key: "genomes", direction: "desc" }}
                  pageSize={8}
                />
                <SuppressionNote suppression={block.suppression} />
              </div>
            ) : null,
          )}
        </div>
      </Section>

      <Section title="Genomes that look alike">
        {data.clusters.length === 0 ? (
          <Empty>
            {data.clusterSummary ??
              "No clustering has been reported on these genomes."}
          </Empty>
        ) : (
          <>
            <StatStrip
              stats={[
                { value: count(data.clustersTotal), label: "Clusters assigned" },
                { value: count(data.clusters.length), label: "Published" },
                // The withheld card appears only when something was withheld.
                // A card reading "0 Withheld" is noise, and it describes a
                // suppression setting rather than the data.
                ...(data.clustersWithheld > 0
                  ? [
                      {
                        value: count(data.clustersWithheld),
                        label: "Withheld",
                        hint: "fewer genomes than the minimum cell",
                      },
                    ]
                  : []),
                {
                  value: count(data.clustersUnassigned),
                  label: "Genomes with no cluster",
                },
              ]}
            />
            <div className="mt-4">
              <DataTable
                columns={clusterColumns}
                rows={data.clusters}
                searchKeys={["cluster_id", "organism", "sector_mix"]}
                searchLabel="Search cluster or organism"
                initialSort={{ key: "isolates", direction: "desc" }}
              />
            </div>
            {data.clustersWithheld > 0 ? (
              <Caption>
                {count(data.clustersWithheld)} clusters below the minimum cell
                are dropped whole rather than shown with their size withheld.
              </Caption>
            ) : null}
          </>
        )}
        <Note tone="limit">
          A cross-sector cluster is the strongest signal here and still not
          proof of transmission: membership is symmetric, so it shows
          relatedness, not direction.
        </Note>
      </Section>

    </>
  );
}
