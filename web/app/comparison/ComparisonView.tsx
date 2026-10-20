"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart } from "@/components/Charts";
import {
  Empty,
  Note,
  Section,
  SuppressionNote,
} from "@/components/Chrome";
import { Figure } from "@/components/Figure";
import { FilterBar, sectorOptions } from "@/components/FilterBar";
import { Segmented } from "@/components/Segmented";
import type {
  ComparisonData,
  ComparisonDimension,
  ComparisonRow,
} from "@/lib/clinical";
import { count, interval, percent, titleCase } from "@/lib/format";
import { useSlice } from "@/lib/slices";
import { OKABE_ITO } from "@/lib/palette";

/**
 * Comparing groups, with the guard rails the staff page has.
 *
 * Three of them matter enough to be visible on screen. Sectors are never
 * pooled, so the sector is chosen first and the comparison happens inside it.
 * A group below the reporting threshold keeps its counts and loses its
 * percentage, and the table says which. And two groups are never ranked
 * against each other without a statement about whether the difference
 * survives the uncertainty: overlapping intervals are reported as not
 * distinguishable, not as a difference of so many points.
 *
 * The overlap test is done here, in the browser, on intervals that were
 * published with the rows. It is not a hypothesis test, and it is described in
 * those terms: non-overlapping intervals are strong evidence of a real
 * difference; overlapping ones do not prove there is none.
 */

/** Whether two Wilson intervals overlap, or null if one is missing. */
function overlaps(a: ComparisonRow, b: ComparisonRow): boolean | null {
  if (
    a.ciLow === null ||
    a.ciHigh === null ||
    b.ciLow === null ||
    b.ciHigh === null
  ) {
    return null;
  }
  return !(a.ciHigh < b.ciLow || b.ciHigh < a.ciLow);
}

/** The groups the chart cannot show, named in one line. */
function BelowFloor({
  rows,
  label,
}: {
  rows: ComparisonRow[];
  label: string;
}) {
  const held = rows.filter((row) => row.status !== "reported");
  if (!held.length) return null;
  return (
    <p className="mt-2 text-[0.78rem] text-ink-faint">
      {held.length} {label.toLowerCase()}
      {held.length === 1 ? "" : "s"} held too few isolates to carry a
      percentage: {held.map((row) => row.group).join(", ")}.
    </p>
  );
}

function HeadToHead({
  rows,
  groupLabel,
  measure,
}: {
  rows: ComparisonRow[];
  groupLabel: string;
  measure: string;
}) {
  const reportable = rows.filter(
    (row) => row.status === "reported" && row.percent !== null,
  );
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");

  useEffect(() => {
    setFirst(reportable[0]?.group ?? "");
    setSecond(reportable[1]?.group ?? "");
    // Re-seeded whenever the set of reportable groups changes, which it does
    // on every change of sector, view or dimension.
  }, [reportable.map((row) => row.group).join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  if (reportable.length < 2) {
    return (
      <Note tone="limit">
        Fewer than two groups hold enough isolates to compare.
      </Note>
    );
  }

  const a = reportable.find((row) => row.group === first);
  const b = reportable.find((row) => row.group === second);
  if (!a || !b) return null;

  const difference = (a.percent as number) - (b.percent as number);
  const overlap = a.group === b.group ? null : overlaps(a, b);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {[
          { label: "First", value: first, onChange: setFirst },
          { label: "Second", value: second, onChange: setSecond },
        ].map((control) => (
          <label key={control.label} className="block">
            <span className="mb-1 block text-[0.74rem] font-semibold text-ink-soft">
              {control.label}
            </span>
            <select
              value={control.value}
              onChange={(event) => control.onChange(event.target.value)}
              className="w-full rounded border border-rule-strong bg-paper px-2.5 py-1.5 text-[0.85rem] text-ink focus:border-brand focus:outline-none"
            >
              {reportable.map((row) => (
                <option key={row.group} value={row.group}>
                  {row.group}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <dl className="grid grid-cols-3 gap-3">
        {[
          {
            label: a.group,
            value: percent(a.percent),
            hint: `95% CI ${interval(a.ciLow, a.ciHigh)}`,
          },
          {
            label: b.group,
            value: percent(b.percent),
            hint: `95% CI ${interval(b.ciLow, b.ciHigh)}`,
          },
          {
            label: "Difference",
            value: `${difference >= 0 ? "+" : ""}${difference.toFixed(1)} points`,
            hint: measure,
          },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-rule bg-paper px-4 py-3.5"
          >
            <dd className="text-[1.4rem] font-bold leading-none tracking-tight">
              {stat.value}
            </dd>
            <dt className="mt-1.5 text-[0.78rem] font-medium text-ink-soft">
              {stat.label}
            </dt>
            <p className="mt-1 text-[0.7rem] leading-snug text-ink-faint">
              {stat.hint}
            </p>
          </div>
        ))}
      </dl>

      {a.group === b.group ? (
        <Note tone="method">Choose two different {groupLabel.toLowerCase()}s.</Note>
      ) : overlap === null ? (
        <Note tone="limit">One group has no interval, so the difference cannot be assessed.</Note>
      ) : overlap ? (
        <Note tone="limit">
          The intervals overlap, so this{" "}
          {Math.abs(difference).toFixed(1)}-point difference is not
          distinguishable from sampling variation.
        </Note>
      ) : (
        <Note tone="method">
          The intervals do not overlap, so the{" "}
          {Math.abs(difference).toFixed(1)}-point difference is unlikely to be
          chance. It does not say why.
        </Note>
      )}
    </div>
  );
}

export function ComparisonView({ data }: { data: ComparisonData }) {
  const sectors = data.slices.map((slice) => slice.sector);
  const [sector, setSector] = useState(sectors[0] ?? "human");
  const slice =
    data.slices.find((candidate) => candidate.sector === sector) ??
    data.slices[0];

  const [viewKey, setViewKey] = useState("pooled");
  const [dimensionKey, setDimensionKey] = useState("region");
  const [months, setMonths] = useState(String(data.periods[0] ?? 12));

  const view =
    slice?.views.find((candidate) => candidate.key === viewKey) ??
    slice?.views[0];

  // A single organism-agent view lives in its own file. The pooled view
  // travels in the page, so the first table is there before any fetch.
  const fetched = useSlice<{ dimensions: ComparisonDimension[] }>(
    "comparison",
    view && !view.pooled ? view.slug : null,
    { dimensions: view?.dimensions ?? [] },
  );

  const dimensions: ComparisonDimension[] = useMemo(() => {
    if (!view) return [];
    if (view.pooled) return view.dimensions ?? [];
    return fetched.data?.dimensions ?? [];
  }, [view, fetched.data]);

  const dimension =
    dimensions.find((candidate) => candidate.key === dimensionKey) ??
    dimensions[0];

  const period = slice?.periods.find(
    (candidate) => String(candidate.months) === months,
  );

  if (!slice || !view) {
    return <Empty>No sector holds enough isolates to compare across.</Empty>;
  }

  return (
    <>
      <FilterBar
        controls={[
          {
            key: "sector",
            label: "Sector",
            value: sector,
            options: sectorOptions(sectors),
            note: "Sectors are never compared against each other.",
            onChange: (next) => {
              setSector(next);
              setViewKey("pooled");
            },
          },
          {
            key: "view",
            label: "What is compared",
            value: view.key,
            options: slice.views.map((candidate) => ({
              value: candidate.key,
              label: candidate.label,
              hint: candidate.pooled
                ? undefined
                : `${count(candidate.isolates ?? 0)} isolates`,
            })),
            note: "One organism and one agent is the clinically usable figure.",
            onChange: setViewKey,
          },
          {
            key: "dimension",
            label: "Compare across",
            value: dimension?.key ?? "",
            options: dimensions.map((candidate) => ({
              value: candidate.key,
              label: candidate.label,
              hint: `${candidate.rows.length} groups`,
            })),
            onChange: setDimensionKey,
          },
        ]}
        summary={`${titleCase(slice.sector)} — ${count(
          slice.isolates,
        )} isolates. Percentages are withheld below ${
          data.minIsolatesForReporting
        } isolates; the counts are still shown.`}
      />

      {fetched.error ? (
        <Note tone="limit">
          That comparison did not load ({fetched.error}).
        </Note>
      ) : null}

      <Section
        title={`Between ${dimension ? dimension.label.toLowerCase() : "groups"}`}
        intro={
          view.pooled
            ? "Pooled across every organism and agent, so groups are only comparable where they tested similar panels."
            : undefined
        }
      >
        {fetched.loading ? (
          <Empty>Loading that comparison…</Empty>
        ) : !dimension || !dimension.rows.length ? (
          <Empty>No group in this sector can be compared on that.</Empty>
        ) : (
          <>
            <Figure
              title={`${view.label} by ${dimension.label.toLowerCase()} — ${titleCase(
                slice.sector,
              )}`}
              hideTitle
            >
              <BarChart
                rows={dimension.rows
                  .filter((row) => row.status === "reported")
                  .map((row) => ({
                    label: row.group,
                    value: row.percent,
                    low: row.ciLow,
                    high: row.ciHigh,
                    denominator: row.unit,
                  }))}
                unit=""
                suffix="%"
                max={100}
                colour={OKABE_ITO.blue}
                xLabel={view.measure}
                yLabel={dimension.label}
                labelWidth={220}
              />
            </Figure>
            <BelowFloor rows={dimension.rows} label={dimension.label} />
            <SuppressionNote suppression={dimension.suppression} />
          </>
        )}
      </Section>

      {dimension && dimension.rows.length ? (
        <Section title="Two groups, side by side">
          <HeadToHead
            rows={dimension.rows}
            groupLabel={dimension.label}
            measure={view.measure}
          />
        </Section>
      ) : null}

      <Section
        title="Over time"
        intro="The most recent window against the one before it."
      >
        <Segmented
          label="Period length"
          options={data.periods.map(String)}
          value={months}
          onChange={setMonths}
          labels={Object.fromEntries(
            data.periods.map((m) => [String(m), `${m} months`]),
          )}
        />
        {period && period.rows.length ? (
          <>
            <Figure
              title={`Most recent ${months} months against the preceding ${months} — ${titleCase(
                slice.sector,
              )}`}
              hideTitle
            >
              <BarChart
                rows={period.rows
                  .filter((row) => row.status === "reported")
                  .map((row) => ({
                    label: row.group,
                    value: row.percent,
                    low: row.ciLow,
                    high: row.ciHigh,
                    denominator: row.unit,
                  }))}
                unit=""
                suffix="%"
                max={100}
                colour={OKABE_ITO.orange}
                xLabel="% non-susceptible"
                yLabel="Period"
                labelWidth={210}
              />
            </Figure>
            <BelowFloor rows={period.rows} label="Period" />
            <SuppressionNote suppression={period.suppression} />
            <HeadToHead
              rows={period.rows}
              groupLabel="Period"
              measure="% non-susceptible"
            />
          </>
        ) : (
          <Empty>
            Both windows need at least {data.minIsolatesForReporting} isolates
            before a change can be reported.
          </Empty>
        )}
      </Section>
    </>
  );
}
