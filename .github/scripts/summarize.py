#!/usr/bin/env python3
"""Summarize Alaska award search results."""

import glob
import json
import os
from io import StringIO

RESULTS_DIR = "results"


def main():
    output_file = os.environ.get("GITHUB_OUTPUT")
    total_deals = 0

    # Capture output for both stdout and GITHUB_OUTPUT
    output = StringIO()

    def log(msg=""):
        print(msg)
        output.write(msg + "\n")

    log("=== Search Results ===")

    for filepath in sorted(glob.glob(f"{RESULTS_DIR}/alaska_*_parsed.json")):
        with open(filepath) as f:
            data = json.load(f)

        origin = data.get("origin", "?")
        destination = data.get("destination", "?")
        date_range = data.get("date_range", {})
        threshold = data.get("highlight_threshold", "?")

        log(f"\n{'#' * 60}")
        log(f"  Route: {origin} -> {destination}")
        log(f"  Period: {date_range.get('start', '?')} to {date_range.get('end', '?')}")
        log(f"  Deal threshold: < {threshold}k miles")
        log(f"{'#' * 60}")

        deals = [f for f in data.get("fares", []) if f.get("is_deal")]
        log(f"  Deals found: {len(deals)}")
        total_deals += len(deals)

        for d in deals:
            log(f"  🔥 {d['date']}: {d['miles']}k + ${d['cash']}")

    if not glob.glob(f"{RESULTS_DIR}/alaska_*_parsed.json"):
        log("No parsed results found.")

    log(f"\n{'=' * 60}")
    log(f"  TOTAL DEALS: {total_deals}")
    log(f"{'=' * 60}")

    # Write outputs for GitHub Actions
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"deals_count={total_deals}\n")
            f.write(f"has_deals={'true' if total_deals > 0 else 'false'}\n")
            f.write("CONTENT<<EOF\n")
            f.write(output.getvalue())
            f.write("EOF\n")


if __name__ == "__main__":
    main()
