import Link from "next/link";
import type { Suppression } from "@/lib/data";
import { STAT_SEQUENCE } from "@/lib/palette";

/**
 * Page furniture: the pieces that repeat on every section page.
 *
 * They are server components. None of them needs state, and a header that
 * arrives with the HTML is a header that is readable before any JavaScript
 * has run.
 */

export function PageHeader({
  badge,
  colour,
  title,
  lede,
}: {
  badge: string;
  colour: string;
  title: string;
  lede: string;
}) {
  return (
    <div className="border-b border-rule bg-shell">
      <div className="mx-auto max-w-[1180px] px-5 py-9">
        <Link
          href="/"
          className="mb-3 inline-flex items-center gap-1.5 text-[0.82rem] font-semibold text-brand hover:underline"
        >
          <span aria-hidden="true">←</span> All sections
        </Link>
        <div className="flex items-center gap-2.5">
          <span
            className="rounded px-1.5 py-0.5 text-[0.64rem] font-bold tracking-[0.09em] text-white"
            style={{ background: colour }}
          >
            {badge}
          </span>
          <h1 className="text-[clamp(1.7rem,3.4vw,2.5rem)] font-bold leading-[1.1]">
            {title}
          </h1>
        </div>
        <p className="measure mt-3 text-[1.02rem] leading-relaxed text-ink-soft">
          {lede}
        </p>
      </div>
    </div>
  );
}

export function Container({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[1180px] px-5 py-9 space-y-11">{children}</div>
  );
}

export function Section({
  title,
  intro,
  id,
  children,
}: {
  title: string;
  intro?: string;
  /** An anchor, so a figure card elsewhere on the page can link to it. The
   *  scroll margin keeps the heading clear of the sticky masthead. */
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <div>
        <h2 className="text-[1.3rem] font-bold leading-snug">{title}</h2>
        {intro ? (
          <p className="measure mt-1.5 text-[0.9rem] leading-relaxed text-ink-soft">
            {intro}
          </p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export interface Stat {
  value: string;
  label: string;
  hint?: string;
  /** The card's accent. Omitted, it takes the next colour in the Okabe-Ito
   *  sequence, so a strip is coloured without every caller choosing. */
  colour?: string;
  /** Where the card leads. A card with a destination is a link, and the whole
   *  card is the target rather than a word inside it. Cards with nothing to
   *  point at stay as they are: a link that goes somewhere unrelated is worse
   *  than no link. */
  href?: string;
}

/**
 * The figures at the head of a block.
 *
 * Each card carries its own colour from the Okabe-Ito set, which stays
 * distinguishable under every common form of colour blindness. The colour is
 * never the only signal -- the label is always written out -- so a card means
 * the same thing to a reader who cannot see the difference.
 */
export function StatStrip({ stats }: { stats: Stat[] }) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {stats.map((stat, index) => {
        const colour = stat.colour ?? STAT_SEQUENCE[index % STAT_SEQUENCE.length];
        const body = (
          <>
            <span
              aria-hidden="true"
              className="absolute left-0 top-0 h-full w-[4px]"
              style={{ background: colour }}
            />
            <dd
              className="text-[1.6rem] font-bold leading-none tracking-tight"
              style={{ color: colour }}
            >
              {stat.value}
            </dd>
            <dt className="mt-1.5 text-[0.78rem] font-medium text-ink-soft">
              {stat.label}
            </dt>
            {stat.hint ? (
              <p className="mt-1 text-[0.7rem] leading-snug text-ink-faint">
                {stat.hint}
              </p>
            ) : null}
          </>
        );

        const shell =
          "relative overflow-hidden rounded-lg border border-rule px-4 py-3.5 pl-5";

        return stat.href ? (
          <Link
            key={stat.label}
            href={stat.href}
            className={`${shell} group block transition-all hover:-translate-y-0.5 hover:border-rule-strong hover:shadow-[0_8px_22px_rgba(22,24,26,0.1)]`}
            style={{ background: `${colour}0f` }}
          >
            {body}
            <span
              aria-hidden="true"
              className="mt-1.5 block text-[0.72rem] font-semibold"
              style={{ color: colour }}
            >
              Open{" "}
              <span className="inline-block transition-transform group-hover:translate-x-0.5">
                →
              </span>
            </span>
          </Link>
        ) : (
          <div
            key={stat.label}
            className={shell}
            style={{ background: `${colour}0f` }}
          >
            {body}
          </div>
        );
      })}
    </dl>
  );
}

/**
 * A note the reader is meant to read before the figure, not after it.
 *
 * `tone="method"` for how a number was produced, `tone="limit"` for what it
 * cannot support. They look different because they are different: one is
 * provenance, the other is a warning against a conclusion.
 */
export function Note({
  tone = "method",
  children,
}: {
  tone?: "method" | "limit";
  children: React.ReactNode;
}) {
  const style =
    tone === "limit"
      ? "border-l-[3px] border-l-data-vermillion bg-[#fdf4ef]"
      : "border-l-[3px] border-l-brand bg-brand-light";
  return (
    <div className={`rounded-r-lg px-4 py-3 ${style}`}>
      <p className="measure text-[0.86rem] leading-relaxed text-ink">
        {children}
      </p>
    </div>
  );
}

/**
 * What was withheld, and why.
 *
 * Published beside the table it describes. A table with silent gaps invites
 * the reader to read them as zero, and a reader who knows how much was held
 * back can judge how much of the picture they are being shown.
 */
export function SuppressionNote({
  suppression,
}: {
  suppression?: Suppression | null;
}) {
  if (!suppression || !suppression.withheld) return null;
  return (
    <p className="measure text-[0.8rem] leading-relaxed text-ink-faint">
      {suppression.summary}
    </p>
  );
}

export function Caption({ children }: { children: React.ReactNode }) {
  return (
    <p className="measure text-[0.8rem] leading-relaxed text-ink-faint">
      {children}
    </p>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-rule-strong bg-shell px-5 py-8 text-center">
      <p className="measure mx-auto text-[0.88rem] leading-relaxed text-ink-soft">
        {children}
      </p>
    </div>
  );
}
