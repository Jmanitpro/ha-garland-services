"""Pure schedule computations; GIS routes are authoritative for weekday/group."""
from __future__ import annotations
from datetime import date, timedelta
from dataclasses import dataclass

WEEKDAYS = {n: i for i, n in enumerate(("monday","tuesday","wednesday","thursday","friday","saturday","sunday"))}
# Published City of Garland 2026 blue/yellow collection calendar.
# 2026-01-06 is a blue Tuesday; 2026-01-13 is a yellow Tuesday.
BLUE_ANCHOR = date(2026, 1, 6)
YELLOW_ANCHOR = date(2026, 1, 13)
# Only explicit city-published modifications. Never assume a holiday shifts pickup.
# original date -> adjusted date
OVERRIDES = {
    date(2026,1,1): date(2026,1,2), date(2026,1,2): date(2026,1,3),
    date(2026,11,26): date(2026,11,27), date(2026,11,27): date(2026,11,28),
    date(2026,12,25): date(2026,12,26), date(2027,1,1): date(2027,1,2),
}

def weekday_number(value: str) -> int:
    normalized = str(value).strip().lower()
    for name, number in WEEKDAYS.items():
        if normalized == name or normalized == name[:3]:
            return number
    raise ValueError(f"Unrecognized collection weekday {value!r}")

def recycle_group(attrs: dict) -> str:
    # COLOR is the primary field. R_WEEK is fallback only when it explicitly names a color.
    for key in ("COLOR", "R_WEEK"):
        raw = str(attrs.get(key) or "").strip().lower()
        if raw in ("blue", "yellow"):
            return raw
        if raw.startswith("blue "):
            return "blue"
        if raw.startswith("yellow "):
            return "yellow"
    raise ValueError("Recycling group is not explicitly Blue/Yellow in GIS attributes")

def recycling_week(day: date, group: str) -> bool:
    if day.year != 2026:
        return False  # no unverified future-year predictions
    anchor = BLUE_ANCHOR if group == "blue" else YELLOW_ANCHOR
    return ((day - anchor).days // 7) % 2 == 0

@dataclass(frozen=True)
class Pickup:
    service: str
    date: date
    original_date: date

    @property
    def shifted(self) -> bool:
        return self.date != self.original_date


def create_schedule(routes: dict, today: date, horizon: int = 45, overrides: dict[date,date] | None = None) -> list[Pickup]:
    if not (1 <= horizon <= 366):
        raise ValueError("horizon must be between 1 and 366")
    exceptions = OVERRIDES if overrides is None else overrides
    weekdays = {
        "trash": weekday_number(routes["trash"]["T_DAY"]),
        "brush": weekday_number(routes["brush"]["B_DAY"]),
        "recycling": weekday_number(routes["recycling"]["R_DAY"]),
    }
    group = recycle_group(routes["recycling"])
    items = []
    # Include the previous two days in case holidays shift dates beyond the nominal day.
    for offset in range(-2, horizon + 1):
        original = today + timedelta(days=offset)
        for service, weekday in weekdays.items():
            if original.weekday() != weekday:
                continue
            if service == "recycling" and not recycling_week(original, group):
                continue
            actual = exceptions.get(original, original)
            if today <= actual <= today + timedelta(days=horizon):
                items.append(Pickup(service, actual, original))
    return sorted(items, key=lambda x: (x.date,x.service))
