/**
 * Reading the published figures.
 *
 * The files in `public/data` are written by `scripts/export_public_data.py`,
 * which runs the platform's own analysis and then its disclosure control. They
 * are read here with `fs`, at build time, in server components -- not fetched
 * in the browser. Three consequences, all of them wanted:
 *
 * The page arrives rendered. A reader on a slow connection in Accra sees the
 * figures in the first paint rather than a spinner waiting on a request.
 *
 * There is nothing to query. No API, no credentials, no endpoint that could be
 * asked a narrower question than the one the export decided to answer.
 *
 * A missing file fails the build rather than the page. If an export has not
 * been run, `npm run build` stops here with the path it wanted, instead of
 * shipping a site with empty sections.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "public", "data");

function read<T>(name: string): T {
  const file = path.join(DATA_DIR, name);
  try {
    return JSON.parse(readFileSync(file, "utf-8")) as T;
  } catch (error) {
    throw new Error(
      `Could not read ${file}. Run \`python scripts/export_public_data.py\` ` +
        `from the repository root first. (${(error as Error).message})`,
    );
  }
}

// ---------------------------------------------------------------------------
// Shapes
// ---------------------------------------------------------------------------

/** A count or the word "withheld". The union is the whole point: a suppressed
 *  cell is a different kind of thing from a number, and the type says so. */
export type Cell = number | string | null;

export interface Suppression {
  withheld: number;
  primary: number;
  secondary: number;
  cellsTotal: number;
  threshold: number;
  summary: string;
}

export interface Manifest {
  generatedAt: string;
  threshold: number;
  minIsolatesForReporting: number;
  counts: {
    genomes: number;
    useRecords: number;
    specimens: number;
    isolates: number;
    results: number;
    organisms: number;
    laboratories: number;
    sectors: number;
    regions: number;
  };
  period: { first: string | null; last: string | null };
  sectors: string[];
  laboratories: string[];
  palette: {
    sector: Record<string, string>;
    sequence: string[];
    result: Record<string, string>;
    missing: string;
  };
}

export interface AntibiogramRow {
  organism: string;
  antibiotic: string;
  tested: Cell;
  susceptible?: Cell;
  resistant?: Cell;
  percent_susceptible: number | null;
  percent_resistant?: number | null;
  ci_low: number | null;
  ci_high: number | null;
  breakpoints?: string;
  status?: string;
}

export interface StratumRow {
  stratum: string;
  isolates: Cell;
  observations: number;
  susceptible: number;
  non_susceptible: number;
  percent_non_susceptible: number | null;
  ci_low: number | null;
  ci_high: number | null;
  distinct_pairs: number;
  status: string;
}

export interface ResistanceSlice {
  sector: string;
  colour: string;
  isolates: number;
  pairsTotal: number;
  pairsReported: number;
  pairsSuppressed: number;
  rows: AntibiogramRow[];
  suppression: Suppression;
  strata: { key: string; label: string; rows: StratumRow[]; suppression: Suppression }[];
  method: { deduplication: string; qcExcluded: number; minIsolates: number };
}

export interface ResistanceData {
  slices: ResistanceSlice[];
  minIsolatesForReporting: number;
}

export interface OrganismSlice {
  sector: string;
  colour: string;
  organisms: number;
  isolates: number;
  laboratories: number;
  rows: { organism: string; isolates: Cell; percent: number | null }[];
  suppression: Suppression;
  specimenTypes: { specimenType: string; isolates: Cell }[];
  specimenTypeSuppression: Suppression;
  sterileSitePercent: number | null;
}

export interface OrganismData {
  slices: OrganismSlice[];
  deduplication: string;
}

export interface OneHealthData {
  sectors: { sector: string; isolates: Cell; colour: string }[];
  sectorSuppression: Suppression;
  sharedOrganisms: { organism: string; sector: string; isolates: Cell }[];
  sharedSuppression: Suppression;
  organismsTotal: number;
  organismsShared: number;
  isolates: number;
  sectorsPresent: string[];
  deduplication: string;
  palette: Record<string, string>;
}

export interface GenomicsData {
  coverage?: Record<string, number | string | null>;
  determinants: {
    group: string;
    determinant: string;
    mechanism: string;
    isolates: Cell;
    genomes_examined: number;
    percent: number | null;
    database: string;
  }[];
  determinantSuppression?: Suppression;
  concordance: {
    summary: Record<string, number | string | null>;
    verdicts: { verdict: string; pairs: number }[];
    agents: { antibiotic: string; pairs: Cell }[];
    agentSuppression: Suppression;
  } | null;
  clusters: {
    cluster_id: string;
    method: string;
    isolates: number;
    organisms: number;
    organism: string;
    sectors: number;
    sector_mix: string;
    sequence_types: string;
    labs: number;
    span_days: number;
  }[];
  clustersTotal: number;
  clustersWithheld: number;
  clustersUnassigned: number;
  clusterMethods: string[];
  clusterSummary?: string;
  verdictLabels?: Record<string, string>;
  sequenced?: number;
  sequenceTypes?: { sequence_type: string; genomes: Cell }[];
  sequenceTypeSuppression?: Suppression;
  plasmids?: {
    label: string;
    examined?: number;
    rows: { name: string; genomes: Cell; percent: number | null }[];
    suppression?: Suppression;
  };
  virulence?: {
    label: string;
    examined?: number;
    rows: { name: string; genomes: Cell; percent: number | null }[];
    suppression?: Suppression;
  };
}

export interface PooledBlock {
  by: string;
  rows: Record<string, Cell>[];
  suppression: Suppression;
  caveat: string;
}

export interface UseData {
  amu: PooledBlock[];
  amc: PooledBlock[];
  pps: {
    surveys: number;
    patients?: number;
    onAntibiotics?: number;
    prevalencePercent?: number | null;
    prescriptions?: number;
    indicationDocumentedPercent?: number | null;
    breakdowns?: {
      key: string;
      label: string;
      rows: { value: string; prescriptions: Cell }[];
      suppression: Suppression;
    }[];
  };
}

export interface AboutData {
  minIsolatesForReporting: number;
  minPublicCell: number;
  withheldLabel: string;
  completeness: Record<string, Cell>[];
  completenessError?: string;
  metrics: Record<string, Cell>[];
  deduplication?: string;
}

// ---------------------------------------------------------------------------
// Loaders
// ---------------------------------------------------------------------------

export const getManifest = () => read<Manifest>("manifest.json");
export const getResistance = () => read<ResistanceData>("resistance.json");
export const getOrganisms = () => read<OrganismData>("organisms.json");
export const getOneHealth = () => read<OneHealthData>("one-health.json");
export const getGenomics = () => read<GenomicsData>("genomics.json");
export const getUse = () => read<UseData>("use.json");
export const getAbout = () => read<AboutData>("about.json");

// ---------------------------------------------------------------------------
// The sections, in one place
// ---------------------------------------------------------------------------

export interface SectionMeta {
  href: string;
  badge: string;
  title: string;
  blurb: string;
  colour: string;
  /** The figure on the card, drawn from the manifest and the section files. */
  stat: (m: Manifest) => { value: number; unit: string };
}

export const SECTIONS: SectionMeta[] = [
  {
    href: "/resistance",
    badge: "AST",
    title: "Resistance",
    blurb:
      "Susceptibility by organism and antibiotic, with the number of isolates behind every figure, and where the resistance sits.",
    colour: "#0072B2",
    stat: (m) => ({ value: m.counts.results, unit: "susceptibility results" }),
  },
  {
    href: "/trends",
    badge: "TIME",
    title: "Trends",
    blurb:
      "How resistance has moved by quarter, with the confidence band drawn so a change can be read against its uncertainty.",
    colour: "#56B4E9",
    stat: (m) => ({ value: m.counts.results, unit: "results over time" }),
  },
  {
    href: "/mdr",
    badge: "MDR",
    title: "Multidrug resistance",
    blurb:
      "Isolates resistant across three or more antimicrobial categories, to the Magiorakos definitions.",
    colour: "#000000",
    stat: (m) => ({ value: m.counts.isolates, unit: "isolates classified" }),
  },
  {
    href: "/regions",
    badge: "GEO",
    title: "Regions",
    blurb:
      "Where the isolates were collected, region by region, and how much each region contributes.",
    colour: "#1d4d43",
    stat: (m) => ({ value: m.counts.regions, unit: "regions reporting" }),
  },
  {
    href: "/organisms",
    badge: "ORG",
    title: "Organisms",
    blurb:
      "What is being isolated, counted as isolates rather than as test results, and the specimens they came from.",
    colour: "#D55E00",
    stat: (m) => ({ value: m.counts.organisms, unit: "organisms identified" }),
  },
  {
    href: "/one-health",
    badge: "OH",
    title: "One Health",
    blurb:
      "Human, animal, food, environmental and aquaculture surveillance side by side, never pooled into one national rate.",
    colour: "#009E73",
    stat: (m) => ({ value: m.counts.sectors, unit: "sectors under surveillance" }),
  },
  {
    href: "/genomics",
    badge: "WGS",
    title: "Genomics",
    blurb:
      "The mechanisms behind the resistance, how often they explain the laboratory result, and which genomes look alike.",
    colour: "#CC79A7",
    stat: (m) => ({ value: m.counts.genomes, unit: "genomes sequenced" }),
  },
  {
    href: "/antimicrobial-use",
    badge: "AMU",
    title: "Antimicrobial use",
    blurb:
      "Human and veterinary consumption and hospital prescribing, as pooled rates with their denominators.",
    colour: "#E69F00",
    stat: (m) => ({
      value: m.counts.useRecords,
      unit: "use and prescribing records",
    }),
  },
  {
    href: "/about",
    badge: "DOC",
    title: "About this data",
    blurb:
      "How every figure is calculated, what is withheld and why, and what laboratory-based surveillance cannot tell you.",
    colour: "#999999",
    stat: (m) => ({ value: m.counts.laboratories, unit: "contributing laboratories" }),
  },
];

// ---------------------------------------------------------------------------
// Sections added after the first release
// ---------------------------------------------------------------------------

export interface TrendPeriodRow {
  period: string;
  isolates: Cell;
  observations: number;
  percent_non_susceptible: number | null;
  ci_low: number | null;
  ci_high: number | null;
  status: string;
}

export interface TrendPairRow {
  period: string;
  tested: Cell;
  percent_susceptible: number | null;
  ci_low: number | null;
  ci_high: number | null;
}

export interface TrendsData {
  slices: {
    sector: string;
    colour: string;
    periods: TrendPeriodRow[];
    suppression: Suppression;
    series: {
      organism: string;
      antibiotic: string;
      points: TrendPairRow[];
      suppression: Suppression;
    }[];
  }[];
  frequency: string;
  minObservations: number;
}

export interface MdrData {
  slices: {
    name: string;
    colour: string;
    isolates: number;
    classifiable: number;
    insufficient: number;
    percent: Record<string, number>;
    counts: { classification: string; isolates: Cell }[];
    countsSuppression: Suppression;
    byOrganism: { organism: string; classification: string; isolates: Cell }[];
    byOrganismSuppression: Suppression;
  }[];
  deduplication: string;
  definitions: Record<string, string>;
}

export interface RegionsData {
  regions: {
    region: string;
    isolates: Cell;
    organisms: number;
    laboratories: number;
    observations?: number;
    percent_non_susceptible: number | null;
    ci_low: number | null;
    ci_high: number | null;
  }[];
  suppression: Suppression;
  bySector: { region: string; sector: string; isolates: Cell }[];
  bySectorSuppression: Suppression;
  centroids: Record<string, { lat: number; lon: number }>;
  deduplication: string;
  palette: Record<string, string>;
}

export interface PriorityEntry {
  tier: string;
  organism: string;
  resistance: string;
  isolates: number | null;
  matched: string[];
  underSurveillance: boolean;
}

export interface PriorityData {
  who: PriorityEntry[];
  ghana: PriorityEntry[];
  tierOrder: string[];
}

export const getTrends = () => read<TrendsData>("trends.json");
export const getMdr = () => read<MdrData>("mdr.json");
export const getRegions = () => read<RegionsData>("regions.json");
export const getPriority = () => read<PriorityData>("priority.json");

/** The manifest of pre-computed filtered views. See lib/slices.ts. */
export interface FiltersFile {
  resistance: {
    dimensions: { key: string; label: string; note?: string }[];
    available: Record<
      string,
      Record<
        string,
        { value: string; slug: string; isolates: number; pairsReported?: number }[]
      >
    >;
  };
  organisms: {
    dimensions: { key: string; label: string; note?: string }[];
    available: Record<
      string,
      Record<string, { value: string; slug: string; isolates: number }[]>
    >;
  };
}

export const getFilters = () => read<FiltersFile>("filters.json");
