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
    "Institute of Computational Biology and Bioinformatics, University of Ghana.",
  openGraph: {
    title: "Antimicrobial resistance in Ghana",
    description:
      "One Health antimicrobial resistance surveillance, reported with the " +
      "number of isolates behind every figure.",
    type: "website",
  },
  robots: { index: true, follow: true },
};

const OWNER = "Institute of Computational Biology and Bioinformatics";

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
                Data to {monthYear(manifest.period.last)}
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

        {/* Deep ink-blue, so the page ends on something deliberate rather
            than fading into another grey band. Three columns: who publishes
            it, where to go, and when it was generated. */}
        <footer className="no-print bg-[#0d1b2a] text-white/85">
          <div className="mx-auto max-w-[1180px] px-5 py-12">
            <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr]">
              <div>
                <p className="text-[1.05rem] font-bold tracking-tight text-white">
                  ICBB-AMRSS
                </p>
                <p className="mt-2 max-w-[42ch] text-[0.88rem] leading-relaxed text-white/70">
                  {OWNER}
                  <br />
                  University of Ghana
                </p>
              </div>

              <nav aria-label="Sections">
                <p className="mb-3 text-[0.7rem] font-bold uppercase tracking-[0.14em] text-white/45">
                  Sections
                </p>
                <ul className="grid grid-flow-col grid-rows-5 gap-x-6 gap-y-1.5">
                  {SECTIONS.map((section) => (
                    <li key={section.href}>
                      <Link
                        href={section.href}
                        className="text-[0.85rem] text-white/75 transition-colors hover:text-white"
                      >
                        {section.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </nav>

              <div>
                <p className="mb-3 text-[0.7rem] font-bold uppercase tracking-[0.14em] text-white/45">
                  Data
                </p>
                <dl className="space-y-1.5 text-[0.85rem]">
                  <div className="flex justify-between gap-4">
                    <dt className="text-white/60">Susceptibility results</dt>
                    <dd className="tabular-nums text-white">
                      {manifest.counts.results.toLocaleString("en-GB")}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-white/60">Isolates</dt>
                    <dd className="tabular-nums text-white">
                      {manifest.counts.isolates.toLocaleString("en-GB")}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-white/60">Laboratories</dt>
                    <dd className="tabular-nums text-white">
                      {manifest.counts.laboratories.toLocaleString("en-GB")}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-white/60">Updated</dt>
                    <dd className="text-white">
                      {monthYear(manifest.generatedAt)}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>

            <div className="mt-10 border-t border-white/12 pt-5">
              <p className="text-[0.78rem] text-white/50">
                &copy; {new Date(manifest.generatedAt).getFullYear()}{" "}
                {OWNER}, University of Ghana.
              </p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
