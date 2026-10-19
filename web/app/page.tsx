import Link from "next/link";
import { SECTIONS, getManifest } from "@/lib/data";
import { count, monthYear } from "@/lib/format";

/**
 * The landing page.
 *
 * A door, not a dashboard: what this is, how much data stands behind it, and
 * what can be looked at. No analysis happens here. The earlier version of this
 * page carried four tabs of tables, so a first-time visitor met a cumulative
 * antibiogram before being told what they were looking at.
 *
 * The whole card is the link. Not a button at the foot of a box -- the entire
 * card is an `<a>`, which is both a larger target and the honest markup for
 * something that navigates.
 *
 * Each card carries one live figure, so the grid is not a menu of promises: a
 * reader can see before clicking whether the genomics section has 1,800
 * genomes behind it or none.
 */
export default function HomePage() {
  const manifest = getManifest();

  return (
    <>
      {/* ── Masthead ───────────────────────────────────────────────── */}
      <section className="border-b border-rule bg-gradient-to-br from-brand to-brand-dark text-white">
        <div className="mx-auto max-w-[1180px] px-5 py-14 sm:py-20">
          <p className="text-[0.74rem] font-bold uppercase tracking-[0.17em] text-white/65">
            One Health surveillance · Ghana
          </p>
          <h1 className="mt-3 max-w-[22ch] text-[clamp(2.1rem,5.5vw,3.7rem)] font-bold leading-[1.04] tracking-tight">
            Antimicrobial resistance in Ghana
          </h1>
          <p className="measure mt-5 text-[1.08rem] leading-relaxed text-white/90">
            Resistance, the organisms behind it, the antimicrobials being used
            and the genomes explaining it — collected across human, animal,
            food, environmental and aquaculture sources, and reported together.
          </p>
          <p className="mt-5 max-w-[78ch] text-[0.87rem] leading-relaxed text-white/70">
            Institute for Clinical Biochemistry and Biotechnology, University
            of Ghana. Aggregate figures only — nothing resting on fewer than{" "}
            {manifest.threshold} records is published.
          </p>
        </div>
      </section>

      {/* ── How much data ──────────────────────────────────────────── */}
      <section className="border-b border-rule bg-shell">
        <div className="mx-auto max-w-[1180px] px-5 py-8">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-3 lg:grid-cols-6">
            {[
              [manifest.counts.specimens, "Specimens"],
              [manifest.counts.isolates, "Isolates"],
              [manifest.counts.results, "Susceptibility results"],
              [manifest.counts.genomes, "Genomes sequenced"],
              [manifest.counts.laboratories, "Laboratories"],
              [manifest.counts.regions, "Regions"],
            ].map(([value, label]) => (
              <div key={label as string}>
                <dd className="text-[1.75rem] font-bold leading-none tracking-tight tabular-nums">
                  {count(value)}
                </dd>
                <dt className="mt-1.5 text-[0.79rem] font-medium text-ink-soft">
                  {label as string}
                </dt>
              </div>
            ))}
          </dl>
          <p className="measure mt-6 text-[0.85rem] leading-relaxed text-ink-faint">
            Specimens collected between{" "}
            <strong className="font-semibold text-ink-soft">
              {monthYear(manifest.period.first)}
            </strong>{" "}
            and{" "}
            <strong className="font-semibold text-ink-soft">
              {monthYear(manifest.period.last)}
            </strong>
            , across {manifest.counts.sectors} sectors. First isolate per
            patient per organism, following CLSI M39.
          </p>
        </div>
      </section>

      {/* ── The sections ───────────────────────────────────────────── */}
      <section className="mx-auto max-w-[1180px] px-5 py-12">
        <p className="eyebrow mb-4">Explore the surveillance</p>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SECTIONS.map((section) => {
            const stat = section.stat(manifest);
            return (
              <li key={section.href}>
                <Link
                  href={section.href}
                  className="group relative flex h-full flex-col overflow-hidden rounded-xl border border-rule bg-paper p-5 pl-6 transition-all hover:-translate-y-0.5 hover:border-rule-strong hover:shadow-[0_10px_28px_rgba(22,24,26,0.1)]"
                >
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-0 h-full w-[5px]"
                    style={{ background: section.colour }}
                  />
                  <span className="mb-2.5 flex items-center gap-2">
                    <span
                      className="rounded px-1.5 py-0.5 text-[0.62rem] font-bold tracking-[0.09em] text-white"
                      style={{ background: section.colour }}
                    >
                      {section.badge}
                    </span>
                    <span className="text-[1.08rem] font-bold tracking-tight">
                      {section.title}
                    </span>
                  </span>
                  <span
                    className="text-[2.1rem] font-bold leading-none tracking-tight tabular-nums"
                    style={{ color: section.colour }}
                  >
                    {count(stat.value)}
                  </span>
                  <span className="mb-3 mt-1 text-[0.78rem] text-ink-faint">
                    {stat.unit}
                  </span>
                  <span className="flex-1 text-[0.88rem] leading-relaxed text-ink-soft">
                    {section.blurb}
                  </span>
                  <span
                    className="mt-4 text-[0.83rem] font-semibold"
                    style={{ color: section.colour }}
                  >
                    Open {section.title}{" "}
                    <span className="inline-block transition-transform group-hover:translate-x-0.5">
                      →
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      {/* ── How to read it ─────────────────────────────────────────── */}
      <section className="border-t border-rule bg-shell">
        <div className="mx-auto grid max-w-[1180px] gap-10 px-5 py-12 lg:grid-cols-3">
          <div>
            <h2 className="text-[1.06rem] font-bold">
              How to read anything on this site
            </h2>
            <p className="mt-2 text-[0.88rem] leading-relaxed text-ink-soft">
              No percentage below {manifest.minIsolatesForReporting} isolates.
              Every percentage carries a 95% confidence interval. Rates are
              pooled, not averaged. Sectors are never combined into one figure.
            </p>
          </div>
          <div>
            <h2 className="text-[1.06rem] font-bold">What is withheld</h2>
            <p className="mt-2 text-[0.88rem] leading-relaxed text-ink-soft">
              Counts below {manifest.threshold} records are withheld, and so is
              any percentage over them.{" "}
              <strong className="font-semibold">Withheld is not zero</strong> —
              it means too few to publish, not none found.
            </p>
          </div>
          <div>
            <h2 className="text-[1.06rem] font-bold">What this is and is not</h2>
            <p className="mt-2 text-[0.88rem] leading-relaxed text-ink-soft">
              Laboratory-based sentinel surveillance: the isolates that reached
              a participating laboratory. Not a random sample of infections, and
              not a measure of resistance in the population.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
