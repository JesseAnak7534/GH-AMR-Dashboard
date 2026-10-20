/**
 * Colour, mirrored from `src/palette.py`.
 *
 * The data colours are Okabe and Ito's eight-colour set, which stays
 * distinguishable under the three common forms of colour vision deficiency.
 * Roughly one man in twelve has one of them, and a surveillance chart that
 * separates resistant from susceptible by a red and a green hue alone is
 * unreadable to them -- not harder to read, unreadable.
 *
 * Two rules hold everywhere these are used.
 *
 * Colour repeats information; it never carries it alone. Every series
 * distinguished by colour is also distinguished by a label, a position or a
 * value printed beside it.
 *
 * Order is fixed. A sector keeps the same colour on every page, so a reader
 * who learns that aquaculture is the blue-green one does not have to relearn
 * it on the next page.
 *
 * The exported manifest carries the same values, so the Python analysis and
 * this site cannot drift apart silently: `lib/data.ts` reads the palette from
 * the manifest wherever a chart colours real data, and these constants are for
 * page furniture.
 */

export const OKABE_ITO = {
  black: "#000000",
  orange: "#E69F00",
  sky: "#56B4E9",
  green: "#009E73",
  yellow: "#F0E442",
  blue: "#0072B2",
  vermillion: "#D55E00",
  purple: "#CC79A7",
  grey: "#999999",
} as const;

/** The qualitative sequence, in the order it should be consumed. */
export const SEQUENCE = [
  OKABE_ITO.blue,
  OKABE_ITO.orange,
  OKABE_ITO.green,
  OKABE_ITO.vermillion,
  OKABE_ITO.sky,
  OKABE_ITO.purple,
  OKABE_ITO.yellow,
  OKABE_ITO.grey,
];

/** The colours the figure cards cycle through.
 *
 * Okabe-Ito, minus yellow: at #F0E442 a bold number on white is unreadable,
 * and a card whose figure cannot be read is not a card. */
export const STAT_SEQUENCE = [
  OKABE_ITO.blue,
  OKABE_ITO.vermillion,
  OKABE_ITO.green,
  OKABE_ITO.purple,
  OKABE_ITO.orange,
  OKABE_ITO.black,
];

export const SECTOR_COLOUR: Record<string, string> = {
  human: OKABE_ITO.blue,
  animal: OKABE_ITO.orange,
  food: OKABE_ITO.green,
  environment: OKABE_ITO.purple,
  aquaculture: OKABE_ITO.sky,
  all: "#1d4d43",
};

/**
 * Susceptibility. Vermillion against blue, not red against green: the
 * red/green pair is exactly the one that disappears under deuteranopia, and
 * S against R is the most consequential distinction on the platform.
 */
export const RESULT_COLOUR: Record<string, string> = {
  S: OKABE_ITO.blue,
  I: OKABE_ITO.orange,
  R: OKABE_ITO.vermillion,
  NS: OKABE_ITO.vermillion,
};

/** Anything withheld or not measured. The same grey everywhere, so a reader
 *  learns to read it as "no number here" rather than as a category. */
export const MISSING = OKABE_ITO.grey;

export function ramp(n: number): string[] {
  if (n <= 0) return [];
  const out: string[] = [];
  while (out.length < n) out.push(...SEQUENCE);
  return out.slice(0, n);
}

export function sectorColour(sector: string): string {
  return SECTOR_COLOUR[sector?.toLowerCase?.() ?? ""] ?? OKABE_ITO.grey;
}
