# pip install requests
import json
import os
import sys
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests

BASE = "https://cmr.earthdata.nasa.gov/search"
HEADERS = {"Client-Id": "astrave-spaceapps"}
OUT_PATH = os.path.join("public", "data", "granule_search.json")
CONFIG_PATH = os.path.join("pipeline", "config.json")
EVENTS_PATH = os.path.join("public", "data", "events.json")


def clean_url(url):
    """Return the request URL with any token-like parameter removed."""
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if "token" not in k.lower()]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def get(url, params=None, extra_headers=None, retries=3):
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    for _ in range(retries):
        r = requests.get(url, params=params, headers=headers, timeout=60)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("retry-after", "5")))
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("CMR rate limit: retries exhausted")


# STEP 1: list NISAR collections so the real IDs and names can be read
def list_collections():
    r = get(f"{BASE}/collections.json", {"keyword": "NISAR", "page_size": 100})
    entries = r.json()["feed"]["entry"]
    for e in entries:
        print(
            e.get("id"), "|", e.get("short_name"), "|", e.get("version_id"),
            "|", e.get("data_center"), "|", e.get("title"),
            "| cloud:", e.get("cloud_hosted"),
        )
    names = {entry.get("id"): entry.get("short_name") for entry in entries}
    return clean_url(r.url), names


# STEP 2: search granules in the chosen collection
def search_granules(collection_id, bbox, temporal):
    params = {
        "collection_concept_id": collection_id,
        "bounding_box": bbox,
        "temporal": temporal,
        "page_size": 200,
        "sort_key[]": "start_date",
    }
    entries, search_after, hits, first_url = [], None, None, None
    while True:
        extra = {"CMR-Search-After": search_after} if search_after else None
        r = get(f"{BASE}/granules.json", params, extra)
        first_url = first_url or clean_url(r.url)
        hits = hits or r.headers.get("CMR-Hits")
        page = r.json()["feed"]["entry"]
        entries.extend(page)
        search_after = r.headers.get("CMR-Search-After")
        if not page or not search_after or len(entries) >= 1000:
            break
    return hits, entries, first_url


def search_event_granules(collection_id, events):
    searches = []
    for event in events:
        bbox = event.get("bbox")
        before = (event.get("before") or {}).get("date")
        after = (event.get("after") or {}).get("date")
        if not isinstance(bbox, list) or len(bbox) != 4 or not before or not after:
            raise ValueError("Event is missing a four-value bbox or before/after date")

        south, west, north, east = bbox
        cmr_bbox = ",".join(str(value) for value in (west, south, east, north))
        first_date, last_date = sorted((before, after))
        temporal = f"{first_date}T00:00:00Z,{last_date}T23:59:59Z"
        hits, entries, request_url = search_granules(
            collection_id, cmr_bbox, temporal
        )
        searches.append({
            "event_id": event["id"],
            "bbox": cmr_bbox,
            "temporal": temporal,
            "hits": hits,
            "request_url": request_url,
            "entries": entries,
        })
        print(f"{event['id']}: matching granules {hits}")
    return searches


if __name__ == "__main__":
    collections_url, collection_names = list_collections()
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    if not cfg.get("collection_id"):
        print("Fill in pipeline/config.json (collection_id), then run again.")
        sys.exit(0)

    if cfg.get("bbox") and cfg.get("temporal"):
        hits, entries, granules_url = search_granules(
            cfg["collection_id"], cfg["bbox"], cfg["temporal"]
        )
        searches = []
        bbox = cfg["bbox"]
        temporal = cfg["temporal"]
        event_requests = []
    else:
        with open(EVENTS_PATH, encoding="utf-8") as f:
            events = json.load(f)
        searches = search_event_granules(cfg["collection_id"], events)
        entries = [entry for search in searches for entry in search["entries"]]
        hits = sum(int(search["hits"] or 0) for search in searches)
        bbox = "Per-event bounding boxes"
        temporal = "Per-event before/after date windows"
        granules_url = ""
        event_requests = [
            {"event_id": search["event_id"], "url": search["request_url"]}
            for search in searches
        ]

    print("Matching granules:", hits)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(
            {
                "collection": cfg["collection_id"],
                "collection_name": collection_names.get(cfg["collection_id"], ""),
                "bbox": bbox,
                "temporal": temporal,
                "hits": hits,
                "api_requests": {
                    "collections": collections_url,
                    "granules": granules_url,
                    "event_granules": event_requests,
                    "concept_template": (
                        BASE + "/concepts/<granule-concept-id>.umm_json"
                    ),
                },
                "searches": searches,
                "entries": entries,
            },
            f,
            indent=2,
        )
    print("Saved", OUT_PATH)
