#!/usr/bin/env python3
"""
Alaska Airlines Award Flight Calendar Scraper

Fetch calendar awards or verified nonstop Main fares from detailed flight results.
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
from pathlib import Path
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
    miles: Optional[float]  # Thousands of miles; preserve values such as 57.5k.
    cash: Optional[float]
    available: bool

    def __str__(self) -> str:
        if not self.available:
            return f"{self.date}: N/A"
        return f"{self.date}: {self.miles:g}k + ${self.cash:g}"


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
                miles_str = f"{fare.miles:g}k" if fare.miles else "?"
                cash_str = f"${fare.cash:g}" if fare.cash is not None else "?"

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
                    date=date_str, day=day, miles=miles, cash=cash, available=True
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

    def to_url(self, nonstop_only: bool = False) -> str:
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
        if nonstop_only:
            base_url = "https://www.alaskaair.com/search/results"
            params.pop("RequestType")
            params.pop("int")
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


def parse_nonstop_fares(cards: list[dict], params: FlightSearchParams) -> CalendarResult:
    """Choose the cheapest verified nonstop Main fare, in thousands of miles."""
    date = datetime.strptime(params.outbound_date, "%Y-%m-%d")
    fares = []
    for card in cards:
        if card["path"] != "Nonstop direct flight path":
            raise ValueError("Nonstop filter returned a connecting or unverified flight")
        if not card["main"]:
            raise ValueError("Flight card has no Main fare tile")
        for tile in card["main"]:
            if tile["disabled"] and "Unavailable" in tile["text"]:
                continue
            match = re.search(r"([\d,]+(?:\.\d+)?)\s*k\s+(?:points\s+)?(?:pts\s+)?\+\s*\$([\d,]+(?:\.\d+)?)", tile["text"])
            if not match or tile["disabled"]:
                raise ValueError(f"Unrecognized Main award fare: {tile['text']}")
            fares.append(AwardFare(params.outbound_date, date.day,
                                   float(match[1].replace(",", "")),
                                   float(match[2].replace(",", "")), True))
    best = min(fares, key=lambda f: (f.miles, f.cash)) if fares else AwardFare(
        params.outbound_date, date.day, None, None, False)
    return CalendarResult(params.origin, params.destination, date.strftime("%B"), date.year, [best])


async def fetch_nonstop_awards(params: FlightSearchParams) -> dict:
    """Use the detailed results filter and verify every returned flight card."""
    result = {"url": params.to_url(nonstop_only=True), "nonstop_only": True}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_default_timeout(60000)
            await page.goto(result["url"], wait_until="domcontentloaded")
            filters = page.get_by_role("button", name=re.compile("Filters and Sort button"))
            await filters.click()
            nonstop = page.get_by_role("radio", name="Nonstop only", exact=True)
            await nonstop.check()
            if not await nonstop.is_checked():
                raise RuntimeError("Could not select nonstop-only filter")
            await page.get_by_role("button", name="Apply", exact=True).click()
            # Wait for a result count; never interpret an unloaded page as no fares.
            count = page.get_by_text(re.compile(r"^Showing \d+ of \d+$"))
            await count.wait_for()
            while await page.get_by_role("button", name="Show more results", exact=True).is_visible():
                previous = await count.inner_text()
                await page.get_by_role("button", name="Show more results", exact=True).click()
                await page.wait_for_function("previous => [...document.querySelectorAll('*')].some(e => /^Showing \\d+ of \\d+$/.test(e.textContent) && e.textContent !== previous)", arg=previous)
            result["result_count"] = await count.inner_text()
            result["cards"] = await page.locator(".flight-card-content").evaluate_all("""cards => cards.map(card => ({
                path: card.querySelector('[aria-label$="flight path"], [aria-label^="Flight path"]')?.getAttribute('aria-label'),
                flight: card.querySelector('.flight-number')?.textContent,
                text: card.innerText,
                main: [...card.querySelectorAll('button')]
                    .filter(b => b.querySelector('.cos-primary')?.textContent.trim() === 'Main')
                    .map(b => ({text: b.innerText, disabled: b.disabled}))
            }))""")
            shown, total = map(int, re.findall(r"\d+", result["result_count"]))
            if shown != total or len(result["cards"]) != total:
                raise RuntimeError("Incomplete flight results")
            # Verify the filter remained selected after results settled.
            await filters.click()
            if not await nonstop.is_checked():
                raise RuntimeError("Nonstop filter did not remain applied")
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            await browser.close()
    return result


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
    nonstop_only: bool = False,
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
        nonstop_only: Search a single date for verified nonstop Main fares.

    Returns:
        CalendarResult with filtered fares, or None if no calendar was parsed.
        Fetch errors and unverified nonstop results raise an exception.
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
    if save_results:
        Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)
        # A failed refresh must not leave a previous fare looking current.
        Path(f"{RESULTS_DIR}/alaska_{origin}_{destination}_{result_suffix}_parsed.json").unlink(missing_ok=True)

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

    if nonstop_only and (fare_type != FARE_TYPES["lowest"] or
                         not date_range_start == outbound_date == date_range_end):
        raise ValueError("Nonstop searches require one exact date and the lowest/Main fare type")
    result = (await fetch_nonstop_awards(params) if nonstop_only
              else await fetch_award_calendar(params, silent=silent))

    if save_results:
        output_file = f"{RESULTS_DIR}/alaska_{origin}_{destination}_{result_suffix}_raw.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        if not silent:
            print(f"\nRaw results saved to {output_file}")

    if result.get("error"):
        raise RuntimeError(result["error"])
    filtered_calendar = None
    if nonstop_only:
        filtered_calendar = parse_nonstop_fares(result["cards"], params)
    elif result.get("dates"):
        raw_text = result["dates"][0].get("text", "")
        if raw_text:
            calendar = parse_calendar_text(raw_text)
            filtered_calendar = calendar.filter_by_date_range(date_range_start, date_range_end)
    if filtered_calendar is not None:
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
                "nonstop_only": nonstop_only,
                "adults": adults,
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
            "origin": "SFO",
            "destination": "LIR",
            "outbound_date": "2026-12-26",
            "date_range_start": "2026-12-26",
            "date_range_end": "2026-12-26",
            "highlight_below": 50,
            "adults": 2,
            "fare_type": FARE_TYPES["lowest"],
            "search_name": "Main",
            "nonstop_only": True,
        },
        {
            "origin": "LIR",
            "destination": "SFO",
            "outbound_date": "2027-01-02",
            "date_range_start": "2027-01-02",
            "date_range_end": "2027-01-02",
            "highlight_below": 50,
            "adults": 2,
            "fare_type": FARE_TYPES["lowest"],
            "search_name": "Main",
            "nonstop_only": True,
        },
    ]

    # Create results directory if it doesn't exist
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("Starting parallel search for all routes...")
    print(f"Searching {len(searches)} routes concurrently...\n")

    async def run_search(search):
        try:
            calendar = await search_awards(**search, silent=True)
            print_result(calendar, **{key: value for key, value in search.items()
                                      if key not in ("outbound_date", "nonstop_only")})
            if search.get("nonstop_only"):
                print("  Verified: nonstop only, Main fares")
            return True
        except Exception as exc:
            print(f"FAILED {search['origin']} -> {search['destination']}: {exc}", flush=True)
            return False

    outcomes = await asyncio.gather(*(run_search(s) for s in searches))
    if not all(outcomes):
        raise RuntimeError("One or more award searches failed")


if __name__ == "__main__":
    asyncio.run(main())
