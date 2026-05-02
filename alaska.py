#!/usr/bin/env python3
"""
Alaska Airlines Award Flight Calendar Scraper

This script fetches award flight availability from Alaska Airlines calendar view.
Uses Playwright for browser automation to handle JavaScript rendering.

Requirements:
    pip install playwright
    playwright install chromium
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

# Output directory for all results
RESULTS_DIR = "results"

# Known Alaska award calendar fare types for future searches.
FARE_TYPES = {
    "lowest": "Lowest+price+available",
    "partner_premium": "Partner+Premium",
    "partner_business": "Partner+Business",
}

from playwright.async_api import async_playwright


@dataclass
class AwardFare:
    date: str
    day: int
    miles: Optional[int]
    cash: Optional[float]
    available: bool

    def __str__(self) -> str:
        if not self.available:
            return f"{self.date}: N/A"
        return f"{self.date}: {self.miles:,}k + ${self.cash:.0f}"


@dataclass
class CalendarResult:
    origin: str
    destination: str
    month: str
    year: int
    fares: list[AwardFare] = field(default_factory=list)

    def filter_by_date_range(self, start_date: str, end_date: str) -> "CalendarResult":
        """Filter fares to only include dates within the given range (inclusive)."""
        filtered_fares = [f for f in self.fares if start_date <= f.date <= end_date]
        return CalendarResult(
            origin=self.origin,
            destination=self.destination,
            month=self.month,
            year=self.year,
            fares=filtered_fares,
        )

    def print_table(self, highlight_below: Optional[int] = None) -> None:
        print(f"\n{'='*60}")
        print(f"  {self.origin} → {self.destination} | {self.month} {self.year}")
        print(f"{'='*60}")
        print(f"{'Date':<12} {'Miles':>10} {'Cash':>8} {'Status':<12}")
        print(f"{'-'*12} {'-'*10} {'-'*8} {'-'*12}")

        for fare in self.fares:
            if fare.available:
                miles_str = f"{fare.miles:,}k" if fare.miles else "?"
                cash_str = f"${fare.cash:.0f}" if fare.cash is not None else "?"

                # Highlight if below threshold
                if highlight_below and fare.miles and fare.miles < highlight_below:
                    status = "🔥 DEAL!"
                    line = f"\033[92m{fare.date:<12} {miles_str:>10} {cash_str:>8} {status:<12}\033[0m"
                else:
                    status = "✓ Available"
                    line = f"{fare.date:<12} {miles_str:>10} {cash_str:>8} {status:<12}"
                print(line)
            else:
                miles_str = "-"
                cash_str = "-"
                status = "✗ N/A"
                print(f"{fare.date:<12} {miles_str:>10} {cash_str:>8} {status:<12}")

        available = [f for f in self.fares if f.available]
        if available:
            best = min(available, key=lambda x: (x.miles or float("inf")))
            print(f"\n🏆 Best fare: {best}")
            print(f"📊 Available: {len(available)}/{len(self.fares)} days")

            if highlight_below:
                deals = [f for f in available if f.miles and f.miles < highlight_below]
                if deals:
                    print(f"🔥 Deals (<{highlight_below}k): {len(deals)} days")


def parse_calendar_text(raw_text: str, year: int = 2026) -> CalendarResult:
    """Parse the raw calendar text into structured data."""
    month_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        raw_text,
    )
    month = month_match.group(1) if month_match else "Unknown"
    year = int(month_match.group(2)) if month_match else year

    month_num = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }.get(month, 1)

    pattern = r"(\d{1,2})\n\n(N/A|(\d+(?:\.\d+)?k)\s*\+\s*\$(\d+))"
    matches = re.findall(pattern, raw_text)

    fares = []
    seen_days = set()

    for match in matches:
        day = int(match[0])
        if day in seen_days:
            continue
        seen_days.add(day)

        date_str = f"{year}-{month_num:02d}-{day:02d}"

        if match[1] == "N/A":
            fares.append(
                AwardFare(
                    date=date_str, day=day, miles=None, cash=None, available=False
                )
            )
        else:
            miles = float(match[2].replace("k", ""))
            cash = float(match[3])
            fares.append(
                AwardFare(
                    date=date_str, day=day, miles=int(miles), cash=cash, available=True
                )
            )

    fares.sort(key=lambda x: x.day)

    origin_match = re.search(r"([A-Z]{3})\n\n.*?\n\n([A-Z]{3})", raw_text)
    origin = origin_match.group(1) if origin_match else "???"
    destination = origin_match.group(2) if origin_match else "???"

    return CalendarResult(
        origin=origin, destination=destination, month=month, year=year, fares=fares
    )


def slugify_fare_type(fare_type: str) -> str:
    """Convert a fare type into a filesystem-friendly suffix."""
    return re.sub(r"[^a-z0-9]+", "_", fare_type.lower()).strip("_")


@dataclass
class FlightSearchParams:
    origin: str
    destination: str
    outbound_date: str
    adults: int = 1
    round_trip: bool = False
    fare_type: str = FARE_TYPES["partner_business"]
    shopping_method: str = "onlineaward"
    locale: str = "en-us"

    def to_url(self) -> str:
        params = {
            "O": self.origin,
            "D": self.destination,
            "OD": self.outbound_date,
            "A": self.adults,
            "RT": str(self.round_trip).lower(),
            "RequestType": "Calendar",
            "ShoppingMethod": self.shopping_method,
            "int": "flightresultsmicrosite:viewby-calendar",
            "locale": self.locale,
        }
        base_url = "https://www.alaskaair.com/search/calendar"
        # Append FareType without encoding the '+' character
        return f"{base_url}?{urlencode(params)}&FareType={self.fare_type}"


async def fetch_award_calendar(
    params: FlightSearchParams, silent: bool = False
) -> dict:
    """
    Fetch award flight calendar data from Alaska Airlines.

    Args:
        params: Flight search parameters
        silent: If True, suppress output during fetch

    Returns:
        Dictionary containing calendar availability data
    """
    url = params.to_url()
    if not silent:
        print(f"Fetching: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        calendar_data = {"dates": [], "raw_responses": []}

        async def handle_response(response):
            """Capture API responses that contain calendar data."""
            if "calendar" in response.url.lower() or "award" in response.url.lower():
                try:
                    if "application/json" in response.headers.get("content-type", ""):
                        data = await response.json()
                        calendar_data["raw_responses"].append(
                            {"url": response.url, "data": data}
                        )
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Wait for calendar to load
            await page.wait_for_timeout(3000)

            # Try to extract calendar data from the page
            calendar_cells = await page.query_selector_all(
                "[class*='calendar'], [class*='Calendar'], [data-date]"
            )

            for cell in calendar_cells:
                try:
                    date_attr = await cell.get_attribute("data-date")
                    text = await cell.inner_text()

                    if date_attr or text:
                        calendar_data["dates"].append(
                            {
                                "date": date_attr,
                                "text": text.strip() if text else None,
                            }
                        )
                except Exception:
                    continue

            # Get full page content for debugging
            calendar_data["page_title"] = await page.title()

        except Exception as e:
            calendar_data["error"] = str(e)
            if not silent:
                print(f"Error fetching calendar: {e}")

        finally:
            await browser.close()

        return calendar_data


async def search_awards(
    origin: str,
    destination: str,
    outbound_date: str,
    date_range_start: str,
    date_range_end: str,
    highlight_below: int = 175,
    adults: int = 2,
    fare_type: str = FARE_TYPES["partner_business"],
    search_name: Optional[str] = None,
    save_results: bool = True,
    silent: bool = False,
) -> Optional[CalendarResult]:
    """
    Search for award flights and display results.

    Args:
        origin: Origin airport code (e.g., "BA3", "SFO")
        destination: Destination airport code (e.g., "TPE", "TYO")
        outbound_date: Reference date for calendar search (YYYY-MM-DD)
        date_range_start: Start of date filter range (YYYY-MM-DD)
        date_range_end: End of date filter range (YYYY-MM-DD)
        highlight_below: Highlight fares below this mileage threshold
        adults: Number of passengers
        fare_type: Fare type (e.g., FARE_TYPES["partner_business"])
        search_name: Optional label for display and saved result files
        save_results: Whether to save results to JSON files
        silent: If True, suppress output during fetch (for parallel execution)

    Returns:
        CalendarResult with filtered fares, or None if fetch failed
    """
    params = FlightSearchParams(
        origin=origin,
        destination=destination,
        outbound_date=outbound_date,
        adults=adults,
        round_trip=False,
        fare_type=fare_type,
    )
    result_suffix = search_name or slugify_fare_type(fare_type)

    if not silent:
        print(f"\n{'#'*60}")
        print(f"Searching for award flights:")
        if search_name:
            print(f"  Search: {search_name}")
        print(f"  Route: {origin} -> {destination}")
        print(f"  Date range: {date_range_start} to {date_range_end}")
        print(f"  Passengers: {adults}")
        print(f"  Fare type: {fare_type}")
        print(f"  Highlighting: < {highlight_below}k miles")
        print(f"{'#'*60}")

    result = await fetch_award_calendar(params, silent=silent)

    if save_results:
        output_file = f"{RESULTS_DIR}/alaska_{origin}_{destination}_{result_suffix}_raw.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        if not silent:
            print(f"\nRaw results saved to {output_file}")

    filtered_calendar = None
    if result.get("dates") and result["dates"]:
        raw_text = result["dates"][0].get("text", "")
        if raw_text:
            calendar = parse_calendar_text(raw_text)
            filtered_calendar = calendar.filter_by_date_range(
                date_range_start, date_range_end
            )
            # Store metadata for later printing
            filtered_calendar.highlight_below = highlight_below
            filtered_calendar.date_range_start = date_range_start
            filtered_calendar.date_range_end = date_range_end
            filtered_calendar.adults = adults
            filtered_calendar.fare_type = fare_type
            filtered_calendar.search_name = search_name

            if not silent:
                filtered_calendar.print_table(highlight_below=highlight_below)

            if save_results:
                parsed_output = (
                    f"{RESULTS_DIR}/alaska_{origin}_{destination}_{result_suffix}_parsed.json"
                )
                parsed_data = {
                    "origin": filtered_calendar.origin,
                    "destination": filtered_calendar.destination,
                    "month": filtered_calendar.month,
                    "year": filtered_calendar.year,
                    "fare_type": fare_type,
                    "search_name": search_name,
                    "date_range": {
                        "start": date_range_start,
                        "end": date_range_end,
                    },
                    "highlight_threshold": highlight_below,
                    "fares": [
                        {
                            "date": f.date,
                            "day": f.day,
                            "miles": f.miles,
                            "cash": f.cash,
                            "available": f.available,
                            "is_deal": f.available
                            and f.miles
                            and f.miles < highlight_below,
                        }
                        for f in filtered_calendar.fares
                    ],
                }
                with open(parsed_output, "w") as f:
                    json.dump(parsed_data, f, indent=2)
                if not silent:
                    print(f"Parsed results saved to {parsed_output}")

    if result.get("error") and not silent:
        print(f"Error: {result['error']}")

    return filtered_calendar


def print_result(
    calendar: Optional[CalendarResult],
    origin: str,
    destination: str,
    date_range_start: str,
    date_range_end: str,
    highlight_below: int,
    adults: int,
    fare_type: str,
    search_name: Optional[str] = None,
) -> None:
    """Print search result for a route."""
    print(f"\n{'#'*60}")
    print(f"Results for award flights:")
    if search_name:
        print(f"  Search: {search_name}")
    print(f"  Route: {origin} -> {destination}")
    print(f"  Date range: {date_range_start} to {date_range_end}")
    print(f"  Passengers: {adults}")
    print(f"  Fare type: {fare_type}")
    print(f"  Highlighting: < {highlight_below}k miles")
    print(f"{'#'*60}")

    if calendar:
        calendar.print_table(highlight_below=highlight_below)
    else:
        print("  No results found.")


async def main():
    # Define all searches
    searches = [
        {
            "origin": "PPT",
            "destination": "BA3",
            "outbound_date": "2026-09-12",
            "date_range_start": "2026-09-12",
            "date_range_end": "2026-09-12",
            "highlight_below": 50,
            "adults": 2,
            "fare_type": FARE_TYPES["partner_premium"],
            "search_name": "Partner Premium",
        },
        {
            "origin": "PPT",
            "destination": "BA3",
            "outbound_date": "2026-09-12",
            "date_range_start": "2026-09-12",
            "date_range_end": "2026-09-12",
            "highlight_below": 80,
            "adults": 2,
            "fare_type": FARE_TYPES["partner_business"],
            "search_name": "Partner Business",
        },
    ]

    # Create results directory if it doesn't exist
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Starting parallel search for all routes...")
    print(f"Searching {len(searches)} routes concurrently...\n")

    # Run all searches in parallel with silent mode
    tasks = [
        search_awards(
            origin=s["origin"],
            destination=s["destination"],
            outbound_date=s["outbound_date"],
            date_range_start=s["date_range_start"],
            date_range_end=s["date_range_end"],
            highlight_below=s["highlight_below"],
            adults=s["adults"],
            fare_type=s.get("fare_type", FARE_TYPES["partner_business"]),
            search_name=s.get("search_name"),
            silent=True,
        )
        for s in searches
    ]

    results = await asyncio.gather(*tasks)

    # Print results sequentially
    print("\n" + "=" * 60)
    print("ALL SEARCHES COMPLETE - RESULTS")
    print("=" * 60)

    for search_params, calendar in zip(searches, results):
        print_result(
            calendar,
            origin=search_params["origin"],
            destination=search_params["destination"],
            date_range_start=search_params["date_range_start"],
            date_range_end=search_params["date_range_end"],
            highlight_below=search_params["highlight_below"],
            adults=search_params["adults"],
            fare_type=search_params.get("fare_type", FARE_TYPES["partner_business"]),
            search_name=search_params.get("search_name"),
        )


if __name__ == "__main__":
    asyncio.run(main())
