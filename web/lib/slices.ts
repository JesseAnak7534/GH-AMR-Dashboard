"use client";

import { useEffect, useState } from "react";

/**
 * Fetching a filtered view.
 *
 * The default view is rendered on the server and arrives in the HTML, so the
 * page is readable before any JavaScript runs. Only a non-default filter costs
 * a request, and the files are small — most are under a kilobyte, because a
 * slice holds the rows that passed rather than a hundred withheld ones.
 *
 * Loading the lot into the page instead would have meant several megabytes of
 * HTML for views most readers never open.
 *
 * A failed fetch is reported, never silently swallowed into an empty table: a
 * blank page that looks like "no data" when it means "the file did not load"
 * is the same confusion this platform refuses everywhere else.
 */

export interface SliceState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export function useSlice<T>(
  section: string,
  fileSlug: string | null,
  fallback: T,
): SliceState<T> {
  const [state, setState] = useState<SliceState<T>>({
    data: fallback,
    loading: false,
    error: null,
  });

  useEffect(() => {
    if (!fileSlug) {
      setState({ data: fallback, loading: false, error: null });
      return;
    }

    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: null }));

    fetch(`/data/slices/${section}/${fileSlug}.json`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`${response.status} ${response.statusText}`);
        }
        return response.json();
      })
      .then((data: T) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setState({ data: null, loading: false, error: error.message });
        }
      });

    return () => {
      cancelled = true;
    };
    // `fallback` is a server-rendered constant for the default view; including
    // it would refetch on every render without changing what is fetched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, fileSlug]);

  return state;
}

export interface SliceEntry {
  value: string;
  slug: string;
  isolates: number;
  pairsReported?: number;
}

export interface FilterManifest {
  dimensions: { key: string; label: string; note?: string }[];
  available: Record<string, Record<string, SliceEntry[]>>;
}

export interface FiltersFile {
  resistance: FilterManifest;
  organisms: FilterManifest;
}

/** The slug for a chosen filter, or null for the unfiltered default. */
export function slugFor(
  manifest: FilterManifest,
  sector: string,
  dimension: string,
  value: string,
): string | null {
  if (!dimension || !value) return null;
  const entries = manifest.available?.[sector]?.[dimension] ?? [];
  return entries.find((entry) => entry.value === value)?.slug ?? null;
}

export function entriesFor(
  manifest: FilterManifest,
  sector: string,
  dimension: string,
): SliceEntry[] {
  return manifest.available?.[sector]?.[dimension] ?? [];
}
