"use client";

/**
 * Taking a figure away with you.
 *
 * The Streamlit pages this replaced gave every chart a toolbar and every table
 * a download, and a surveillance site people quote from needs that: the
 * numbers behind a figure are the point, and a reader who cannot get at them
 * has to retype them.
 *
 * What a reader can take is the picture, for a slide or a report. The rows
 * behind it are not downloadable anywhere on this site: the figure and its
 * printed values are what is published.
 */

export function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked on the next tick: revoking immediately cancels the download in
  // some browsers before it has started.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Rasterise an inline SVG to a PNG.
 *
 * The SVG is serialised, not screenshotted, so the result is as sharp as the
 * scale asks for. Two things have to be fixed up first: the font, which the
 * rasteriser does not inherit from the page, and the background, which is
 * transparent and would make black text invisible on a dark slide.
 */
export async function svgToPng(
  svg: SVGSVGElement,
  filename: string,
  scale = 2,
): Promise<void> {
  const clone = svg.cloneNode(true) as SVGSVGElement;

  const box = svg.getBoundingClientRect();
  const viewBox = svg.viewBox.baseVal;
  const width = viewBox?.width || box.width || 800;
  const height = viewBox?.height || box.height || 400;

  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.style.fontFamily =
    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

  const backdrop = document.createElementNS(
    "http://www.w3.org/2000/svg", "rect");
  backdrop.setAttribute("x", "0");
  backdrop.setAttribute("y", "0");
  backdrop.setAttribute("width", String(width));
  backdrop.setAttribute("height", String(height));
  backdrop.setAttribute("fill", "#ffffff");
  clone.insertBefore(backdrop, clone.firstChild);

  const source = new XMLSerializer().serializeToString(clone);
  const encoded =
    "data:image/svg+xml;charset=utf-8," + encodeURIComponent(source);

  const image = new Image();
  image.crossOrigin = "anonymous";
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error("could not rasterise the figure"));
    image.src = encoded;
  });

  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("no 2d canvas context");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);

  await new Promise<void>((resolve) => {
    canvas.toBlob((blob) => {
      if (blob) {
        download(blob, filename.endsWith(".png") ? filename : `${filename}.png`);
      }
      resolve();
    }, "image/png");
  });
}

/** A filename that says what the figure is and when it was taken. */
export function figureFilename(title: string, extra?: string): string {
  const slug = (text: string) =>
    text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const stamp = new Date().toISOString().slice(0, 10);
  return ["amrss", slug(title), extra ? slug(extra) : "", stamp]
    .filter(Boolean)
    .join("-");
}
