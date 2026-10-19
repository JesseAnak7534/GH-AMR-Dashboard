import Link from "next/link";
import type { Suppression } from "@/lib/data";

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
  children,
}: {
  title: string;
  intro?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
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

export function StatStrip({
  stats,
}: {
  stats: { value: string; label: string; hint?: string }[];
}) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="rounded-lg border border-rule bg-paper px-4 py-3.5"
        >
          <dd className="text-[1.6rem] font-bold leading-none tracking-tight">
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
        </div>
      ))}
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
