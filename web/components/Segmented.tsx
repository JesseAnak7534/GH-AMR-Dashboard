"use client";

import { titleCase } from "@/lib/format";

/**
 * The control that switches between pre-computed slices.
 *
 * It is a radio group rather than a row of buttons, because that is what it
 * is: one of several mutually exclusive views, navigable by arrow key and
 * announced as a group. A `<select>` would hide the options, and on this site
 * the set of available sectors is itself information -- a reader should see
 * that aquaculture exists before deciding whether to look at it.
 *
 * Each option carries its own colour marker, but the label is always present,
 * so the colour is a reminder of which series is which on the chart below and
 * never the only way to tell the options apart.
 */
export function Segmented({
  options,
  value,
  onChange,
  label,
  colours,
  labels,
}: {
  options: string[];
  value: string;
  onChange: (next: string) => void;
  label: string;
  colours?: Record<string, string>;
  /** Display text per option, where the raw value is a column name rather
   *  than something a reader should see. */
  labels?: Record<string, string>;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-col gap-1.5">
      <span className="eyebrow">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const active = option === value;
          const colour = colours?.[option];
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(option)}
              className={[
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[0.82rem] font-medium transition-colors",
                active
                  ? "border-brand bg-brand text-white"
                  : "border-rule-strong bg-paper text-ink-soft hover:border-brand hover:text-brand",
              ].join(" ")}
            >
              {colour ? (
                <span
                  aria-hidden="true"
                  className="inline-block h-2 w-2 rounded-full"
                  style={{
                    background: active ? "rgba(255,255,255,0.9)" : colour,
                  }}
                />
              ) : null}
              {labels?.[option] ??
                (option === "all" ? "All sectors" : titleCase(option))}
            </button>
          );
        })}
      </div>
    </div>
  );
}
