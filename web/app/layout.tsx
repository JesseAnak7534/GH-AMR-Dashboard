import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { NAV_GROUPS, groupSections, getManifest } from "@/lib/data";
import { monthYear } from "@/lib/format";
import { NavMenu } from "@/components/NavMenu";

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
 * row groups fifteen sections under four headings that open on hover or on
 * click -- a flat row of fifteen was a horizontal scrollbar, and a reader who
 * has to scroll a navigation bar cannot see what the site holds. The footer
 * keeps the flat list, so every section is one plain link away even with no
 * JavaScript running.
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

          <NavMenu
            groups={NAV_GROUPS.map((group) => ({
              label: group.label,
              entries: groupSections(group).map((section) => ({
                href: section.href,
                title: section.title,
                colour: section.colour,
              })),
            }))}
          />
        </header>

        <main id="content" className="flex-1">
          {children}
        </main>

        {/* Deep ink-blue, so the page ends on something deliberate rather
            than fading into another grey band. Three columns: who publishes
            it, where to go, and when it was generated. */}
        <footer className="no-print bg-[#0d1b2a] text-white/85">
          <div className="mx-auto max-w-[1180px] px-5 py-12">
            <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1fr_1.9fr_1fr]">
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

              <nav aria-label="Sections" className="sm:col-span-2 lg:col-span-1">
                <div className="grid gap-6 sm:grid-cols-2">
                  {NAV_GROUPS.map((group) => (
                    <div key={group.label}>
                      <p className="mb-3 text-[0.7rem] font-bold uppercase tracking-[0.14em] text-white/45">
                        {group.label}
                      </p>
                      <ul className="space-y-1.5">
                        {groupSections(group).map((section) => (
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
                    </div>
                  ))}
                </div>
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
