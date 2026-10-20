/**
 * The clinical sections: mechanisms, hospital infection, data coverage and
 * quality, comparison, and risk.
 *
 * Read the same way as everything in `data.ts` -- with `fs`, at build time, in
 * server components. They live in their own module because these five arrived
 * together and are the five largest shapes on the site; appending them to
 * `data.ts` would have doubled it.
 *
 * One of them is not read here. A single organism-agent comparison is fetched
 * in the browser from `public/data/slices/comparison`, because publishing ten
 * dimensions for six pairs in five sectors inside the page would be most of a
 * megabyte of tables for views most readers never open.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

import type { Cell, Suppression } from "@/lib/data";

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
// Resistance mechanisms
// ---------------------------------------------------------------------------

export interface SentinelRow {
  code: string;
  label: string;
  whoTier: string;
  positive: Cell;
  tested: Cell;
  percent: number | null;
}

export interface MechanismTotalRow {
  mechanism: string;
  isolates: Cell;
  percent: number | null;
  basis: string;
}

export interface MechanismOrganismRow {
  mechanism: string;
  organism: string;
  isolates: Cell;
  high: Cell;
  moderate: Cell;
}

export interface CrossResistanceRow {
  antibioticClass: string;
  isolates: Cell;
  high: Cell;
  moderate: Cell;
  testedOnTwoOrMore: number;
  percent: number | null;
}

export interface BreadthBandRow {
  band: string;
  isolates: Cell;
}

export interface BreadthOrganismRow {
  organism: string;
  isolates: Cell;
  medianAgents: number | null;
  maxAgents: number | null;
}

export interface MechanismSlice {
  sector: string;
  colour: string;
  isolatesScreened: number;
  observations: number;
  sentinel: { rows: SentinelRow[]; suppression: Suppression | null };
  mechanisms: {
    totals: MechanismTotalRow[];
    totalSuppression: Suppression | null;
    rows: MechanismOrganismRow[];
    suppression: Suppression | null;
  };
  crossResistance: {
    rows: CrossResistanceRow[];
    suppression: Suppression | null;
  };
  breadth: {
    bands: BreadthBandRow[];
    bandSuppression: Suppression | null;
    rows: BreadthOrganismRow[];
    suppression: Suppression | null;
    isolates?: number;
    isolatesScreened?: number;
    percent?: number | null;
    medianAgents?: number | null;
  };
}

export interface MechanismsData {
  slices: MechanismSlice[];
  basis: Record<string, string>;
}

export const getMechanisms = () => read<MechanismsData>("mechanisms.json");

// ---------------------------------------------------------------------------
// Hospital-acquired infection
// ---------------------------------------------------------------------------

export interface HaiGroupRow {
  group: string;
  observations: Cell;
  isolates: Cell;
  resistancePercent: number | null;
  mdrIsolates?: Cell;
}

export interface HaiData {
  available: boolean;
  headline?: {
    isolates: number;
    observations: number;
    nosocomialIsolates: number;
    nosocomialPercent: number | null;
    mdrIsolates: number;
    mdrPercent: number | null;
    resistancePercent: number | null;
    organisms: number;
    laboratories: number;
    classifiable: number;
  };
  eskape?: {
    rows: {
      organism: string;
      isolates: Cell;
      observations: Cell;
      resistancePercent: number | null;
      mdrIsolates: Cell;
      mdrPercent: number | null;
    }[];
    suppression: Suppression | null;
  };
  profile?: {
    rows: {
      organism: string;
      observations: Cell;
      isolates: Cell;
      resistancePercent: number | null;
      nosocomial: boolean;
    }[];
    suppression: Suppression | null;
  };
  split?: { rows: HaiGroupRow[]; suppression: Suppression | null };
  mdr?: {
    rows: { organism: string; isolates: Cell }[];
    suppression: Suppression | null;
    topOrganism: string | null;
    classes: {
      rows: {
        antibioticClass: string;
        observations: Cell;
        resistancePercent: number | null;
      }[];
      suppression: Suppression | null;
    } | null;
  };
  laboratories?: { rows: HaiGroupRow[]; suppression: Suppression | null };
  regions?: { rows: HaiGroupRow[]; suppression: Suppression | null };
  trend?: {
    points: {
      period: string;
      observations: number;
      resistancePercent: number | null;
      mdrPercent: number | null;
      nosocomialPercent: number | null;
    }[];
    minObservations: number;
  };
}

export const getHai = () => read<HaiData>("hai.json");

// ---------------------------------------------------------------------------
// Data coverage and quality
// ---------------------------------------------------------------------------

export interface QualityData {
  headline: string;
  coverage: {
    specimens: number;
    isolates: number;
    observations: number;
    patients: number;
    laboratories: number;
    sectors: { sector: string; specimens: number; colour: string }[];
  };
  completeness: {
    rows: {
      field: string;
      column: string;
      scope: string;
      recorded: number;
      of: number;
      percent: number | null;
      status: string;
    }[];
    notCollected: string[];
  };
  timeliness: {
    latest: string | null;
    daysSinceLatest: number | null;
    status: string;
    note: string;
    turnaroundMedianDays: number | null;
    turnaroundMeasurable: number;
  };
  linkage: {
    culturePositivityPercent: number | null;
    specimensTotal: number;
    specimensWithIsolate: number;
    specimensWithWard: number;
    specimensWithWardPercent: number | null;
    isolatesTotal: number;
    isolatesWithResult: number;
    isolatesWithResultPercent: number | null;
    genomicResults: number;
    isolatesSequenced: number;
    percentIsolatesSequenced: number | null;
  };
  resultQuality: {
    qcRecorded: number;
    qcTotal: number;
    qcRecordedPercent: number | null;
    qcPass: number;
    qcFail: number;
    resultsWithoutEdition: number;
    sources: { source: string; results: number }[];
  };
  plausibility: {
    rows: {
      organism: string;
      antibiotic: string;
      kind: string;
      results: Cell;
      recordedSusceptible: Cell;
      reason: string;
    }[];
    suppression: Suppression | null;
    impossiblePairs: number;
    suppressPairs: number;
    observationsAffected: number;
    percentAffected: number | null;
    recordedSusceptible: number;
    resultsTotal: number;
  };
  denominators: {
    available: boolean;
    rows: {
      dataset: string;
      records: number;
      denominator: string;
      withDenominator: number;
      percent: number | null;
      consequence: string;
    }[];
    metrics: Record<string, string>[];
    error?: string;
  };
}

export const getQuality = () => read<QualityData>("quality.json");

// ---------------------------------------------------------------------------
// Comparative analysis
// ---------------------------------------------------------------------------

export interface ComparisonRow {
  group: string;
  unit: Cell;
  percent: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  status: string;
  isolates?: Cell;
  tested?: Cell;
  pairs?: number;
  susceptible?: Cell;
  nonSusceptible?: Cell;
}

export interface ComparisonDimension {
  key: string;
  label: string;
  rows: ComparisonRow[];
  suppression: Suppression | null;
}

export interface ComparisonView {
  key: string;
  /** The slice file holding this view's tables, or null when they travel in
   *  the page. Only the pooled view travels in the page. */
  slug: string | null;
  label: string;
  measure: string;
  unitLabel: string;
  pooled: boolean;
  isolates?: number;
  dimensions: ComparisonDimension[] | null;
}

export interface ComparisonSlice {
  sector: string;
  colour: string;
  isolates: number;
  excludedPairs: number;
  views: ComparisonView[];
  periods: {
    months: number;
    rows: ComparisonRow[];
    suppression: Suppression | null;
  }[];
}

export interface ComparisonData {
  slices: ComparisonSlice[];
  minIsolatesForReporting: number;
  periods: number[];
}

export const getComparison = () => read<ComparisonData>("comparison.json");

// ---------------------------------------------------------------------------
// Risk assessment
// ---------------------------------------------------------------------------

export interface RiskSlice {
  sector: string;
  colour: string;
  statistics: {
    observations: number;
    resistant: number;
    intermediate: number;
    susceptible: number;
    resistancePercent: number | null;
    intermediatePercent: number | null;
    susceptiblePercent: number | null;
    organisms: number;
    antibiotics: number;
    isolates: number;
  };
  trend: {
    direction: string;
    firstHalfPercent: number | null;
    secondHalfPercent: number | null;
    changePoints: number | null;
    band: string | null;
  };
  scores: {
    rows: {
      organism: string;
      riskScore: Cell;
      riskLevel: string | null;
      resistancePercent: number | null;
      observations: Cell;
      antibioticDiversity: Cell;
      factors: string | null;
    }[];
    suppression: Suppression | null;
  };
  burden: {
    observations: number;
    resistantObservations: number;
    resistancePercent: number | null;
    band: string;
    rows: {
      group: string;
      observations: Cell;
      resistantObservations: Cell;
      resistancePercent: number | null;
    }[];
    suppression: Suppression | null;
  };
  emerging: {
    rows: {
      organism: string;
      antibiotic: string;
      resistancePercent: number | null;
      observations: Cell;
      severity: string;
    }[];
    suppression: Suppression | null;
    windowDays: number;
  };
  forecast: {
    points: { monthsAhead: number; percent: number }[];
    history: {
      period: string;
      observations: number;
      resistancePercent: number | null;
    }[];
    slope: number | null;
    confidence: string | null;
    error: string | null;
  };
  organismComparison: {
    rows: {
      organism: string;
      resistant: Cell;
      intermediate: Cell;
      susceptible: Cell;
      observations: Cell;
      resistancePercent: number | null;
    }[];
    suppression: Suppression | null;
  };
  antibioticComparison: {
    rows: {
      antibiotic: string;
      resistant: Cell;
      intermediate: Cell;
      susceptible: Cell;
      observations: Cell;
      resistancePercent: number | null;
      susceptibilityPercent: number | null;
    }[];
    suppression: Suppression | null;
  };
  susceptibilitySummary: {
    rows: {
      organism: string;
      antibiotic: string;
      tested: Cell;
      susceptible: Cell;
      susceptibilityPercent: number | null;
      ciLow: number | null;
      ciHigh: number | null;
      observation: string | null;
      meetsThreshold: boolean;
    }[];
    suppression: Suppression | null;
    pairs: number;
    reportable: number;
    provisional: number;
  };
}

export interface RiskData {
  slices: RiskSlice[];
  scoringRule: { component: string; condition: string; points: string }[];
  minIsolates: number;
}

export const getRisk = () => read<RiskData>("risk.json");
