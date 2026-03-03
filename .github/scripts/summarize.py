#!/usr/bin/env python3
"""Summarize Alaska award search results."""

import glob
import json


def main():
    print("=== Search Results ===")

    for filepath in sorted(glob.glob("alaska_*_parsed.json")):
        print(f"\n--- {filepath} ---")

        with open(filepath) as f:
            data = json.load(f)

        origin = data.get("origin", "?")
        destination = data.get("destination", "?")
        month = data.get("month", "?")
        year = data.get("year", "?")

        print(f"Route: {origin} -> {destination}")
        print(f"Month: {month} {year}")

        deals = [f for f in data.get("fares", []) if f.get("is_deal")]
        print(f"Deals found: {len(deals)}")

        for d in deals:
            print(f"  🔥 {d['date']}: {d['miles']}k + ${d['cash']}")

    if not glob.glob("alaska_*_parsed.json"):
        print("No parsed results found.")


if __name__ == "__main__":
    main()
