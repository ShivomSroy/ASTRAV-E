"""Search NISAR S-band STAC collections through the Bhoonidhi API."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from bhoonidhi_client import (
    BhoonidhiError,
    BhoonidhiSession,
    collection_ids,
    estimate_item_size,
    online_status,
    write_csv,
    write_geojson,
)


def parse_bbox(value: str) -> list[float]:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must contain four values: minLon,minLat,maxLon,maxLat.")
    try:
        coordinates = [float(part.strip()) for part in parts]
    except ValueError as error:
        raise argparse.ArgumentTypeError("bbox values must be numeric.") from error
    if not all(math.isfinite(value) for value in coordinates):
        raise argparse.ArgumentTypeError("bbox values must be finite numbers.")
    west, south, east, north = coordinates
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise argparse.ArgumentTypeError("bbox longitude values must be between -180 and 180.")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise argparse.ArgumentTypeError("bbox latitude values must be between -90 and 90.")
    if west >= east or south >= north:
        raise argparse.ArgumentTypeError("bbox minimum coordinates must be less than maximum coordinates.")
    return coordinates


def parse_positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a positive integer.") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer.")
    return parsed


def _read_json_argument(value: str, argument_name: str) -> Any:
    if value.startswith("@"):
        path = Path(value[1:])
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ValueError(f"Could not read {argument_name} file: {path}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"{argument_name} file is not valid JSON: {path}") from error
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{argument_name} must be JSON or @path-to-json-file.") from error


def _validate_datetime(value: str) -> str:
    parts = value.split("/")
    if len(parts) > 2:
        raise ValueError("--datetime must be one RFC 3339 instant or a start/end range.")
    for part in parts:
        try:
            parsed = datetime.fromisoformat(part.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("--datetime must use RFC 3339 date-time values with timezone offsets.") from error
        if parsed.tzinfo is None:
            raise ValueError("--datetime values must include a timezone, such as Z.")
    return value


def build_query(args: argparse.Namespace) -> dict[str, Any]:
    query: dict[str, Any] = {
        "collections": [args.collection],
        "limit": args.limit,
    }

    if args.bbox is not None:
        query["bbox"] = args.bbox
    if args.intersects is not None:
        geometry = _read_json_argument(args.intersects, "--intersects")
        if not isinstance(geometry, dict) or not isinstance(geometry.get("type"), str) or "coordinates" not in geometry:
            raise ValueError("--intersects must be a GeoJSON geometry object with type and coordinates.")
        query["intersects"] = geometry

    if args.datetime:
        if args.start_date or args.end_date:
            raise ValueError("Use either --datetime or --start-date/--end-date, not both.")
        query["datetime"] = _validate_datetime(args.datetime)
    elif args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise ValueError("--start-date and --end-date must be provided together.")
        try:
            start = date.fromisoformat(args.start_date)
            end = date.fromisoformat(args.end_date)
        except ValueError as error:
            raise ValueError("Dates must use YYYY-MM-DD format.") from error
        if start.isoformat() != args.start_date or end.isoformat() != args.end_date:
            raise ValueError("Dates must use YYYY-MM-DD format.")
        if start > end:
            raise ValueError("--start-date cannot be later than --end-date.")
        query["datetime"] = (
            f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z"
        )

    filters = []
    if args.filter_json:
        user_filter = _read_json_argument(args.filter_json, "--filter-json")
        if not isinstance(user_filter, dict):
            raise ValueError("--filter-json must contain a CQL2-JSON object.")
        filters.append(user_filter)
    if args.online_only:
        filters.append({"op": "eq", "args": [{"property": "Online"}, "Y"]})
    if len(filters) == 1:
        query["filter"] = filters[0]
    elif filters:
        query["filter"] = {"op": "and", "args": filters}
    if filters:
        query["filter-lang"] = "cql2-json"
    return query


def _format_size(byte_count: int | None) -> str:
    if byte_count is None:
        return "unknown"
    return f"{byte_count / 1_000_000_000:.2f} GB"


def print_summary(features: list[dict[str, Any]], output: Path, format_name: str) -> None:
    statuses = Counter(online_status(feature) for feature in features)
    sizes = [estimate_item_size(feature) for feature in features]
    known_sizes = [item_size[0] for item_size in sizes if item_size[0] is not None]
    estimated_total = sum(known_sizes) if known_sizes else None
    metadata_count = sum(item_size[1] == "metadata" for item_size in sizes)
    typical_count = sum(item_size[1] == "typical estimate" for item_size in sizes)
    unknown_count = sum(item_size[1] == "unknown" for item_size in sizes)

    print(f"Items found: {len(features)}")
    print(
        "Online status: "
        f"Y={statuses.get('Y', 0)}, N={statuses.get('N', 0)}, "
        f"unknown={statuses.get('unknown', 0)}"
    )
    print(
        f"Estimated total size: {_format_size(estimated_total)} "
        f"(metadata: {metadata_count}, typical product estimate: {typical_count}, "
        f"unknown: {unknown_count})"
    )
    print(f"Saved {format_name.upper()} results to {output}")
    if statuses.get("N", 0):
        print(
            "Warning: Online='N' products cannot be downloaded through this API; "
            "use Bhoonidhi Browse & Order."
        )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search NISAR S-band products in the Bhoonidhi STAC catalogue."
    )
    parser.add_argument("--collection", required=True, help="NISAR_SSAR_* collection ID, verified against the live API.")
    area = parser.add_mutually_exclusive_group()
    area.add_argument("--bbox", type=parse_bbox, help="minLon,minLat,maxLon,maxLat in WGS84.")
    area.add_argument(
        "--intersects",
        help="GeoJSON geometry JSON or @path-to-GeoJSON-geometry-file.",
    )
    parser.add_argument("--start-date", help="UTC range start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", help="UTC range end date (YYYY-MM-DD).")
    parser.add_argument("--datetime", help="RFC 3339 instant or start/end range.")
    parser.add_argument(
        "--filter-json",
        help="CQL2-JSON filter object or @path-to-filter.json; inspect item properties first.",
    )
    parser.add_argument(
        "--online-only",
        action="store_true",
        help="Add the documented Online='Y' filter. Without it, report each item's Online value.",
    )
    parser.add_argument("--limit", type=parse_positive_int, default=5, help="Items per API page (1-500; default: 5).")
    parser.add_argument("--max-items", type=parse_positive_int, help="Optional total result cap across pages.")
    parser.add_argument(
        "--inspect-properties",
        action="store_true",
        help="Print the first result's full properties object to help discover filter fields.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("search_results.geojson"),
        help="Output file (default: search_results.geojson).",
    )
    parser.add_argument(
        "--format",
        choices=("geojson", "csv"),
        help="Output format; inferred from .csv extension when omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.limit > 500:
        parser.error("--limit cannot exceed the API maximum of 500.")

    try:
        query = build_query(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    load_dotenv()
    user_id = os.environ.get("BHOONIDHI_USER")
    password = os.environ.get("BHOONIDHI_PASSWORD")
    if not user_id or not password:
        parser.error(
            "Set BHOONIDHI_USER and BHOONIDHI_PASSWORD in the environment or a local .env file."
        )

    output_format = args.format or ("csv" if args.output.suffix.lower() == ".csv" else "geojson")
    client = BhoonidhiSession(user_id, password)
    try:
        available_collections = collection_ids(client.list_collections())
        if args.collection not in available_collections:
            raise BhoonidhiError(
                f"Collection {args.collection!r} was not returned by the live API. "
                "Available IDs: " + ", ".join(available_collections)
            )

        result = client.search(query, max_items=args.max_items)
        features = result["features"]
        if args.inspect_properties and features:
            properties = features[0].get("properties", {})
            print("First item properties:", file=sys.stderr)
            print(json.dumps(properties, indent=2, ensure_ascii=False), file=sys.stderr)

        if output_format == "csv":
            write_csv(features, args.output)
        else:
            write_geojson(features, args.output)
        print_summary(features, args.output, output_format)
        return 0
    except (BhoonidhiError, OSError, ValueError) as error:
        print(f"Bhoonidhi search failed: {error}", file=sys.stderr)
        return 1
    finally:
        try:
            client.close()
        except BhoonidhiError as error:
            print(f"Warning: Bhoonidhi logout failed: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
