/**
 * The Ghana map.
 *
 * Built by Folium in `scripts/export_map.py` and embedded here, so the
 * platform keeps one map implementation rather than two. The file is a
 * self-contained Leaflet page; an iframe is the honest way to include it,
 * and it keeps that page's scripts out of this one's scope.
 *
 * A `title` is set because an unlabelled iframe is unusable with a screen
 * reader, and the figures are repeated in the table below it so nothing
 * depends on the map loading at all.
 */
export function FoliumMap({
  src = "/maps/regions.html",
  height = 620,
  title = "Map of Ghana showing surveillance isolates by region",
}: {
  src?: string;
  height?: number;
  title?: string;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-rule">
      <iframe
        src={src}
        title={title}
        loading="lazy"
        className="block w-full"
        style={{ height, border: 0 }}
      />
    </div>
  );
}
