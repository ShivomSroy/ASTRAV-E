"""Small, rate-limit-aware client for the Bhoonidhi STAC API."""

from __future__ import annotations

import copy
import csv
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit

import requests


API_BASE_URL = "https://bhoonidhi-api.nrsc.gov.in"
TYPICAL_PRODUCT_SIZE_GB = {
    "RSLC": 33.0,
    "GSLC": 54.0,
    "GCOV": 11.0,
    "GUNW": 3.5,
    "GOFF": 1.3,
}
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_DOWNLOAD_RETRYABLE_STATUSES = _RETRYABLE_STATUSES | {412}
_SIZE_FIELDS = ("file:size", "size_bytes", "file_size", "FileSize", "size")
_SIZE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(bytes?|b|kb|mb|gb|tb)?\s*$", re.I)


class BhoonidhiError(RuntimeError):
    """An API, authentication, or download operation failed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class _IncompleteDownload(Exception):
    pass


def collection_ids(payload: Any) -> list[str]:
    """Extract collection identifiers from common STAC collection responses."""
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload.get("collections", payload.get("features"))
        if entries is None and payload.get("id"):
            entries = [payload]
    else:
        entries = None

    if not isinstance(entries, list):
        raise BhoonidhiError("Bhoonidhi returned an unrecognized collections response.")

    identifiers = []
    for entry in entries:
        identifier = entry if isinstance(entry, str) else entry.get("id") if isinstance(entry, dict) else None
        if isinstance(identifier, str) and identifier:
            identifiers.append(identifier)
    if not identifiers:
        raise BhoonidhiError("Bhoonidhi returned no collection identifiers.")
    return identifiers


def online_status(feature: Mapping[str, Any]) -> str:
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        return "unknown"
    value = properties.get("Online")
    if value is None:
        return "unknown"
    return str(value).strip().upper()


def _parse_size(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    if not isinstance(value, str):
        return None

    match = _SIZE_PATTERN.match(value)
    if not match:
        return None
    amount = float(match.group(1))
    unit = (match.group(2) or "bytes").lower()
    multipliers = {
        "byte": 1,
        "bytes": 1,
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
    }
    return int(amount * multipliers[unit]) if amount > 0 else None


def estimate_item_size(feature: Mapping[str, Any]) -> tuple[int | None, str]:
    """Return size in bytes and whether it came from metadata or a typical estimate."""
    properties = feature.get("properties")
    if isinstance(properties, Mapping):
        for key in _SIZE_FIELDS:
            size = _parse_size(properties.get(key))
            if size:
                return size, "metadata"

    assets = feature.get("assets")
    if isinstance(assets, Mapping):
        for asset in assets.values():
            if not isinstance(asset, Mapping):
                continue
            for key in _SIZE_FIELDS:
                size = _parse_size(asset.get(key))
                if size:
                    return size, "metadata"

    collection = str(feature.get("collection", "")).upper()
    product = collection.rsplit("_", 1)[-1]
    typical_gb = TYPICAL_PRODUCT_SIZE_GB.get(product)
    if typical_gb is not None:
        return int(typical_gb * 1_000_000_000), "typical estimate"
    return None, "unknown"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def write_geojson(features: list[dict[str, Any]], output: Path) -> None:
    """Write a STAC FeatureCollection to a GeoJSON file atomically."""
    document = {
        "type": "FeatureCollection",
        "features": features,
    }
    _write_text_atomically(output, json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def write_csv(features: list[dict[str, Any]], output: Path) -> None:
    """Write feature identifiers, geometry, and flattened STAC properties to CSV."""
    property_names = sorted({
        key
        for feature in features
        for key in (feature.get("properties") or {})
        if isinstance(feature.get("properties"), Mapping)
    })
    fieldnames = ["id", "collection", "geometry", *property_names]
    temporary = output.with_name(output.name + ".part")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for feature in features:
                row = {
                    "id": feature.get("id", ""),
                    "collection": feature.get("collection", ""),
                    "geometry": _jsonable(feature.get("geometry")),
                }
                properties = feature.get("properties")
                if isinstance(properties, Mapping):
                    row.update({key: _jsonable(value) for key, value in properties.items()})
                writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except OSError:
        if temporary.exists():
            temporary.unlink()
        raise


def _write_text_atomically(output: Path, text: str) -> None:
    temporary = output.with_name(output.name + ".part")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except OSError:
        if temporary.exists():
            temporary.unlink()
        raise


class BhoonidhiSession:
    """Authenticated Bhoonidhi client with token caching and API rate limits."""

    def __init__(
        self,
        user_id: str,
        password: str,
        *,
        base_url: str = API_BASE_URL,
        timeout: tuple[float, float] = (30, 300),
        max_attempts: int = 5,
        retry_base_seconds: float = 1.0,
        search_interval_seconds: float = 0.4,
        download_interval_seconds: float = 30.0,
        max_concurrent_downloads: int = 2,
        http_session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not user_id or not password:
            raise ValueError("A Bhoonidhi user ID and password are required.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if not 1 <= max_concurrent_downloads <= 5:
            raise ValueError("max_concurrent_downloads must be between 1 and 5.")
        if retry_base_seconds <= 0:
            raise ValueError("retry_base_seconds must be positive.")
        if search_interval_seconds < 0.4:
            raise ValueError("Search requests must be at least 0.4 seconds apart.")
        if download_interval_seconds < 30:
            raise ValueError("Download requests must be at least 30 seconds apart.")

        self.user_id = user_id
        self._password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.search_interval_seconds = search_interval_seconds
        self.download_interval_seconds = download_interval_seconds
        self.http = http_session or requests.Session()
        self.http.headers.update({"Accept": "application/json"})
        self._sleep = sleep
        self._monotonic = monotonic

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._access_expires_at = 0.0
        self._auth_lock = threading.RLock()
        self._search_lock = threading.Lock()
        self._last_search_at: float | None = None
        self._download_rate_lock = threading.Lock()
        self._last_download_at: float | None = None
        self._download_slots = threading.BoundedSemaphore(max_concurrent_downloads)

    def __enter__(self) -> BhoonidhiSession:
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        del _exc_type, _exc_value, _traceback
        self.close()

    def close(self) -> None:
        try:
            self.logout()
        finally:
            self.http.close()

    def _token_response(self, payload: dict[str, str]) -> dict[str, Any]:
        try:
            response = self.http.post(
                self.base_url + "/auth/token",
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise BhoonidhiError("Could not reach the Bhoonidhi authentication service.") from error
        try:
            if not response.ok:
                raise self._response_error(response)
            data = self._decode_json(response)
        finally:
            response.close()

        if not isinstance(data, dict):
            raise BhoonidhiError("Bhoonidhi returned an invalid token response.")
        return data

    def _store_tokens(self, data: Mapping[str, Any]) -> None:
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise BhoonidhiError("Bhoonidhi token response did not contain an access token.")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise BhoonidhiError("Bhoonidhi token response did not contain a refresh token.")
        try:
            lifetime = int(data.get("expires_in", 1200))
        except (TypeError, ValueError) as error:
            raise BhoonidhiError("Bhoonidhi returned an invalid token lifetime.") from error
        if lifetime <= 0:
            raise BhoonidhiError("Bhoonidhi returned an expired access token.")

        refresh_margin = min(60, max(1, lifetime // 10))
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._access_expires_at = self._monotonic() + max(0, lifetime - refresh_margin)

    def _login(self) -> None:
        data = self._token_response({
            "userId": self.user_id,
            "password": self._password,
            "grant_type": "password",
        })
        self._store_tokens(data)

    def _refresh_or_login(self) -> None:
        with self._auth_lock:
            if not self._refresh_token:
                self._login()
                return
            try:
                data = self._token_response({
                    "userId": self.user_id,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                })
            except BhoonidhiError as error:
                if error.status_code != 401:
                    raise
                self._login()
                return
            self._store_tokens(data)

    def _get_access_token(self) -> str:
        with self._auth_lock:
            if not self._access_token:
                self._login()
            elif self._monotonic() >= self._access_expires_at:
                self._refresh_or_login()
            if not self._access_token:
                raise BhoonidhiError("Bhoonidhi authentication did not produce an access token.")
            return self._access_token

    def logout(self) -> None:
        with self._auth_lock:
            refresh_token = self._refresh_token
            if not refresh_token:
                return
            try:
                response = self.http.post(
                    self.base_url + "/auth/logout",
                    headers={"Authorization": "Bearer " + refresh_token},
                    timeout=self.timeout,
                )
                try:
                    if not response.ok:
                        raise self._response_error(response)
                finally:
                    response.close()
            except requests.RequestException as error:
                raise BhoonidhiError("Could not reach the Bhoonidhi logout endpoint.") from error
            finally:
                self._access_token = None
                self._refresh_token = None
                self._access_expires_at = 0.0

    def _response_error(self, response: requests.Response) -> BhoonidhiError:
        description = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            for key in ("Description", "description", "message", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    description = value.strip()
                    break
        for secret in (self._password, self._access_token, self._refresh_token):
            if secret:
                description = description.replace(secret, "[redacted]")
        message = "Bhoonidhi API returned HTTP " + str(response.status_code)
        if description:
            message += ": " + description
        return BhoonidhiError(message, response.status_code)

    def _decode_json(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError as error:
            raise BhoonidhiError("Bhoonidhi returned a response that was not valid JSON.") from error

    def _wait_for_search_slot(self) -> None:
        with self._search_lock:
            now = self._monotonic()
            if self._last_search_at is not None:
                delay = self.search_interval_seconds - (now - self._last_search_at)
                if delay > 0:
                    self._sleep(delay)
            self._last_search_at = self._monotonic()

    def _wait_for_download_slot(self) -> None:
        with self._download_rate_lock:
            now = self._monotonic()
            if self._last_download_at is not None:
                delay = self.download_interval_seconds - (now - self._last_download_at)
                if delay > 0:
                    self._sleep(delay)
            self._last_download_at = self._monotonic()

    def _retry_delay(self, retry_index: int, response: requests.Response | None) -> float:
        delay = min(self.retry_base_seconds * (2**retry_index), 60.0)
        if response is None:
            return delay
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return delay
        try:
            return max(delay, float(retry_after))
        except ValueError:
            try:
                retry_time = parsedate_to_datetime(retry_after)
                if retry_time.tzinfo is None:
                    retry_time = retry_time.replace(tzinfo=timezone.utc)
                return max(delay, (retry_time - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return delay

    def _authorized_request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        stream: bool = False,
        search_request: bool = False,
        download_request: bool = False,
    ) -> requests.Response:
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise ValueError("Only GET and POST are supported by this client.")

        retries = 0
        auth_retried = False
        while True:
            if search_request:
                self._wait_for_search_slot()
            if download_request:
                self._wait_for_download_slot()

            try:
                response = self.http.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers={"Authorization": "Bearer " + self._get_access_token()},
                    timeout=self.timeout,
                    stream=stream,
                )
            except requests.RequestException as error:
                if retries >= self.max_attempts - 1:
                    raise BhoonidhiError("A Bhoonidhi API request failed after retries.") from error
                self._sleep(self._retry_delay(retries, None))
                retries += 1
                continue

            if response.status_code == 401 and not auth_retried:
                response.close()
                self._refresh_or_login()
                auth_retried = True
                continue

            retryable = (
                _DOWNLOAD_RETRYABLE_STATUSES if download_request
                else _RETRYABLE_STATUSES
            )
            if response.status_code in retryable:
                if retries >= self.max_attempts - 1:
                    error = self._response_error(response)
                    response.close()
                    raise error
                delay = self._retry_delay(retries, response)
                response.close()
                self._sleep(delay)
                retries += 1
                continue
            return response

    def list_collections(self) -> Any:
        response = self._authorized_request("GET", self.base_url + "/data/collections")
        try:
            if not response.ok:
                raise self._response_error(response)
            return self._decode_json(response)
        finally:
            response.close()

    def _trusted_next_url(self, href: str) -> str:
        target = urljoin(self.base_url + "/", href)
        base = urlsplit(self.base_url)
        candidate = urlsplit(target)
        if candidate.scheme != base.scheme or candidate.netloc.lower() != base.netloc.lower():
            raise BhoonidhiError("Bhoonidhi returned a pagination link outside its API origin; refusing to forward credentials.")
        return target

    def search(
        self,
        query: Mapping[str, Any],
        *,
        max_items: int | None = None,
    ) -> dict[str, Any]:
        """POST a STAC search and follow same-origin next links."""
        if not isinstance(query, Mapping):
            raise TypeError("query must be a mapping.")
        request_body = copy.deepcopy(dict(query))
        if "token" in request_body:
            raise ValueError("Do not put authentication tokens in the search body.")
        if "filter" in request_body and "filter-lang" not in request_body:
            request_body["filter-lang"] = "cql2-json"
        limit = request_body.get("limit", 10)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("Search limit must be an integer from 1 to 500.")
        if max_items is not None and max_items < 1:
            raise ValueError("max_items must be positive.")

        search_url = self.base_url + "/data/search"
        response = self._authorized_request(
            "POST",
            search_url,
            json_body=request_body,
            search_request=True,
        )
        try:
            if not response.ok:
                raise self._response_error(response)
            result = self._decode_json(response)
        finally:
            response.close()

        if not isinstance(result, dict) or not isinstance(result.get("features"), list):
            raise BhoonidhiError("Bhoonidhi returned an invalid STAC FeatureCollection.")

        features: list[dict[str, Any]] = []
        links = result.get("links", [])
        if not isinstance(links, list):
            raise BhoonidhiError("Bhoonidhi returned invalid STAC pagination links.")
        result_links = [link for link in links if isinstance(link, dict) and link.get("rel") != "next"]
        initial_signature = ("POST", search_url, json.dumps(request_body, sort_keys=True, default=str))
        seen = {initial_signature}
        page = result
        page_count = 0

        while True:
            page_features = page.get("features", [])
            if not isinstance(page_features, list):
                raise BhoonidhiError("Bhoonidhi returned an invalid STAC features list.")
            if any(not isinstance(feature, dict) for feature in page_features):
                raise BhoonidhiError("Bhoonidhi returned a non-feature entry in its STAC response.")
            if max_items is not None:
                remaining = max_items - len(features)
                features.extend(page_features[:remaining])
            else:
                features.extend(page_features)
            page_count += 1
            if page_count > 1000:
                raise BhoonidhiError("Bhoonidhi pagination exceeded the safety limit of 1,000 pages.")
            if max_items is not None and len(features) >= max_items:
                break

            next_link = next(
                (link for link in page.get("links", []) if isinstance(link, dict) and link.get("rel") == "next"),
                None,
            )
            if next_link is None:
                break
            href = next_link.get("href")
            if not isinstance(href, str) or not href:
                raise BhoonidhiError("Bhoonidhi returned a pagination link without an href.")
            next_url = self._trusted_next_url(href)
            next_method = str(next_link.get("method", "GET")).upper()
            if next_method not in {"GET", "POST"}:
                raise BhoonidhiError("Bhoonidhi returned an unsupported pagination method.")
            next_body = next_link.get("body") if next_method == "POST" else None
            if next_method == "POST" and not isinstance(next_body, Mapping):
                raise BhoonidhiError("Bhoonidhi returned a POST pagination link without a JSON body.")
            signature = (
                next_method,
                next_url,
                json.dumps(next_body, sort_keys=True, default=str),
            )
            if signature in seen:
                raise BhoonidhiError("Bhoonidhi returned a repeated pagination link.")
            seen.add(signature)

            response = self._authorized_request(
                next_method,
                next_url,
                json_body=next_body,
                search_request=True,
            )
            try:
                if not response.ok:
                    raise self._response_error(response)
                page = self._decode_json(response)
            finally:
                response.close()
            if not isinstance(page, dict):
                raise BhoonidhiError("Bhoonidhi returned an invalid paginated STAC response.")
            links = page.get("links", [])
            if not isinstance(links, list):
                raise BhoonidhiError("Bhoonidhi returned invalid STAC pagination links.")

        context = result.get("context")
        if not isinstance(context, dict):
            context = {}
            result["context"] = context
        context["returned"] = len(features)
        result["features"] = features
        result["links"] = result_links
        return result

    def download_item(
        self,
        feature: Mapping[str, Any],
        destination: str | Path,
        *,
        collection_id: str | None = None,
        chunk_size: int = 8 * 1024 * 1024,
    ) -> Path:
        """Download one Online=Y product to a .part file, then atomically rename it."""
        if online_status(feature) != "Y":
            raise BhoonidhiError("Downloads are allowed only for products with Online='Y'.")
        item_id = feature.get("id")
        collection = collection_id or feature.get("collection")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("The STAC feature must include an item id.")
        if not isinstance(collection, str) or not collection:
            raise ValueError("The STAC feature must include a collection id.")
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive.")

        target = Path(destination)
        temporary = target.with_name(target.name + ".part")
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)

        with self._download_slots:
            for attempt in range(self.max_attempts):
                response = self._authorized_request(
                    "GET",
                    self.base_url + "/download",
                    params={"id": item_id, "collection": collection},
                    stream=True,
                    download_request=True,
                )
                try:
                    if not response.ok:
                        raise self._response_error(response)
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "json" in content_type:
                        raise BhoonidhiError("Bhoonidhi returned JSON instead of a product file.", response.status_code)
                    expected_size_text = response.headers.get("Content-Length")
                    expected_size = int(expected_size_text) if expected_size_text and expected_size_text.isdigit() else None
                    content_encoding = response.headers.get("Content-Encoding", "").lower()
                    if content_encoding not in ("", "identity"):
                        expected_size = None
                    received = 0
                    try:
                        with temporary.open("wb") as handle:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if chunk:
                                    handle.write(chunk)
                                    received += len(chunk)
                            handle.flush()
                            os.fsync(handle.fileno())
                    except OSError:
                        if temporary.exists():
                            temporary.unlink()
                        raise
                    if received == 0:
                        raise _IncompleteDownload("Bhoonidhi returned an empty product file.")
                    if expected_size is not None and received != expected_size:
                        raise _IncompleteDownload(
                            "Bhoonidhi download ended before the advertised content length."
                        )
                except (requests.RequestException, _IncompleteDownload) as error:
                    if temporary.exists():
                        temporary.unlink()
                    if attempt >= self.max_attempts - 1:
                        raise BhoonidhiError("Product download failed after retries.") from error
                    self._sleep(self._retry_delay(attempt, None))
                    continue
                finally:
                    response.close()

                os.replace(temporary, target)
                return target

        raise BhoonidhiError("Product download failed without a response.")
