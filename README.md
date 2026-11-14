# 🌍 ASTRAV//E
### Making Earth's Invisible Changes Visible.

**ASTRAV//E** is a SAR-powered Earth Surface Change Monitoring and Intelligence Platform designed to make changes across Earth's surface easier to explore, visualize and understand using NASA-ISRO NISAR satellite data.

From wetland loss and flooding to forest disturbances, agricultural changes and land deformation, ASTRAV//E aims to transform complex Earth observation data into accessible geographical insights.

---

## 🚀 The Problem

Earth's surface is constantly changing due to natural processes and human activities. However, identifying, monitoring and understanding these changes using satellite observations can be challenging.

Traditional optical satellite imagery can be limited by cloud cover and lighting conditions. Meanwhile, Synthetic Aperture Radar (SAR) data offers powerful observation capabilities but can be difficult for non-specialists to access, interpret and communicate.

There is a need for an accessible platform that bridges the gap between complex satellite observations and meaningful environmental insights.

## 💡 Our Solution

ASTRAV//E provides an interactive geospatial environment for exploring Earth surface changes through SAR satellite observations.

Our platform focuses on:

- 🌐 **Interactive Global Exploration** — Explore geographical locations and Areas of Interest (AOIs).
- 🛰️ **NISAR Data Discovery** — Connect with NASA and ISRO Earth observation catalogues.
- 🔍 **Multi-Date Comparison** — Explore satellite observations from different dates.
- 🗺️ **Geospatial Visualization** — Understand geographical changes through interactive maps and overlays.
- 📊 **Change Monitoring** — Support the investigation of changes in Earth's surface.
- 📡 **Multi-Source Integration** — Bring together NASA and ISRO Earth observation data discovery workflows.

## ✨ Key Features

| Feature | Description |
|---|---|
| Interactive Map | Explore geographical locations using Leaflet.js |
| AOI Exploration | Represent Areas of Interest using geographical boundaries |
| Before/After Slider | Compare satellite imagery interactively |
| Change Overlay | Toggle visual change-detection overlays |
| Satellite Catalogue Search | Discover NISAR products through NASA and ISRO integrations |
| Data Source Explorer | Explore available satellite data sources |
| Responsive Interface | Adaptable interface with light/dark themes |
| Accessibility | Keyboard navigation, ARIA attributes and reduced-motion support |

## 🛰️ Earth Observation Integrations

ASTRAV//E connects with multiple Earth observation services.

### 1. NASA CMR — Common Metadata Repository
Used for discovering NASA Earth science datasets and associated satellite metadata.

### 2. Alaska Satellite Facility (ASF)
Provides SAR data discovery workflows and access to NASA Earthdata products, including NISAR L-band product searches.

### 3. ISRO Bhoonidhi STAC API
A custom Python client integrates with the Bhoonidhi STAC catalogue to discover NISAR S-band products using CQL2-JSON filters and GeoJSON Areas of Interest.

### 4. NASA GIBS
Integrates MODIS Terra true-colour imagery through WMTS to provide geographical context and interactive map baselayers.

> **Note:** NASA GIBS MODIS imagery is used as geographical basemap context. It is not NISAR SAR imagery. Catalogue discovery also does not automatically mean that a product has been downloaded or scientifically processed.

## 🏗️ Technology Stack

### Frontend
- HTML5
- CSS3
- Vanilla JavaScript (ES6+)
- Leaflet.js v1.9.4
- Google Fonts — Bricolage Grotesque

### Backend
- Node.js v18+
- Express.js 4.x
- Nodemon
- REST API architecture

### Satellite Data Pipeline
- Python 3.10+
- Requests
- Python-dotenv
- NASA CMR
- Alaska Satellite Facility (ASF)
- ISRO Bhoonidhi STAC API
- NASA GIBS WMTS

### Testing & Data Formats
- Python unittest
- unittest.mock
- GeoJSON
- JSON
- CSV
- HDF5 (.h5)

## 🧩 System Architecture

```text
                 ASTRAV//E
                     |
          FRONTEND APPLICATION
          HTML / CSS / JavaScript
                     |
                Leaflet.js
                     |
              REST API REQUESTS
                     |
              NODE.JS + EXPRESS
                     |
          PYTHON DATA WORKFLOWS
                     |
        +------------+------------+
        |            |            |
      NASA         ASF         ISRO
      CMR        NISAR L       Bhoonidhi
                   Band        S Band
        |            |            |
        +------------+------------+
                     |
              SATELLITE DATA
              DISCOVERY RESULTS

        NASA GIBS → MAP BASEMAP TILES
```

## 📂 Project Structure

```text
ASTRAV-E/
│
├── public/                 # Frontend assets
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
│
├── scripts/
│   └── search_nisar_s.py   # Bhoonidhi search CLI
│
├── bhoonidhi_client.py    # ISRO STAC API client
├── cmr_search.py          # NASA CMR catalogue search
├── asf_workflow.py        # ASF search workflow
│
├── tests/                 # Python automated tests
│
├── events.json            # Project event data
├── sources.json           # Data source metadata
├── package.json
├── requirements.txt
└── README.md
```

*The directory overview is illustrative; adjust filenames and folders to match the actual repository.*

## ⚙️ Getting Started

### Prerequisites

Make sure you have the following installed:

- Node.js v18 or later
- npm
- Python 3.10 or later
- Git

### 1. Clone the Repository

```bash
git clone YOUR_REPOSITORY_URL
cd ASTRAV-E
```

### 2. Install Node Dependencies

```bash
npm install
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root and add the credentials required by the relevant data services.

```env
# Add required service credentials here
```

Never commit API credentials, passwords or private tokens to GitHub.

### 5. Start the Application

```bash
npm run dev
```

If a development script is not configured, use:

```bash
node server.js
```

Open the local URL printed by the server in your browser.

### 6. Run Python Tests

```bash
python -m unittest discover -s tests -v
```

## 🌱 Potential Applications

ASTRAV//E can support exploration and research across several domains:

- **Disaster Management:** Investigating flood extent and post-disaster surface changes.
- **Environmental Monitoring:** Exploring wetland changes and forest disturbances.
- **Agriculture:** Investigating agricultural surface conditions and moisture-related changes.
- **Climate Research:** Exploring glacier and ice-surface changes.
- **Urban Planning:** Investigating land-use changes and possible ground deformation.
- **Scientific Research:** Making multi-temporal SAR observations easier to explore.

## 🔬 Future Scope

We envision expanding ASTRAV//E with:

- Advanced SAR preprocessing and calibrated backscatter analysis.
- Automated multi-temporal change detection.
- InSAR-based surface deformation analysis.
- Time-series visualization and historical monitoring.
- Raster processing using Rasterio, NumPy and GDAL.
- Spatial analysis and geographical data management.
- Downloadable analytical reports.
- Additional environmental and population datasets for contextual analysis.

## ⚠️ Scientific Considerations

SAR backscatter changes can be influenced by several factors, including surface roughness, moisture, vegetation structure, incidence angle and acquisition geometry.

A detected change does not automatically establish its cause. Reliable interpretation requires compatible satellite observations, appropriate processing, supporting datasets and, where possible, ground validation.

ASTRAV//E aims to communicate these uncertainties rather than present every detected difference as a confirmed environmental event.

## 🎯 Our Vision

We believe satellite data should not remain accessible only to remote-sensing specialists.

ASTRAV//E aims to bridge the gap between complex radar observations and understandable environmental information, helping researchers, decision-makers, students and communities explore the changing face of our planet.

**Making Earth's Invisible Changes Visible.**

---

## 👥 Team

Developed as part of the **NASA Space Apps Challenge**.

**Project:** ASTRAV//E  
**Challenge:** The Dance of Earth's Surface  
**Domain:** Earth Observation · SAR · Geospatial Intelligence

---

## 📜 Acknowledgements

We acknowledge the organizations and open Earth observation infrastructure that make this project possible:

- NASA — National Aeronautics and Space Administration
- ISRO — Indian Space Research Organisation
- Alaska Satellite Facility (ASF)
- NASA Earthdata / Common Metadata Repository
- NASA Global Imagery Browse Services (GIBS)
- Leaflet.js

---

**ASTRAV//E — Making Earth's Invisible Changes Visible.**
