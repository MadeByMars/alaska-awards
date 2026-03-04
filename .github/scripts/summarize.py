#!/usr/bin/env python3
"""Summarize Alaska award search results."""

import glob
import json
import os


def main():
    print("=== Search Results ===")

    output_file = os.environ.get("GITHUB_OUTPUT")
    total_deals = 0

    for filepath in sorted(glob.glob("alaska_*_parsed.json")):
        with open(filepath) as f:
            data = json.load(f)

        origin = data.get("origin", "?")
        destination = data.get("destination", "?")
        month = data.get("month", "?")
        year = data.get("year", "?")
        date_range = data.get("date_range", {})
        threshold = data.get("highlight_threshold", "?")



        print(f"\n{'#' * 60}")
        print(f"  Route: {origin} -> {destination}")
        print(f"  Period: {date_range.get('start', '?')} to {date_range.get('end', '?')}")
        print(f"  Deal threshold: < {threshold}k miles")
        print(f"{'#' * 60}")

        deals = [f for f in data.get("fares", []) if f.get("is_deal")]
        print(f"  Deals found: {len(deals)}")
        total_deals += len(deals)

        for d in deals:
            print(f"  🔥 {d['date']}: {d['miles']}k + ${d['cash']}")

    if not glob.glob("alaska_*_parsed.json"):
        print("No parsed results found.")

    print(f"\n{'=' * 60}")
    print(f"  TOTAL DEALS: {total_deals}")
    print(f"{'=' * 60}")

    # Write outputs for GitHub Actions
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"deals_count={total_deals}\n")
            f.write(f"has_deals={'true' if total_deals > 0 else 'false'}\n")


if __name__ == "__main__":
    main()
