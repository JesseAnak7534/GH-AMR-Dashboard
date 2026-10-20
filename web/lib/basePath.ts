/**
 * Where the site is served from.
 *
 * On a GitHub Pages project site the whole site lives under a sub-path --
 * `/GH-AMR-Dashboard` -- rather than at the root of a domain. Next.js rewrites
 * its own links and bundles for that automatically once `basePath` is set, but
 * it cannot rewrite a string this code builds by hand: the `fetch` for a
 * filtered slice, or the `src` of the map iframe. Those are absolute paths and
 * would 404 on anything but a root domain.
 *
 * So the prefix is read from the environment at build time and applied where
 * we build a URL ourselves. Empty locally and on a root domain, which is why
 * `npm run dev` is unaffected.
 */
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** An absolute path within the site, correct wherever the site is served. */
export function asset(path: string): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  return `${BASE_PATH}${clean}`;
}
