# Astrave 🛰️

> **NASA Space Apps Challenge · NISAR: The satellite that sees through clouds**
> Astrave is an interactive Earth observation web platform that visualizes surface change (floods, glacier motion, wetland loss) using Synthetic Aperture Radar (SAR) and optical satellite comparisons.

---

## 🚀 Quick Start

### Prerequisites
- [Node.js](https://nodejs.org/) (v18 or higher recommended; tested on Node v24)
- npm

### 1. Installation
Install the required dependencies (`express` and `nodemon`):
```bash
npm install
```

### 2. Run the Server
Start the local server:
```bash
npm start
```
The server will start on `http://localhost:3000`. If port 3000 is occupied, it automatically increments to the next free port and displays the active URL in your terminal.

For development with hot reloading:
```bash
npm run dev
```

### 3. Open in Browser
- **Home Page**: [http://localhost:3000/index.html](http://localhost:3000/index.html)
- **Event Viewer**: [http://localhost:3000/viewer.html](http://localhost:3000/viewer.html)
  - Flood: [http://localhost:3000/viewer.html#flood](http://localhost:3000/viewer.html#flood)
  - Glacier: [http://localhost:3000/viewer.html#glacier](http://localhost:3000/viewer.html#glacier)
  - Wetland: [http://localhost:3000/viewer.html#wetland](http://localhost:3000/viewer.html#wetland)
- **How SAR Works**: [http://localhost:3000/how-sar.html](http://localhost:3000/how-sar.html)
- **Data Sources & Credits**: [http://localhost:3000/data.html](http://localhost:3000/data.html)

The feedback form requires the Express API. VS Code's Live Server only serves static files, so run `npm start` and use the URL printed by the app.

---

## Bhoonidhi NISAR S-band search

The optional Python client and CLI search Bhoonidhi's STAC catalogue for NISAR S-band products. Bhoonidhi requires a registered account; NASA/ASF remains the source for NISAR L-band data. Search results are metadata, while `.h5` products can be tens of gigabytes. The client does not download anything unless a caller explicitly invokes its `download_item` method.

Python 3.10 or later is required.

Install the Python dependencies and configure credentials locally:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `BHOONIDHI_USER` and `BHOONIDHI_PASSWORD` in `.env` or as environment variables. Do not commit `.env` or share tokens. The CLI confirms the requested collection against the live catalogue before searching:

```powershell
# First inspect a small sample and its real property names
python -m scripts.search_nisar_s --collection NISAR_SSAR_GCOV --bbox 77,28,78,29 --start-date 2026-07-08 --end-date 2026-07-15 --limit 5 --max-items 5 --inspect-properties --output preview.geojson

# Then run a bounded metadata search and save a CSV
python -m scripts.search_nisar_s --collection NISAR_SSAR_GCOV --bbox 77,28,78,29 --start-date 2026-07-08 --end-date 2026-07-15 --online-only --max-items 50 --output results.csv
```

Use `--intersects @aoi.geojson` instead of `--bbox` for a GeoJSON geometry, `--datetime` for an RFC 3339 instant/range, and `--filter-json @filter.json` for CQL2-JSON filters. Inspect a real item's properties before selecting field names. By default the CLI reports `Online=Y/N/unknown`; `--online-only` adds the documented `Online='Y'` filter. It reports file sizes from item metadata when present and otherwise uses published typical sizes where available.

The client caches access/refresh tokens in memory, refreshes expired sessions, follows same-origin STAC `next` links, waits at least 0.4 seconds between search requests, and backs off on transient API errors. Its download helper rejects products unless `Online='Y'`, streams to a `.part` file, checks the advertised content length, and only renames a complete file. Downloads are rate-limited to one request every 30 seconds per client instance and concurrency defaults to two (maximum five). Confirm a product's size and obtain user approval before calling the download helper. Do not scrape or automate the Bhoonidhi web portal; if an API request fails with `Invalid session detected`, stop and contact [Bhoonidhi support](mailto:bhoonidhi@nrsc.gov.in) or use Browse & Order.

Official specification: [Bhoonidhi Data Access Software Interface Specification](https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/).

## 📡 API Endpoints

All endpoints return standard JSON responses with appropriate HTTP status codes (200, 404, 500):

- `GET /api/events` — Returns summary list of events (`flood`, `glacier`, `wetland`) with thumbnails and descriptions.
- `GET /api/events/:id` — Detailed event dataset including before/after images, dates, sample metric values, gap days, bounding box (`[south, west, north, east]`), and full attribution metadata. Returns 404 if event is unknown.
- `GET /api/sources` — Rows for the Data Sources and Datasets table.
- `GET /api/team` — 5 NASA Space Apps team members with roles and names.
- `GET /api/steps` — The 4 sequential steps explaining Synthetic Aperture Radar.

---

## 📊 Features & Architecture

- **Vanilla Frontend**: Pure vanilla HTML5, CSS3, and JavaScript — no heavyweight frontend framework.
- **Bundled Event Data**: The Event viewer loads Flood, Glacier, and Wetland records from `public/data/events.json`, so event data does not require the API server.
- **Before/After Split Slider**: Compare two satellite passes with draggable handle, range slider input, touch support, and full keyboard navigation (arrow keys, Home, End).
- **Change Area Highlight**: Toggleable tinted overlay highlighting surface change on the After image.
- **Interactive Global Map**: Leaflet map uses NASA GIBS MODIS Terra true-color WMTS imagery for context, with a date picker, basemap selector, opacity control, and the study-area bounding box. The viewer reads the layer's format, matrix set, zoom level, tile URL, and available dates from live GIBS capabilities. GIBS tiles are pre-rendered visualization, not NISAR science data.
- **Dark/Light Theming & Accessibility**: Respects `prefers-color-scheme`, `prefers-reduced-motion`, visible focus rings, ARIA roles (`role="status"`, `aria-pressed`, `aria-label`).
- **Optimized Media**: Original 22.3 MB GIF converted to 4.2 MB WebP and 955 KB MP4. All satellite imagery scaled to max 1600px wide.

### Bhoonidhi Python CLI tests

Run the isolated client and CLI unit tests (all network responses are mocked) with:

```powershell
python -m unittest discover -s tests -v
```

---

## ⚖️ Honesty Rules & Scientific Attribution

In accordance with scientific integrity guidelines:
- **Sample Data**: The viewer's metric values (percentages, estimated rates, gap days) remain illustrative **Sample data**; they are not computed from downloaded NISAR products. NISAR L-band products are distributed through NASA/ASF, while the Bhoonidhi tooling above searches for S-band products.
- **Satellite Labelling**: No proxy image is falsely labelled as NISAR. All satellite imagery is credited with its true origin:
  - **River flood**: Copernicus Sentinel-1 C-band SAR & Copernicus Sentinel-2 MSI (ESA / European Union).
  - **Glacier movement**: Copernicus Sentinel-1 C-SAR & Sentinel-2 (ESA / European Union) over Jakobshavn Glacier / Ilulissat Icefjord, Greenland.
  - **Wetland change**: Copernicus Sentinel-2 (Fuente de Piedra, Spain) and NASA/JPL UAVSAR & ALOS PALSAR L-band SAR (Pacaya-Samiria, Amazon Basin).

### To Replace Sample Data with NISAR Products
When integrating NISAR products from NASA Earthdata / ASF DAAC (L-band) or Bhoonidhi (S-band):
1. `before.value` and `after.value`: Replace illustrative percentages with NISAR L-band backscatter intensity (dB), interferometric coherence ($\gamma$), or surface water extent ($km^2$).
2. `before.image` and `after.image`: Replace with calibrated geocoded NISAR GCOV (Geocoded Polarimetric Covariance) or GSV (Geocoded Surface Velocity) rasters.
3. `before.date` and `after.date`: Replace with exact 12-day NISAR repeat orbit acquisition dates.
4. `gapDays`: Replace with actual orbital revisit difference (typically 12 or 24 days).
