# pip install requests
import json
import os
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests

CMR = "https://cmr.earthdata.nasa.gov/search"
EONET = "https://eonet.gsfc.nasa.gov/api/v3/events"
POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"
GIBS_CAPS = ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi"
             "?SERVICE=WMTS&request=GetCapabilities")
GIBS_LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"
HEADERS = {"Client-Id": "astrave-spaceapps"}
OUT_DIR = os.path.join("public", "data", "india")
EVENTS_PATH = os.path.join(OUT_DIR, "events.json")
CONFIG_PATH = os.path.join("pipeline", "config.json")


def clean_url(url):
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if "token" not in k.lower()]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def get(url, params=None, extra=None, retries=3):
    headers = dict(HEADERS)
    if extra:
        headers.update(extra)
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=60)
        except requests.RequestException as err:
            print("Request failed:", err)
            time.sleep(3)
            continue
        if r.status_code == 429:
            time.sleep(int(r.headers.get("retry-after", "5")))
            continue
        if r.status_code >= 400:
            print("HTTP", r.status_code, "for", clean_url(r.url))
            return None
        return r
    return None


def check_gibs():
    r = get(GIBS_CAPS)
    print("GIBS layer", GIBS_LAYER, "listed in GetCapabilities:",
          bool(r) and GIBS_LAYER in r.text)


def list_nisar_collections():
    r = get(CMR + "/collections.json", {"keyword": "NISAR", "page_size": 100})
    if not r:
        return
    for e in r.json()["feed"]["entry"]:
        print(e.get("id"), "|", e.get("short_name"), "|", e.get("version_id"),
              "|", e.get("data_center"), "|", e.get("title"))


def cmr_granules(collection_id, bbox, temporal):
    params = {"collection_concept_id": collection_id, "bounding_box": bbox,
              "temporal": temporal, "page_size": 200, "sort_key[]": "start_date"}
    entries, search_after, hits, first_url = [], None, None, None
    while True:
        extra = {"CMR-Search-After": search_after} if search_after else None
        r = get(CMR + "/granules.json", params, extra)
        if not r:
            break
        first_url = first_url or clean_url(r.url)
        hits = hits or r.headers.get("CMR-Hits")
        page = r.json()["feed"]["entry"]
        entries.extend(page)
        search_after = r.headers.get("CMR-Search-After")
        if not page or not search_after or len(entries) >= 500:
            break
    return {"collection": collection_id, "temporal": temporal, "hits": hits,
            "request_url": first_url, "entries": entries}


def eonet_events(bbox, temporal):
    west, south, east, north = [float(x) for x in bbox.split(",")]
    start, end = [t[:10] for t in temporal.split(",")]
    params = {"bbox": f"{west},{north},{east},{south}", "start": start,
              "end": end, "status": "all", "limit": 50}
    r = get(EONET, params)
    if not r:
        return None
    return {"request_url": clean_url(r.url), "events": r.json().get("events", [])}


def power_rain(rain):
    if not rain:
        return None
    params = {"parameters": "PRECTOTCORR", "community": "RE",
              "longitude": rain["lon"], "latitude": rain["lat"],
              "start": rain["start"], "end": rain["end"], "format": "JSON"}
    r = get(POWER, params)
    if not r:
        return None
    body = r.json()
    return {"request_url": clean_url(r.url), "parameter": "PRECTOTCORR",
            "data": body.get("properties", {}).get("parameter", {}).get("PRECTOTCORR", {})}


if __name__ == "__main__":
    check_gibs()
    with open(EVENTS_PATH) as f:
        events = json.load(f)["events"]
    try:
        with open(CONFIG_PATH) as f:
            collection_id = json.load(f).get("collection_id", "")
    except FileNotFoundError:
        collection_id = ""
    if not collection_id:
        print("No collection_id in pipeline/config.json. Listing NISAR collections:")
        list_nisar_collections()
    for ev in events:
        out = {
            "event_id": ev["id"],
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bbox": ev["bbox"],
            "cmr": (cmr_granules(collection_id, ev["bbox"], ev["temporal"])
                    if collection_id else None),
            "eonet": eonet_events(ev["bbox"], ev["temporal"]),
            "power": power_rain(ev.get("rain")),
        }
        with open(os.path.join(OUT_DIR, ev["id"] + ".json"), "w") as f:
            json.dump(out, f, indent=2)
        print("Saved", ev["id"])
