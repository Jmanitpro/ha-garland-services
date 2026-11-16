"""Run with: python -m unittest discover -s tests -v

Pure-logic tests; the Home Assistant package __init__ is not imported.
"""
import importlib
import sys
import types
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "garland_services"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Register a bare package so relative imports work without running __init__.py.
_pkg = types.ModuleType("garland_services")
_pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("garland_services", _pkg)
schedule = importlib.import_module("garland_services.schedule")
holidays = importlib.import_module("garland_services.holidays")

ROUTES = {"trash": {"T_DAY": "Thursday"}, "brush": {"B_DAY": "Friday"},
          "recycling": {"R_DAY": "Thursday", "COLOR": "Blue"}}
HOLIDAY_HTML = (FIXTURES / "holiday_2026.html").read_text(encoding="utf-8")
CALENDAR_HTML = (FIXTURES / "calendar_page.html").read_text(encoding="utf-8")


class ScheduleTests(unittest.TestCase):
    def test_weekday(self):
        self.assertEqual(schedule.weekday_number("Thu"), 3)

    def test_blue_week(self):
        self.assertTrue(schedule.recycling_week(date(2026, 11, 26), "blue"))
        self.assertFalse(schedule.recycling_week(date(2026, 11, 19), "blue"))

    def test_thanksgiving(self):
        pickups = schedule.create_schedule(ROUTES, date(2026, 11, 25), 5)
        self.assertTrue(any(p.service == "trash" and p.date == date(2026, 11, 27) and p.shifted for p in pickups))
        self.assertTrue(any(p.service == "brush" and p.date == date(2026, 11, 28) for p in pickups))
        trash = next(p for p in pickups if p.service == "trash")
        self.assertEqual(trash.holiday, "Thanksgiving Day")

    def test_no_2027_recycling_without_projection(self):
        pickups = schedule.create_schedule(ROUTES, date(2027, 1, 1), 10)
        self.assertFalse(any(p.service == "recycling" for p in pickups))

    def test_2027_recycling_projected_and_flagged(self):
        pickups = schedule.create_schedule(ROUTES, date(2027, 1, 1), 21, project_recycling=True)
        recycling = [p for p in pickups if p.service == "recycling"]
        self.assertTrue(recycling)
        self.assertTrue(all(not p.verified for p in recycling))
        # Cadence continues: exactly two weeks apart.
        self.assertEqual((recycling[1].date - recycling[0].date).days, 14)
        # Continuity across the year boundary from the last verified 2026 pickup.
        self.assertTrue(schedule.recycling_week(date(2026, 12, 24), "blue"))
        self.assertFalse(schedule.recycling_week(date(2026, 12, 31), "blue"))
        self.assertEqual(recycling[0].date, date(2027, 1, 7))

    def test_2026_recycling_verified(self):
        pickups = schedule.create_schedule(ROUTES, date(2026, 11, 20), 10, project_recycling=True)
        self.assertTrue(all(p.verified for p in pickups if p.service == "recycling"))

    def test_invalid_group(self):
        with self.assertRaises(ValueError):
            schedule.recycle_group({"COLOR": "unknown"})

    def test_legacy_mapping_overrides(self):
        pickups = schedule.create_schedule(ROUTES, date(2026, 11, 25), 5,
                                           overrides={date(2026, 11, 26): date(2026, 11, 28)})
        trash = next(p for p in pickups if p.service == "trash")
        self.assertEqual(trash.date, date(2026, 11, 28))

    def test_service_specific_shift(self):
        shift = holidays.HolidayShift(date(2026, 11, 26), date(2026, 11, 27), "X", frozenset({"trash"}))
        pickups = schedule.create_schedule(ROUTES, date(2026, 11, 25), 5, [shift])
        by_service = {p.service: p for p in pickups if p.original_date == date(2026, 11, 26)}
        self.assertEqual(by_service["trash"].date, date(2026, 11, 27))
        self.assertEqual(by_service["recycling"].date, date(2026, 11, 26))


class HolidayParserTests(unittest.TestCase):
    def setUp(self):
        self.feed = holidays.parse_holiday_page(HOLIDAY_HTML)

    def test_page_year(self):
        self.assertEqual(self.feed.page_year, 2026)
        self.assertEqual(self.feed.warnings, [])

    def test_live_page_matches_verified_table(self):
        parsed = {(s.original, s.adjusted, s.holiday) for s in self.feed.shifts}
        builtin = {(s.original, s.adjusted, s.holiday) for s in schedule.BUILTIN_SHIFTS}
        self.assertEqual(parsed, builtin)

    def test_unaffected_holidays_recorded(self):
        unaffected = {n.holiday for n in self.feed.notices if not n.collection_affected}
        self.assertIn("Martin Luther King Jr. Day", unaffected)
        self.assertIn("Christmas Eve", unaffected)
        self.assertEqual(len(self.feed.notices), 11)

    def test_new_wording_and_new_year(self):
        html = """<h2>Holiday Service Delays for 2027</h2>
        <p><strong>Memorial Day -</strong> The Transfer Station will be closed Monday, May 31, 2027.<br>
        Trash and recycling collections normally scheduled on Monday will be collected on Tuesday, June 1, 2027.</p>
        <p><strong>Labor Day -</strong> closed Monday, September 6, 2027. Collection will not be affected.</p>"""
        feed = holidays.parse_holiday_page(html)
        self.assertEqual(feed.page_year, 2027)
        self.assertEqual(len(feed.shifts), 1)
        shift = feed.shifts[0]
        self.assertEqual((shift.original, shift.adjusted), (date(2027, 5, 31), date(2027, 6, 1)))
        self.assertEqual(shift.services, frozenset({"trash", "recycling"}))

    def test_wrong_weekday_is_rejected(self):
        html = "<p><b>Oops -</b> Collections normally scheduled on Thursday will be collected on Friday, January 3, 2026.</p>"
        feed = holidays.parse_holiday_page(html)
        self.assertEqual(feed.shifts, [])
        self.assertTrue(feed.warnings)

    def test_garbage_page(self):
        feed = holidays.parse_holiday_page("<html><body><p>Page not found</p></body></html>")
        self.assertEqual(feed.notices, [])

    def test_merge_live_is_authoritative_for_covered_years(self):
        stale = holidays.HolidayShift(date(2026, 7, 3), date(2026, 7, 4), "Removed by city")
        older = holidays.HolidayShift(date(2025, 12, 25), date(2025, 12, 26), "Christmas 2025")
        merged = holidays.merge_shifts(self.feed, [stale, older])
        self.assertNotIn(stale, merged)
        self.assertIn(older, merged)
        self.assertEqual(len(merged), len(self.feed.shifts) + 1)

    def test_merge_without_live_uses_fallback(self):
        merged = holidays.merge_shifts(None, list(schedule.BUILTIN_SHIFTS))
        self.assertEqual(len(merged), len(schedule.BUILTIN_SHIFTS))

    def test_round_trip(self):
        for shift in self.feed.shifts:
            self.assertEqual(holidays.HolidayShift.from_dict(shift.as_dict()), shift)


class CalendarPageTests(unittest.TestCase):
    def test_years_and_urls(self):
        found = holidays.parse_calendar_page(CALENDAR_HTML, "https://www.garlandtx.gov/3814/Calendar")
        self.assertEqual(sorted(found), [2025, 2026])
        self.assertIn("https://www.garlandtx.gov/DocumentCenter/View/23028/2026-BYCalendar-Eng-Spa", found[2026])

    def test_new_year_detected(self):
        html = CALENDAR_HTML + '<a href="/DocumentCenter/View/24001/2027-BYCalendar-Eng-Spa">2027</a>'
        found = holidays.parse_calendar_page(html, "https://www.garlandtx.gov/3814/Calendar")
        self.assertEqual(max(found), 2027)


if __name__ == "__main__":
    unittest.main()
