"use client";

import { useCallback, useRef, useState } from "react";
import { CsvColumn, downloadCsv, figureFilename, svgToPng } from "@/lib/download";

/**
 * The frame every figure sits in, and the toolbar that comes with it.
 *
 * The Streamlit pages this replaced gave each chart a modebar and each table a
 * download button. Losing that was a real regression: on a surveillance site
 * people quote from, a figure you cannot take away is a figure you have to
 * retype.
 *
 * What it offers, and what it deliberately does not:
 *
 * **Data** downloads the rows behind the figure, exactly as they are on screen
 * — after whatever filter and sort the reader applied, so the file matches
 * what they were looking at.
 *
 * **Image** rasterises the chart itself. Serialised from the SVG rather than
 * screenshotted, so it is sharp at any size.
 *
 * **Expand** fills the screen. Charts here are dense -- a heat map of thirteen
 * organisms against forty agents -- and this is what a reader actually wants
 * when they cannot read one.
 *
 * There is no free zoom or pan, and that is a decision rather than an
 * omission. These axes are fixed on purpose: susceptibility runs 0-100% so
 * that a five-point difference cannot be made to look like a collapse. A
 * reader who can rescale can undo that, and the figure stops meaning what it
 * says. The map is the exception and has real zoom, because it is a map.
 */

function ToolbarButton({
  onClick,
  label,
  title,
  busy,
}: {
  onClick: () => void;
  label: string;
  title: string;
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={busy}
      className="rounded border border-rule-strong bg-paper px-2 py-1 text-[0.74rem] font-medium text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:opacity-50"
    >
      {busy ? "…" : label}
    </button>
  );
}

export function Figure({
  title,
  caption,
  csv,
  downloadable = true,
  expandable = true,
  hideTitle = false,
  children,
}: {
  /** Names the figure, and names the file it downloads as. */
  title: string;
  caption?: string;
  /** The rows behind the figure. Omit where there are none to offer. */
  csv?: { rows: unknown[]; columns: CsvColumn[]; name?: string };
  /** Whether an image of the figure can be taken. Tables have no SVG. */
  downloadable?: boolean;
  expandable?: boolean;
  /** Keep the title for the filename but do not draw it. Use when the section
   *  around the figure already names it -- saying it twice is clutter. */
  hideTitle?: boolean;
  children: React.ReactNode;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const saveImage = useCallback(async () => {
    const svg = frame.current?.querySelector("svg");
    if (!svg) {
      setFailed("This figure has no image to save.");
      return;
    }
    setBusy(true);
    setFailed(null);
    try {
      await svgToPng(svg as SVGSVGElement, figureFilename(title));
    } catch (error) {
      // Said out loud rather than swallowed: a button that silently does
      // nothing is worse than one that explains itself.
      setFailed(`Could not save the image (${(error as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }, [title]);

  const toggleExpand = useCallback(() => {
    const node = frame.current;
    if (!node) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
      setExpanded(false);
      return;
    }
    node.requestFullscreen?.().then(
      () => setExpanded(true),
      // Fullscreen can be refused -- an iframe without the permission, a
      // browser that does not allow it. Fall back rather than do nothing.
      () => setExpanded((previous) => !previous),
    );
  }, []);

  const hasToolbar = Boolean(csv?.rows.length) || downloadable || expandable;

  return (
    <figure
      ref={frame}
      className={
        expanded
          ? "overflow-auto bg-paper p-6"
          : "rounded-lg border border-rule bg-paper p-4"
      }
    >
      <figcaption className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          {hideTitle ? null : (
            <h3 className="text-[0.98rem] font-semibold leading-snug">{title}</h3>
          )}
          {caption ? (
            <p className="measure mt-0.5 text-[0.8rem] leading-relaxed text-ink-faint">
              {caption}
            </p>
          ) : null}
        </div>
        {hasToolbar ? (
          <div className="no-print flex shrink-0 gap-1.5">
            {csv?.rows.length ? (
              <ToolbarButton
                label="Data"
                title="Download these rows as CSV, exactly as filtered and sorted here"
                onClick={() =>
                  downloadCsv(csv.rows, csv.columns,
                    figureFilename(csv.name ?? title))
                }
              />
            ) : null}
            {downloadable ? (
              <ToolbarButton
                label="Image"
                title="Save this figure as a PNG"
                onClick={saveImage}
                busy={busy}
              />
            ) : null}
            {expandable ? (
              <ToolbarButton
                label={expanded ? "Close" : "Expand"}
                title={expanded ? "Leave full screen" : "Fill the screen"}
                onClick={toggleExpand}
              />
            ) : null}
          </div>
        ) : null}
      </figcaption>

      {children}

      {failed ? (
        <p className="mt-2 text-[0.78rem] text-data-vermillion">{failed}</p>
      ) : null}
    </figure>
  );
}
