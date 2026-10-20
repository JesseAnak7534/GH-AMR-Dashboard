"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * The grouped navigation.
 *
 * Fifteen sections in a flat row was a horizontal scrollbar, and a reader who
 * has to scroll a navigation bar cannot see what the site holds. They are
 * grouped under four headings, each of which opens on hover or on click.
 *
 * Both, deliberately. Hover is what a reader on a laptop expects of a menu
 * with an arrow on it; there is no hover on a phone, and a menu that only
 * opens on hover is a menu that does not open there. So pointer entry opens
 * it, a click toggles it, Escape closes it, a click elsewhere closes it, and
 * moving focus out of the group closes it.
 *
 * The heading itself is a button rather than a link. A group is not a
 * destination -- there is no /resistance-group page -- and making it a link
 * that also opens a menu means a tap on a phone navigates away from the menu
 * it was meant to open.
 *
 * The group holding the current page keeps its underline while the reader is
 * on that page, so the menu says where they are and not only where they can
 * go.
 */

export interface NavEntry {
  href: string;
  title: string;
  colour: string;
}

export interface NavGroupView {
  label: string;
  entries: NavEntry[];
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 10 6"
      width="9"
      height="6"
      aria-hidden="true"
      className={[
        "mt-[1px] shrink-0 transition-transform duration-150",
        open ? "rotate-180" : "",
      ].join(" ")}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M1 1.2 5 4.8 9 1.2" />
    </svg>
  );
}

export function NavMenu({ groups }: { groups: NavGroupView[] }) {
  const pathname = usePathname();
  const [open, setOpen] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(null), []);

  useEffect(() => {
    if (!open) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (!container.current?.contains(event.target as Node)) close();
    };

    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
    };
  }, [open, close]);

  // A navigation closes when it has navigated. Without this the panel stays
  // open over the page the reader just asked for.
  useEffect(() => {
    setOpen(null);
  }, [pathname]);

  return (
    <nav
      aria-label="Sections"
      className="border-b border-rule bg-paper/95 backdrop-blur"
    >
      <div
        ref={container}
        className="mx-auto flex max-w-[1180px] flex-wrap items-stretch gap-0.5 px-5"
        onMouseLeave={close}
      >
        {groups.map((group) => {
          const isOpen = open === group.label;
          const holdsCurrent = group.entries.some(
            (entry) =>
              pathname === entry.href || pathname?.startsWith(`${entry.href}/`),
          );
          const panelId = `nav-${group.label.replace(/[^a-z]+/gi, "-").toLowerCase()}`;

          return (
            <div
              key={group.label}
              className="relative"
              onMouseEnter={() => setOpen(group.label)}
              onBlur={(event) => {
                if (
                  !event.currentTarget.contains(event.relatedTarget as Node)
                ) {
                  close();
                }
              }}
            >
              <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                aria-haspopup="true"
                onClick={() => setOpen(isOpen ? null : group.label)}
                onFocus={() => setOpen(group.label)}
                className={[
                  "flex items-center gap-1.5 border-b-[3px] px-3 py-2.5 text-[0.86rem] font-medium transition-colors",
                  isOpen || holdsCurrent
                    ? "border-brand text-brand"
                    : "border-transparent text-ink-soft hover:border-brand hover:text-brand",
                ].join(" ")}
              >
                {group.label}
                <Chevron open={isOpen} />
              </button>

              <div
                id={panelId}
                hidden={!isOpen}
                className="absolute left-0 top-full z-40 w-[min(15rem,calc(100vw-2.5rem))] rounded-b-lg border border-rule bg-paper p-1.5 shadow-[0_14px_38px_-14px_rgba(13,27,42,0.4)]"
              >
                <ul>
                  {group.entries.map((entry) => {
                    const current =
                      pathname === entry.href ||
                      pathname?.startsWith(`${entry.href}/`);
                    return (
                      <li key={entry.href}>
                        <Link
                          href={entry.href}
                          aria-current={current ? "page" : undefined}
                          onClick={close}
                          className={[
                            "flex items-center gap-2.5 rounded px-2.5 py-2 text-[0.86rem] leading-snug transition-colors",
                            current
                              ? "bg-shell font-semibold text-brand"
                              : "text-ink hover:bg-shell",
                          ].join(" ")}
                        >
                          <span
                            aria-hidden="true"
                            className="h-[0.8rem] w-[3px] shrink-0 rounded-full"
                            style={{ background: entry.colour }}
                          />
                          {entry.title}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          );
        })}
      </div>
    </nav>
  );
}
