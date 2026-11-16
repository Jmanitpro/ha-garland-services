"""Run with: python -m unittest discover -s tests -v"""
import sys,unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"custom_components"))
# Avoid importing the HA-dependent package __init__ for pure algorithm tests.
import importlib.util
spec=importlib.util.spec_from_file_location("schedule",Path(__file__).resolve().parents[1]/"custom_components/garland_services/schedule.py")
schedule=importlib.util.module_from_spec(spec)
sys.modules["schedule"]=schedule
spec.loader.exec_module(schedule)
ROUTES={"trash":{"T_DAY":"Thursday"},"brush":{"B_DAY":"Friday"},"recycling":{"R_DAY":"Thursday","COLOR":"Blue"}}
class ScheduleTests(unittest.TestCase):
    def test_weekday(self):
        self.assertEqual(schedule.weekday_number("Thu"),3)
    def test_blue_week(self):
        self.assertTrue(schedule.recycling_week(date(2026,11,26),"blue"))
        self.assertFalse(schedule.recycling_week(date(2026,11,19),"blue"))
    def test_thanksgiving(self):
        pickups=schedule.create_schedule(ROUTES,date(2026,11,25),5)
        self.assertTrue(any(p.service=="trash" and p.date==date(2026,11,27) and p.shifted for p in pickups))
        self.assertTrue(any(p.service=="brush" and p.date==date(2026,11,28) for p in pickups))
    def test_no_2027_recycling(self):
        pickups=schedule.create_schedule(ROUTES,date(2027,1,1),10)
        self.assertFalse(any(p.service=="recycling" for p in pickups))
    def test_invalid_group(self):
        with self.assertRaises(ValueError):
            schedule.recycle_group({"COLOR":"unknown"})
if __name__=="__main__":unittest.main()
