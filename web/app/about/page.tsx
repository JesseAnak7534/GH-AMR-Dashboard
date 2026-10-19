import type { Metadata } from "next";
import {
  Caption,
  Container,
  Note,
  PageHeader,
  Section,
  StatStrip,
} from "@/components/Chrome";
import { CompletenessTable, MetricTable } from "./AboutTables";
import { getAbout, getManifest } from "@/lib/data";
import { count, monthYear } from "@/lib/format";

export const metadata: Metadata = {
  title: "About this data",
  description:
    "How every figure on this site is calculated, what is withheld and why, " +
    "and what laboratory-based sentinel surveillance cannot tell you.",
};

/**
 * The page that makes the rest of the site readable.
 *
 * Not a disclaimer page. A reader who does not know that the denominator is
 * isolates rather than results, that sectors are never pooled, or that a
 * withheld cell is not a zero, will misread every figure on the site -- and
 * the completeness table is the part that lets them judge how much weight any
 * breakdown can carry.
 */
export default function AboutPage() {
  const about = getAbout();
  const manifest = getManifest();

  return (
    <>
      <PageHeader
        badge="DOC"
        colour="#56B4E9"
        title="About this data"
        lede="Where these figures come from, how they are calculated, and what they do not show."
      />
      <Container>
        <StatStrip
          stats={[
            { value: count(manifest.counts.specimens), label: "Specimens" },
            { value: count(manifest.counts.isolates), label: "Isolates" },
            {
              value: count(manifest.counts.results),
              label: "Susceptibility results",
            },
            {
              value: count(manifest.counts.laboratories),
              label: "Laboratories",
            },
          ]}
        />
        <Caption>
          Specimens collected between {monthYear(manifest.period.first)} and{" "}
          {monthYear(manifest.period.last)}. Figures on this site were generated{" "}
          {monthYear(manifest.generatedAt)}.
        </Caption>

        <Section title="How these figures are built">
          <div className="measure space-y-4 text-[0.93rem] leading-relaxed text-ink">
            <p>
              <strong>One isolate per patient per organism.</strong> A patient
              sampled four times in a fortnight would otherwise contribute four
              results and shift the percentage on their own. Following CLSI M39,
              the first isolate of each organism from each patient is counted
              and the rest are set aside. Where the data cannot identify the
              patient behind a specimen, that is said rather than quietly
              skipped — reporting &ldquo;0% duplicates removed&rdquo; on
              unlinkable data looks identical to a properly deduplicated
              antibiogram and means something entirely different.
            </p>
            {about.deduplication ? (
              <p className="rounded-r-lg border-l-[3px] border-l-brand bg-brand-light px-4 py-3 text-[0.88rem]">
                {about.deduplication}
              </p>
            ) : null}
            <p>
              <strong>
                No percentage below {about.minIsolatesForReporting} isolates.
              </strong>{" "}
              A proportion calculated on a handful of results is not a
              measurement. The count is still reported where it is large enough
              to publish.
            </p>
            <p>
              <strong>Every percentage carries a confidence interval</strong>,
              computed by the Wilson method, which stays inside 0 to 100% near
              the extremes where the ordinary normal approximation does not.
            </p>
            <p>
              <strong>Rates are pooled, not averaged.</strong> Numerators are
              summed and denominators are summed. Averaging each
              facility&rsquo;s own rate gives a ten-bed clinic the same weight
              as a teaching hospital.
            </p>
            <p>
              <strong>Sectors are not pooled.</strong> Human, animal, food,
              environmental and aquaculture results are counted separately
              unless a page says explicitly that it is combining them.
            </p>
            <p>
              <strong>The denominator is stated.</strong> Where the unit is one
              isolate against one agent rather than the isolate, the column says
              so — because an isolate tested against twelve agents cannot be the
              denominator for twelve results.
            </p>
          </div>
        </Section>

        <Section title="What is withheld">
          <div className="measure space-y-4 text-[0.93rem] leading-relaxed text-ink">
            <p>
              Any count resting on fewer than {about.minPublicCell} records is
              withheld, and so is any percentage calculated over it. Where
              withholding one value would let it be recovered by subtracting the
              rest from a published total, a second value is withheld as well —
              suppressing one cell beside a published total achieves nothing,
              and that is the usual way a disclosure-control pass fails.
            </p>
            <p>
              <strong>Withheld is not zero.</strong> It means too few records to
              publish, not none found. The two are shown differently throughout:
              a withheld cell says so in words, because a blank reads as
              &ldquo;nothing here&rdquo; and a zero reads as &ldquo;we looked
              and found none&rdquo;.
            </p>
            <p>
              The risk on a public surveillance page was never the headline
              figures. It is narrowing: a visitor filtering by sector, region,
              laboratory and organism can reach a cell holding one person, and
              each filter is another attribute attached to them. This site
              therefore publishes pre-computed slices rather than answering
              arbitrary queries — the search and sort controls only reach rows
              that were already published.
            </p>
          </div>
        </Section>

        <Section
          title="Completeness of the fields these figures depend on"
          intro="A figure can only be as complete as the field behind it. This is the part that lets a reader judge everything else: a ward-level breakdown resting on a ward field completed half the time should be read as such."
        >
          <CompletenessTable rows={about.completeness} />
          {about.completenessError ? (
            <Caption>
              The completeness report could not be produced for this data.
            </Caption>
          ) : null}
        </Section>

        {about.metrics.length ? (
          <Section
            title="What each metric means"
            intro="Every definition is implemented once, in the platform's analysis layer, and applied identically on every page. A figure appearing in two places is the same calculation in both."
          >
            <MetricTable rows={about.metrics} />
          </Section>
        ) : null}

        <Section title="What this does not show">
          <div className="measure space-y-4 text-[0.93rem] leading-relaxed text-ink">
            <p>
              No patient identifier, specimen identifier or individual result
              appears anywhere on this site. What is published is an aggregate
              of records held under the surveillance system&rsquo;s own access
              controls.
            </p>
            <p>
              Resistance measured here describes the isolates that reached a
              participating laboratory. Who gets cultured is not random:
              specimens arrive more often from severe infections, from patients
              who have already failed treatment, and from facilities with a
              laboratory on site. These figures describe laboratory-based
              sentinel surveillance, not the burden of resistance in the general
              population.
            </p>
            <p>
              <strong>Laboratories are named.</strong> Attribution is the point
              of sentinel surveillance, and a rate nobody can attribute is a
              rate nobody can act on.
            </p>
          </div>
        </Section>

        <Note>
          <strong>How this site is built.</strong> The figures are computed in
          the surveillance platform&rsquo;s own analysis layer and exported as
          published files after passing through its disclosure control. This
          site holds no database connection and answers no queries, so no
          combination of controls on it can produce a figure the export did not
          decide to publish.
        </Note>
      </Container>
    </>
  );
}
