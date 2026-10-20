"use client";

import { BarChart } from "@/components/Charts";
import { Caption, Section, StatStrip } from "@/components/Chrome";
import type { CustodyData } from "@/lib/data";
import { count, percent } from "@/lib/format";

/**
 * The chain of custody, from patient to genome.
 *
 * This is the thing the platform is built around: a resistance result or a
 * genome is only actionable if it can be followed back to the specimen, the
 * encounter and the person it came from. A figure with no provenance is a
 * figure nobody can check.
 *
 * Shown as counts of links, never as links. The chain is demonstrated to be
 * intact without a single identifier reaching the page — which is the point:
 * traceability and anonymity are not in tension here, because what is
 * published is the *shape* of the chain rather than its contents.
 *
 * Where a link is incomplete the page says so. A stage that cannot be joined
 * backwards is where the chain breaks, and hiding it would make the platform
 * look more complete than it is.
 */

const STAGE_COLOUR = [
  "#1d4d43",
  "#246055",
  "#2c7366",
  "#348678",
  "#3c998a",
  "#45ac9c",
];

export function CustodyChain({
  data,
  compact = false,
}: {
  data: CustodyData;
  compact?: boolean;
}) {
  const stages = data.stages ?? [];
  if (!stages.length) return null;

  const linkFor = (table: string): { of: number; linked: number } | null => {
    const l = data.linked ?? {};
    switch (table) {
      case "specimens":
        return { of: stageCount("specimens"), linked: l.specimens_to_subject ?? 0 };
      case "isolates":
        return { of: stageCount("isolates"), linked: l.isolates_to_specimen ?? 0 };
      case "phenotypes":
        return { of: stageCount("phenotypes"), linked: l.phenotypes_to_isolate ?? 0 };
      case "genomic_results":
        return { of: stageCount("genomic_results"), linked: l.genomes_to_isolate ?? 0 };
      default:
        return null;
    }
  };

  function stageCount(table: string): number {
    return stages.find((s) => s.table === table)?.records ?? 0;
  }

  return (
    <Section title="Chain of custody">
      <StatStrip
        stats={[
          {
            value: percent(data.percentGenomesTraceable),
            label: "Genomes traceable to a patient",
            hint: `${count(data.genomesTraceable)} of ${count(data.genomes)}`,
          },
          {
            value: count(data.totalEvents),
            label: "Custody events recorded",
            hint: "every handover is appended, never overwritten",
          },
          {
            value: count(stageCount("specimens")),
            label: "Specimens in the chain",
          },
          {
            value: count(stageCount("subjects")),
            label: "Patients or sources",
            hint: "pseudonymised",
          },
        ]}
      />

      <ol className="mt-5 space-y-2">
        {stages.map((stage, index) => {
          const link = linkFor(stage.table);
          const complete =
            link && link.of > 0 ? (100 * link.linked) / link.of : null;
          return (
            <li
              key={stage.table}
              className="relative rounded-lg border border-rule bg-paper px-4 py-3 pl-5"
            >
              <span
                aria-hidden="true"
                className="absolute left-0 top-0 h-full w-[4px] rounded-l-lg"
                style={{ background: STAGE_COLOUR[index] ?? "#45ac9c" }}
              />
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <span className="text-[0.95rem] font-semibold">
                  <span className="mr-2 text-ink-faint">{index + 1}</span>
                  {stage.label}
                </span>
                <span className="text-[1.05rem] font-bold tabular-nums">
                  {count(stage.records)}
                </span>
              </div>
              {!compact ? (
                <p className="mt-0.5 text-[0.8rem] leading-snug text-ink-soft">
                  {stage.note}
                </p>
              ) : null}
              {link ? (
                <p className="mt-1 text-[0.78rem] text-ink-faint">
                  {complete !== null && complete >= 99.95 ? (
                    <>Every record links back to the stage above it.</>
                  ) : (
                    <>
                      {count(link.linked)} of {count(link.of)} link back to the
                      stage above
                      {complete !== null ? ` (${percent(complete)})` : ""}.
                    </>
                  )}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>

      {data.events?.length ? (
        <div className="mt-6">
          <h3 className="mb-2 text-[0.95rem] font-semibold">
            Custody events by type
          </h3>
          <BarChart
            rows={data.events.map((event) => ({
              label: event.event.replace(/_/g, " "),
              value: event.events,
              colour: "#1d4d43",
            }))}
            unit=""
            xLabel="Events recorded"
            yLabel="Event"
            labelWidth={150}
          />
        </div>
      ) : null}


    </Section>
  );
}
