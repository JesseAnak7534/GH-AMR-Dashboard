/**
 * The site is a static export.
 *
 * There is no server, no API route and no database reachable from the web
 * tier. Every figure is read from the JSON in `public/data`, which
 * `scripts/export_public_data.py` writes after putting it through the
 * platform's disclosure control. That is the point of the architecture: a
 * static snapshot cannot be made to leak a small cell by a clever combination
 * of filters, because the filters only reach rows that were already published.
 *
 * `images.unoptimized` because the optimiser needs a running server, and
 * `trailingSlash` so the export's directory-per-route layout works on a plain
 * static host.
 */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
