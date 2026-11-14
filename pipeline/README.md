# CMR metadata search

Create a virtual environment and install the pipeline dependency:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -r pipeline/requirements.txt
# macOS/Linux:
.venv/bin/python -m pip install -r pipeline/requirements.txt
```

Run the search once to print available NISAR collections:

```bash
# Windows:
.venv\Scripts\python pipeline\cmr_search.py
# macOS/Linux:
.venv/bin/python pipeline/cmr_search.py
```

Read the printed collection list and copy a collection ID into
`pipeline/config.json`. With `bbox` and `temporal` left empty, the script reads
each event's bounding box and before/after dates from `public/data/events.json`,
searches each event separately, and saves the results to
`public/data/granule_search.json`. Filling both fields runs one custom search
instead.

## India event data

The configured collection is `C3622241360-ASF` (`NISAR_L2_GCOV_V1`), the
validated Geocoded Polarimetric Covariance Product. The event bounding boxes
and search window are read from `public/data/india/events.json`; the 2026
search window checks current product availability and is not the date of each
historical event. The script records metadata only and does not download radar
imagery. To change products, set `collection_id` in `pipeline/config.json`.
If it is empty, the script prints the available NISAR collections. Run:

```bash
# Windows:
.venv\Scripts\python pipeline\india_data.py
# macOS/Linux:
.venv/bin/python pipeline/india_data.py
```

The script saves one JSON result file per India event under
`public/data/india/`.
