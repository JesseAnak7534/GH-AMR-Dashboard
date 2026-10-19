import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { SECTIONS, getManifest } from "@/lib/data";
import { monthYear } from "@/lib/format";

export const metadata: Metadata = {
  title: {
    default: "Antimicrobial resistance in Ghana — ICBB-AMRSS",
    template: "%s — ICBB-AMRSS",
  },
  description:
    "One Health antimicrobial resistance surveillance across human, animal, " +
    "food, environmental and aquaculture sources in Ghana. Published by the " +
    "Institute for Clinical Biochemistry and Biotechnology, University of Ghana.",
  openGraph: {
    title: "Antimicrobial resistance in Ghana",
    description:
      "One Health antimicrobial resistance surveillance, reported with the " +
      "number of isolates behind every figure.",
    type: "website",
  },
  robots: { index: true, follow: true },
};

const OWNER = "Institute for Clinical Biochemistry and Biotechnology";

/**
 * The shell.
 *
 * One masthead, one navigation row, one footer, on every page. The navigation
 * is plain links rather than a client-side menu: six destinations do not need
 * JavaScript, and a link works before any of it has loaded.
 *
 * `skip to content` is first in the DOM. A reader using a screen reader or a
 * keyboard should not have to walk the navigation on every page.
 */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const manifest = getManifest();

  return (
    <html lang="en-GB">
      <body className="flex min-h-screen flex-col">
        <a
          href="#content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-brand focus:px-3 focus:py-2 focus:text-sm focus:text-white"
        >
          Skip to content
        </a>

        <header className="no-print">
          <div className="bg-brand text-white">
            <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3 px-5 py-3">
              <Link href="/" className="group flex items-baseline gap-2.5">
                <span className="text-[1.02rem] font-bold tracking-tight">
                  ICBB-AMRSS
                </span>
                <span className="text-[0.76rem] text-white/70">
                  Antimicrobial resistance surveillance · Ghana
                </span>
              </Link>
              <span className="text-[0.72rem] text-white/60">
                Data to {monthYear(manifest.period.last)} · aggregate figures only
              </span>
            </div>
          </div>

          <nav
            aria-label="Sections"
            className="border-b border-rule bg-paper/95 backdrop-blur"
          >
            <div className="mx-auto flex max-w-[1180px] gap-1 overflow-x-auto px-5">
              {SECTIONS.map((section) => (
                <Link
                  key={section.href}
                  href={section.href}
                  className="shrink-0 border-b-[3px] border-transparent px-3 py-2.5 text-[0.86rem] font-medium text-ink-soft transition-colors hover:border-brand hover:text-brand"
                >
                  {section.title}
                </Link>
              ))}
            </div>
          </nav>
        </header>

        <main id="content" className="flex-1">
          {children}
        </main>

        <footer className="no-print mt-16 border-t border-rule bg-shell">
          <div className="mx-auto grid max-w-[1180px] gap-8 px-5 py-10 sm:grid-cols-2 lg:grid-cols-4">
            <div className="lg:col-span-2">
              <p className="eyebrow mb-2">Published by</p>
              <p className="text-[0.92rem] font-semibold">{OWNER}</p>
              <p className="mt-1 text-[0.85rem] leading-relaxed text-ink-soft">
                University of Ghana. Laboratories are named throughout.
              </p>
            </div>

            <div>
              <p className="eyebrow mb-2">How to read it</p>
              <p className="text-[0.82rem] leading-relaxed text-ink-soft">
                No percentage below {manifest.minIsolatesForReporting}{" "}
                isolates. Counts below {manifest.threshold} records are withheld
                — withheld is not zero.
              </p>
            </div>

            <div>
              <p className="eyebrow mb-2">Sections</p>
              <ul className="space-y-1">
                {SECTIONS.map((section) => (
                  <li key={section.href}>
                    <Link
                      href={section.href}
                      className="text-[0.82rem] text-ink-soft hover:text-brand hover:underline"
                    >
                      {section.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="border-t border-rule">
            <div className="mx-auto max-w-[1180px] px-5 py-4 text-[0.76rem] text-ink-faint">
              Generated {monthYear(manifest.generatedAt)} from{" "}
              {manifest.counts.results.toLocaleString("en-GB")} susceptibility
              results. Aggregate figures only.
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
