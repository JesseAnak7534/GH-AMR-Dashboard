/**
 * Formatting, including the one case that matters most.
 *
 * A withheld cell must never render as a blank or a zero. A blank reads as
 * "nothing here" and a zero reads as "we looked and found none", and the whole
 * point of the suppression is that neither is true: it means too few records to
 * publish. So `WITHHELD` is printed as a word, in a style that marks it as a
 * state rather than a value.
 */

export const WITHHELD = "withheld";

export function isWithheld(value: unknown): boolean {
  return typeof value === "string" && value.trim().toLowerCase() === WITHHELD;
}

/** A count, with thousands separators. */
export function count(value: unknown): string {
  if (isWithheld(value)) return WITHHELD;
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString("en-GB");
}

/** A percentage, to one decimal place. */
export function percent(value: unknown, places = 1): string {
  if (isWithheld(value)) return WITHHELD;
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(places)}%`;
}

/** A confidence interval, as the pair it is. */
export function interval(low: unknown, high: unknown, places = 1): string {
  if (low === null || high === null || low === undefined || high === undefined) {
    return "—";
  }
  const a = Number(low);
  const b = Number(high);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return "—";
  return `${a.toFixed(places)}–${b.toFixed(places)}`;
}

/** A number for a chart axis: null where it cannot be drawn. */
export function numeric(value: unknown): number | null {
  if (value === null || value === undefined || isWithheld(value)) return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** "March 2024" rather than an ISO timestamp. */
export function monthYear(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

export function titleCase(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/** A column name from the Python side, as a reader should see it. */
export function humanise(key: string): string {
  return titleCase(
    key
      .replace(/_at_collection$/, "")
      .replace(/_/g, " ")
      .replace(/\bci\b/i, "95% CI")
      .trim(),
  );
}
