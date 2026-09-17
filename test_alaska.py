import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from alaska import FARE_TYPES, FlightSearchParams, parse_calendar_text, parse_nonstop_fares, search_awards


def card(text="Main\n49.5k\npoints\npts\n+\n$25.60", path="Nonstop direct flight path", disabled=False):
    return {"path": path, "main": [{"text": text, "disabled": disabled}]}


class FareTests(unittest.TestCase):
    def setUp(self):
        self.params = FlightSearchParams("SFO", "LIR", "2026-12-26", adults=2, fare_type=FARE_TYPES["lowest"])

    def test_fractional_calendar_fare(self):
        fare = parse_calendar_text("December 2026\n26\n\n57.5k + $25").fares[0]
        self.assertEqual(fare.miles, 57.5)

    def test_cheapest_main_preserves_fractions(self):
        result = parse_nonstop_fares([card("Main 70k points + $25"), card()], self.params)
        self.assertEqual((result.fares[0].miles, result.fares[0].cash), (49.5, 25.6))

    def test_connecting_or_unknown_path_rejected(self):
        for path in ("Flight path with 1 stop", None):
            with self.subTest(path=path), self.assertRaises(ValueError):
                parse_nonstop_fares([card(path=path)], self.params)

    def test_malformed_or_missing_main_rejected(self):
        for item in (card("Main mystery price"), {"path": "Nonstop direct flight path", "main": []}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                parse_nonstop_fares([item], self.params)

    def test_unavailable_and_empty_results(self):
        for cards in ([], [card("Main Unavailable", disabled=True)]):
            self.assertFalse(parse_nonstop_fares(cards, self.params).fares[0].available)


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def run_search(self):
        return await search_awards("SFO", "LIR", "2026-12-26", "2026-12-26", "2026-12-26",
                                   highlight_below=50, fare_type=FARE_TYPES["lowest"],
                                   search_name="Main", nonstop_only=True, silent=True)

    async def test_saved_threshold_and_nonstop_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch("alaska.RESULTS_DIR", directory):
            for miles, expected in ((49.5, True), (50, False), (50.5, False)):
                with patch("alaska.fetch_nonstop_awards", AsyncMock(return_value={"cards": [card(f"Main {miles}k points + $25")]})):
                    await self.run_search()
                data = json.loads((Path(directory) / "alaska_SFO_LIR_Main_parsed.json").read_text())
                self.assertTrue(data["nonstop_only"])
                self.assertEqual(data["adults"], 2)
                self.assertEqual(data["fares"][0]["is_deal"], expected)

    async def test_failure_raises_and_removes_stale_result(self):
        with tempfile.TemporaryDirectory() as directory, patch("alaska.RESULTS_DIR", directory):
            stale = Path(directory) / "alaska_SFO_LIR_Main_parsed.json"
            stale.write_text('{"fares": [{"is_deal": true}]}')
            with patch("alaska.fetch_nonstop_awards", AsyncMock(return_value={"error": "timeout"})):
                with self.assertRaisesRegex(RuntimeError, "timeout"):
                    await self.run_search()
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
