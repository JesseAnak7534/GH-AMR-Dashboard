"use client";

import { useCallback, useRef, useState } from "react";
import { figureFilename, svgToPng } from "@/lib/download";

/**
 * The frame every figure sits in, and the two controls that come with it.
 *
 * **Save the image.** The chart as a PNG, for a slide or a report. It is
 * serialised from the SVG rather than screenshotted, so it stays sharp at any
 * size.
 *
 * **Expand.** Charts here are dense -- a heat map of thirteen organisms
 * against forty agents -- and filling the screen is what a reader actually
 * wants when they cannot read one.
 *
 * What is deliberately absent:
 *
 * **The data.** There is no download of the rows behind a figure, anywhere on
 * this site. The picture and its printed values are what is published.
 *
 * **Zoom and pan.** These axes are fixed on purpose: susceptibility runs
 * 0-100% so a five-point difference cannot be made to look like a collapse,
 * and a trend's confidence band only means something against a stable scale. A
 * reader who can rescale can undo that. The map is the exception and has real
 * zoom, because it is a map.
 */

function SaveIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 1.5v8" />
      <path d="M4.5 6.5 8 10l3.5-3.5" />
      <path d="M2 11v2.5h12V11" />
    </svg>
  );
}

function ExpandIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 2H2v4" />
      <path d="M10 2h4v4" />
      <path d="M6 14H2v-4" />
      <path d="M10 14h4v-4" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"
         fill="none" stroke="currentColor" strokeWidth="1.5"
         strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 6h4V2" />
      <path d="M13.5 6h-4V2" />
      <path d="M2.5 10h4v4" />
      <path d="M13.5 10h-4v4" />
    </svg>
  );
}

function ToolButton({
  onClick,
  label,
  children,
  busy,
}: {
  onClick: () => void;
  /** Read aloud and shown on hover. The icon alone names nothing. */
  label: string;
  children: React.ReactNode;
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      disabled={busy}
      className="inline-flex h-7 w-7 items-center justify-center rounded border border-rule-strong bg-paper text-ink-faint transition-colors hover:border-brand hover:text-brand disabled:opacity-40"
    >
      {busy ? (
        <span className="text-[0.7rem]" aria-hidden="true">
          …
        </span>
      ) : (
        children
      )}
    </button>
  );
}

export function Figure({
  title,
  caption,
  downloadable = true,
  expandable = true,
  hideTitle = false,
  children,
}: {
  /** Names the figure, and names the file its image saves as. */
  title: string;
  caption?: string;
  /** Whether an image can be taken. False where there is no SVG to take. */
  downloadable?: boolean;
  expandable?: boolean;
  /** Keep the title for the filename but do not draw it, where the section
   *  around the figure already names it. */
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
      // Said out loud rather than swallowed: a control that silently does
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
      // Fullscreen can be refused. Fall back to an in-page expansion rather
      // than leaving the control dead.
      () => setExpanded((previous) => !previous),
    );
  }, []);

  const hasTools = downloadable || expandable;

  return (
    <figure
      ref={frame}
      className={
        expanded
          ? "overflow-auto bg-paper p-6"
          : "rounded-lg border border-rule bg-paper p-4"
      }
    >
      {hideTitle && !caption && !hasTools ? null : (
        <figcaption className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div>
            {hideTitle ? null : (
              <h3 className="text-[0.98rem] font-semibold leading-snug">
                {title}
              </h3>
            )}
            {caption ? (
              <p className="measure mt-0.5 text-[0.8rem] leading-relaxed text-ink-faint">
                {caption}
              </p>
            ) : null}
          </div>
          {hasTools ? (
            <div className="no-print ml-auto flex shrink-0 gap-1.5">
              {downloadable ? (
                <ToolButton label="Save this figure as an image"
                            onClick={saveImage} busy={busy}>
                  <SaveIcon />
                </ToolButton>
              ) : null}
              {expandable ? (
                <ToolButton
                  label={expanded ? "Leave full screen" : "Fill the screen"}
                  onClick={toggleExpand}
                >
                  {expanded ? <CloseIcon /> : <ExpandIcon />}
                </ToolButton>
              ) : null}
            </div>
          ) : null}
        </figcaption>
      )}

      {children}

      {failed ? (
        <p className="mt-2 text-[0.78rem] text-data-vermillion">{failed}</p>
      ) : null}
    </figure>
  );
}
