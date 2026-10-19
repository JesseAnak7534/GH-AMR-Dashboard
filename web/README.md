Written for: whoever picks up this repository next, including the author in six months.

# The public site

A Next.js static site holding the public face of ICBB-AMRSS: resistance,
organisms, One Health, genomics, antimicrobial use, and how to read any of it.

It is not the platform. The Streamlit application in the repository root is
where data is uploaded, validated, traced and analysed, and where the staff
pages live behind a password. This site publishes the part of that work which
is meant to be read by anyone.

## How the two fit together

```
  Supabase (PostgreSQL)
          │
          │   src/surveillance.py · src/genomics.py · src/consumption.py
          │   the analysis: CLSI M39 deduplication, Wilson intervals,
          │   the thirty-isolate floor, pooled (never averaged) rates
          ▼
  scripts/export_public_data.py
          │   src/disclosure.py runs here: small cells withheld, and a
          │   second cell withheld where the first could be recovered
          │   by subtraction
          ▼
  web/public/data/*.json      ← the only thing this site ever reads
          │
          ▼
  web/  (Next.js, static export)
```

**The site holds no database connection.** It reads JSON written by the export
and renders it. There is no API route, no credential and nothing to query.

**Disclosure control runs before anything leaves the machine.** A live public
API would have to suppress correctly on every request, for every combination of
filters a visitor can invent, forever. A snapshot has to be right once, in one
file, where it can be tested. The risk on a public surveillance page was never
the headline figures — it is a visitor narrowing by sector, region, laboratory
and organism until a cell holds one person. Publishing pre-computed slices
removes the ability to narrow that far, which is why the site offers a sector
switch and in-table search rather than arbitrary filtering: both only ever
reach rows the export already decided to publish.

**The analysis stays in Python.** Re-implementing deduplication or Wilson
intervals in TypeScript would mean two definitions of every number and no way
to tell which one is on screen.

## Running it

From the repository root, with the Python environment that runs the platform:

```bash
python scripts/export_public_data.py        # writes web/public/data/*.json
cd web
npm install
npm run dev                                 # http://localhost:3000
```

To produce the deployable site:

```bash
npm run build        # static HTML into web/out/
```

`web/out/` is a plain directory of files. It can be served by anything — a
static host, an object store, a web server on a university box. There is no
Node process in production.

The build fails if `web/public/data` is missing, by design: a site that
silently ships empty sections is worse than one that refuses to build.

## Refreshing the figures

Re-run the export and rebuild. The published JSON is committed, so the site can
always be built from a clean checkout without database access, and so a change
in a published figure shows up as a reviewable diff rather than appearing
silently.

```bash
python scripts/export_public_data.py
cd web && npm run build
```

The export accepts `--threshold` to raise the minimum publishable cell. It
cannot be lowered below the platform's floor; passing a smaller number raises it
back and says so.

## Layout

```
app/
  layout.tsx          masthead, section navigation, footer
  page.tsx            the landing page: nine cards, each one a link
  resistance/         antibiogram by sector, as intervals or as a matrix,
                      with the WHO and Ghana priority lists as a lens
  trends/             resistance by quarter, with confidence bands
  mdr/                MDR and XDR to the Magiorakos definitions
  regions/            the Folium map and the region table
  organisms/          what is being isolated, counted as isolates
  one-health/         sectors side by side; the cross-sector grid
  genomics/           determinants, concordance, clusters, STs, plasmids
  amu/                human consumption, DDD per 1,000 patient-days
  amc/                veterinary consumption, mg per kg biomass
  pps/                point prevalence of antibiotic use
components/
  Chrome.tsx          page header, sections, stat strips, notes
  Charts.tsx          SVG charts: bars, point-with-interval, proportion
  TrendChart.tsx      time series with its confidence band
  HeatGrid.tsx        the antibiogram as a matrix
  FoliumMap.tsx       embeds the Folium map built by the export
  Pooled.tsx          a pooled consumption rate, shared by AMU and AMC
  DataTable.tsx       sortable, searchable, withheld-aware table
  Segmented.tsx       the control that switches between published slices
lib/
  data.ts             reads public/data at build time; the shapes
  format.ts           number formatting, including the withheld case
  palette.ts          Okabe-Ito, mirrored from src/palette.py
```

Each section page is a server component that reads its JSON and hands it to a
client component for the interactive parts. The figures therefore arrive in the
HTML: a reader on a slow connection sees numbers in the first paint rather than
a spinner.

## Filters

Two kinds, and they are not interchangeable.

**Slice filters** — sector, period, region, laboratory — select a view that was
computed and suppressed in Python and written to its own file. Changing one
fetches a different published file; the default view is already in the HTML, so
only a non-default filter costs a request. The site cannot compose a
combination nobody exported, which is exactly what stops a reader narrowing
onto one person.

One secondary dimension at a time. The cross-product of sector, region,
laboratory and period is several thousand tables, almost all of them empty.

**Row filters** — organism, antibiotic, minimum isolates, mechanism — work on
rows already on the page. They can only show less than was published, never
more, so they run in the browser.

A slice holds only the rows that passed, so most are under a kilobyte: a region
with nothing publishable is a file of counts rather than a hundred withheld
rows. 194 slices come to about 280 KB in total.

### What the filters honestly return

A regional or laboratory antibiogram in this collection reaches the
thirty-isolate floor for **nought to eight** organism–antibiotic pairs out of
roughly a hundred and ten. Those filters are still offered, and each option
carries its own evidence in the dropdown — "Ahafo — 85 isolates, 0 rates" —
so a reader knows before selecting. Choosing one shows the counts and says
plainly that this is a statement about how much data the view holds, not about
how much resistance is in it.

Period filters do support rates: 43 to 59 published pairs per year.

## Rules the code keeps

**Copy stays short.** One line of intro per section, one method line per page,
and a limitation note only where a reader would otherwise draw a wrong
conclusion. The longer reasoning belongs in these docs and in the module
docstrings, not on screen.

**Withheld is never rendered as blank or zero.** A blank reads as "nothing
here" and a zero reads as "we looked and found none". Both are wrong, and
`lib/format.ts` and the table component treat the marker as a state rather than
a value. Sorting puts withheld rows at the end in both directions, because they
are the absence of a measurement, not a low one.

**Colour never carries meaning alone.** Every coloured series also has a label
or a printed value. The data colours are Okabe-Ito, which stays legible under
the three common forms of colour vision deficiency. Susceptibility uses blue
against vermillion rather than green against red, since that pair is exactly the
one that disappears under deuteranopia and S/I/R is the most consequential
distinction on the platform.

**Axes are not scaled to the data.** The susceptibility chart runs 0–100%. An
axis from 70 to 95 makes a five-point difference look like a collapse, and these
are figures people will quote.

**Trends deduplicate inside each period, not across the series.** A patient's
isolate a year later is next year's data point, not a repeat, and dropping it
would bend the line.

**MDR is only counted where enough categories were tested.** An isolate tested
against two categories cannot answer a question about three, so it is reported
as "insufficient testing" rather than as "not MDR" — otherwise a laboratory
with a small panel looks like one with little resistance.

**The region map is built by Folium**, in `scripts/export_map.py`, and embedded
as the page it produces — one map implementation rather than two, on the same
OpenStreetMap basemap and region centroids the Streamlit pages use. Circles,
not shading: no specimen carries coordinates and there are no boundary polygons
here. The map is of where specimens were collected, not of where resistance is.

**Suppression is a setting, not a constant.** The export defaults to
`--threshold 1`, which publishes every count, and says so on every run. The
machinery stays in place: `--threshold 5` or higher turns it back on and
nothing downstream changes. **Raise it before this site carries real patient
data.** The UI follows the setting — the withheld language and the withheld
columns appear only when something was actually withheld.

**Hospital identity is not published.** Laboratories are named — attribution is
the point of sentinel surveillance — but facility names are not, which is why
the consumption page offers no split by facility.

**Sectors are not pooled.** There is no "all sectors" option on the resistance
page, because a percentage mixing hospital isolates with river water describes
neither. Organism *counts* do offer one, since an animal isolate plus a human
isolate is genuinely two isolates.

## Charts are hand-written SVG

Deliberately, not for lack of a library. Error bars are first-class here rather
than an afterthought; a missing value is omitted and labelled rather than
plotted at the baseline; and the house style is thin rules and muted gridlines,
which is less work to write than to override. Every chart is accompanied by a
table of the same numbers, so nothing depends on seeing the picture.
