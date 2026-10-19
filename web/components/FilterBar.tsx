"use client";

import { titleCase } from "@/lib/format";

/**
 * The filter bar.
 *
 * Visible, labelled and in the same place on every page, because a control the
 * reader cannot find is a control that does not exist. It sits above the
 * figures rather than in a sidebar for the same reason: the first thing a
 * visitor should learn is what they are allowed to change.
 *
 * What it cannot do is compose arbitrary queries. The site is static, so each
 * filtered view was computed in Python and written to a file; a combination
 * nobody exported cannot be reached. That is a deliberate trade — it is also
 * what makes the filtering safe, since no sequence of selections can narrow
 * onto a cell the export did not decide to publish.
 *
 * Options carry their own evidence. A region that supports no published rate
 * says so in the option itself, so the reader learns that before selecting it
 * rather than after meeting an empty table.
 */

export interface FilterOption {
  value: string;
  label: string;
  /** Shown after the label, e.g. "163 isolates · 8 rates". */
  hint?: string;
  disabled?: boolean;
}

export interface FilterControl {
  key: string;
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (next: string) => void;
  /** One line under the control, explaining what it does to the figures. */
  note?: string;
}

export function FilterBar({
  controls,
  summary,
  onReset,
  canReset,
}: {
  controls: FilterControl[];
  /** What the current selection amounts to, in words. */
  summary?: string;
  onReset?: () => void;
  canReset?: boolean;
}) {
  return (
    <section
      aria-label="Filters"
      className="rounded-lg border border-rule bg-shell px-4 py-3.5"
    >
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <h2 className="eyebrow">Filters</h2>
        {canReset && onReset ? (
          <button
            type="button"
            onClick={onReset}
            className="text-[0.78rem] font-semibold text-brand hover:underline"
          >
            Reset
          </button>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-3">
        {controls.map((control) => (
          <div key={control.key} className="min-w-[180px] flex-1">
            <label className="block">
              <span className="mb-1 block text-[0.74rem] font-semibold text-ink-soft">
                {control.label}
              </span>
              <select
                value={control.value}
                onChange={(event) => control.onChange(event.target.value)}
                className="w-full rounded border border-rule-strong bg-paper px-2.5 py-1.5 text-[0.85rem] text-ink focus:border-brand focus:outline-none"
              >
                {control.options.map((option) => (
                  <option
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                  >
                    {option.label}
                    {option.hint ? ` — ${option.hint}` : ""}
                  </option>
                ))}
              </select>
            </label>
            {control.note ? (
              <p className="mt-1 text-[0.72rem] leading-snug text-ink-faint">
                {control.note}
              </p>
            ) : null}
          </div>
        ))}
      </div>

      {summary ? (
        <p className="mt-3 border-t border-rule pt-2.5 text-[0.8rem] text-ink-soft">
          {summary}
        </p>
      ) : null}
    </section>
  );
}

/** A number input used as a filter, for thresholds the reader may raise. */
export function ThresholdControl({
  label,
  value,
  min,
  max,
  step = 5,
  onChange,
  note,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (next: number) => void;
  note?: string;
}) {
  return (
    <div className="min-w-[160px] flex-1">
      <label className="block">
        <span className="mb-1 block text-[0.74rem] font-semibold text-ink-soft">
          {label}
        </span>
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(event) => {
            const next = Number(event.target.value);
            // The floor cannot be lowered. A reader may hide more than the
            // export withheld; they may never see less than it withheld.
            onChange(Number.isFinite(next) ? Math.max(min, next) : min);
          }}
          className="w-full rounded border border-rule-strong bg-paper px-2.5 py-1.5 text-[0.85rem] text-ink focus:border-brand focus:outline-none"
        />
      </label>
      {note ? (
        <p className="mt-1 text-[0.72rem] leading-snug text-ink-faint">{note}</p>
      ) : null}
    </div>
  );
}

export function sectorOptions(
  sectors: string[],
  hints?: Record<string, string>,
): FilterOption[] {
  return sectors.map((sector) => ({
    value: sector,
    label: sector === "all" ? "All sectors" : titleCase(sector),
    hint: hints?.[sector],
  }));
}
