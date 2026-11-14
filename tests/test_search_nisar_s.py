import argparse
import unittest

from scripts.search_nisar_s import build_query, make_parser, parse_bbox


class SearchCliTests(unittest.TestCase):
    def test_build_query_converts_dates_and_combines_filters(self):
        args = make_parser().parse_args([
            "--collection", "NISAR_SSAR_GCOV",
            "--bbox", "77,28,78,29",
            "--start-date", "2026-07-08",
            "--end-date", "2026-07-15",
            "--online-only",
            "--filter-json", '{"op":"eq","args":[{"property":"Node"},"ASCENDING"]}',
        ])

        query = build_query(args)

        self.assertEqual(query["bbox"], [77.0, 28.0, 78.0, 29.0])
        self.assertEqual(
            query["datetime"],
            "2026-07-08T00:00:00Z/2026-07-15T23:59:59Z",
        )
        self.assertEqual(query["filter-lang"], "cql2-json")
        self.assertEqual(query["filter"]["op"], "and")
        self.assertEqual(query["filter"]["args"][1]["args"][1], "Y")

    def test_bbox_rejects_reversed_or_invalid_ranges(self):
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "minimum coordinates"):
            parse_bbox("78,28,77,29")
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "four values"):
            parse_bbox("77,28,78")


if __name__ == "__main__":
    unittest.main()
