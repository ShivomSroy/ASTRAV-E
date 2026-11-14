import csv
import json
import tempfile
import unittest
from pathlib import Path

from bhoonidhi_client import (
    BhoonidhiError,
    BhoonidhiSession,
    estimate_item_size,
    online_status,
    write_csv,
    write_geojson,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, body=b"", headers=None):
        self.status_code = status_code
        self.payload = payload
        self.body = body
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300
        self.closed = False

    def json(self):
        if self.payload is None:
            raise ValueError("No JSON body")
        return self.payload

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.body

    def close(self):
        self.closed = True


class FakeHttpSession:
    def __init__(self, responses=None, token_responses=None):
        self.headers = {}
        self.responses = list(responses or [])
        self.token_responses = list(token_responses or [
            FakeResponse(payload={
                "access_token": "access-one",
                "refresh_token": "refresh-one",
                "expires_in": 1200,
            })
        ])
        self.calls = []
        self.token_calls = []
        self.closed = False

    def post(self, url, json=None, headers=None, timeout=None):
        del timeout
        self.token_calls.append((url, json, headers))
        if url.endswith("/auth/logout"):
            return FakeResponse()
        return self.token_responses.pop(0)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def feature(item_id, online="Y", collection="NISAR_SSAR_GCOV"):
    return {
        "type": "Feature",
        "id": item_id,
        "collection": collection,
        "geometry": {"type": "Point", "coordinates": [77, 28]},
        "properties": {"Online": online, "datetime": "2026-07-08T00:00:00Z"},
    }


class BhoonidhiClientTests(unittest.TestCase):
    def make_client(self, responses, token_responses=None, **options):
        http = FakeHttpSession(responses, token_responses)
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds

        client = BhoonidhiSession(
            "user",
            "password",
            http_session=http,
            sleep=sleep,
            monotonic=lambda: clock[0],
            **options,
        )
        return client, http, clock

    def test_search_follows_next_link_and_reuses_cached_token(self):
        first = {
            "type": "FeatureCollection",
            "context": {"returned": 1},
            "features": [feature("one")],
            "links": [{"rel": "next", "href": "/data/search?cursor=two"}],
        }
        second = {
            "type": "FeatureCollection",
            "features": [feature("two")],
            "links": [],
        }
        client, http, clock = self.make_client([FakeResponse(payload=first), FakeResponse(payload=second)])

        result = client.search({"collections": ["NISAR_SSAR_GCOV"], "limit": 1})

        self.assertEqual([item["id"] for item in result["features"]], ["one", "two"])
        self.assertEqual(result["context"]["returned"], 2)
        self.assertEqual([call[0] for call in http.calls], ["POST", "GET"])
        self.assertEqual(len(http.token_calls), 1)
        self.assertEqual(http.calls[0][2]["headers"]["Authorization"], "Bearer access-one")
        self.assertAlmostEqual(clock[0], 0.4)

    def test_search_refreshes_token_once_after_401(self):
        token_responses = [
            FakeResponse(payload={
                "access_token": "access-one",
                "refresh_token": "refresh-one",
                "expires_in": 1200,
            }),
            FakeResponse(payload={
                "access_token": "access-two",
                "refresh_token": "refresh-two",
                "expires_in": 1200,
            }),
        ]
        result_page = {"type": "FeatureCollection", "features": [], "links": []}
        client, http, _ = self.make_client(
            [FakeResponse(status_code=401), FakeResponse(payload=result_page)],
            token_responses=token_responses,
            max_attempts=1,
        )

        client.search({"collections": ["NISAR_SSAR_GCOV"], "limit": 5})

        self.assertEqual([call[1]["grant_type"] for call in http.token_calls], ["password", "refresh_token"])
        self.assertEqual(http.calls[1][2]["headers"]["Authorization"], "Bearer access-two")

    def test_search_honors_retry_after_on_rate_limit(self):
        page = {"type": "FeatureCollection", "features": [], "links": []}
        client, http, clock = self.make_client(
            [
                FakeResponse(status_code=429, headers={"Retry-After": "2"}),
                FakeResponse(payload=page),
            ],
            max_attempts=2,
        )

        client.search({"collections": ["NISAR_SSAR_GCOV"], "limit": 5})

        self.assertEqual(len(http.calls), 2)
        self.assertGreaterEqual(clock[0], 2.0)

    def test_api_error_does_not_echo_credentials_or_tokens(self):
        response = FakeResponse(
            status_code=400,
            payload={"Description": "password access-one refresh-one"},
        )
        client, _, _ = self.make_client([response])

        with self.assertRaises(BhoonidhiError) as raised:
            client.search({"collections": ["NISAR_SSAR_GCOV"], "limit": 5})

        message = str(raised.exception)
        self.assertNotIn("password", message)
        self.assertNotIn("access-one", message)
        self.assertNotIn("refresh-one", message)

    def test_client_does_not_allow_rate_limits_to_be_lowered(self):
        with self.assertRaisesRegex(ValueError, "0.4 seconds"):
            BhoonidhiSession("user", "password", search_interval_seconds=0.1)
        with self.assertRaisesRegex(ValueError, "30 seconds"):
            BhoonidhiSession("user", "password", download_interval_seconds=1)

    def test_search_refuses_external_pagination_host(self):
        page = {
            "type": "FeatureCollection",
            "features": [],
            "links": [{"rel": "next", "href": "https://other.example/collect"}],
        }
        client, _, _ = self.make_client([FakeResponse(payload=page)])

        with self.assertRaisesRegex(BhoonidhiError, "outside its API origin"):
            client.search({"collections": ["NISAR_SSAR_GCOV"], "limit": 5})

    def test_download_rejects_non_online_items_without_request(self):
        client, http, _ = self.make_client([])

        with self.assertRaisesRegex(BhoonidhiError, "Online='Y'"):
            client.download_item(feature("delayed", online="N"), "unused.h5")

        self.assertEqual(http.calls, [])
        self.assertEqual(http.token_calls, [])

    def test_download_writes_then_renames_complete_file(self):
        response = FakeResponse(
            body=b"hdf5-data",
            headers={"Content-Length": "9", "Content-Type": "application/octet-stream"},
        )
        client, http, _ = self.make_client([response])

        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "product.h5"
            saved = client.download_item(feature("granule"), target)

            self.assertEqual(saved.read_bytes(), b"hdf5-data")
            self.assertFalse(target.with_name(target.name + ".part").exists())

        self.assertEqual(http.calls[0][2]["params"], {
            "id": "granule",
            "collection": "NISAR_SSAR_GCOV",
        })

    def test_incomplete_download_is_not_promoted_to_final_file(self):
        response = FakeResponse(
            body=b"short",
            headers={"Content-Length": "20", "Content-Type": "application/octet-stream"},
        )
        client, _, _ = self.make_client(
            [response],
            max_attempts=1,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "product.h5"
            with self.assertRaisesRegex(BhoonidhiError, "failed after retries"):
                client.download_item(feature("granule"), target)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_size_estimates_prefer_item_metadata_and_report_unknown(self):
        item = feature("granule")
        item["properties"]["size"] = "2.5 GB"
        self.assertEqual(estimate_item_size(item), (2_500_000_000, "metadata"))
        self.assertEqual(online_status(feature("granule", online="n")), "N")
        self.assertEqual(estimate_item_size({"collection": "OTHER"}), (None, "unknown"))

    def test_exporters_write_geojson_and_flatten_csv_properties(self):
        item = feature("granule")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            geojson = root / "items.geojson"
            csv_path = root / "items.csv"

            write_geojson([item], geojson)
            write_csv([item], csv_path)

            self.assertEqual(json.loads(geojson.read_text(encoding="utf-8"))["features"][0]["id"], "granule")
            with csv_path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["Online"], "Y")
            self.assertEqual(row["id"], "granule")


if __name__ == "__main__":
    unittest.main()
