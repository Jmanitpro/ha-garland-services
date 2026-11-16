"""Pure schedule computations; GIS routes are authoritative for weekday/group."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from .holidays import ALL_SERVICES, HolidayShift

WEEKDAYS = {n: i for i, n in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}

# Published City of Garland 2026 Blue/Yellow collection calendar.
# 2026-01-06 is a Blue Tuesday; 2026-01-13 is a Yellow Tuesday.
BLUE_ANCHOR = date(2026, 1, 6)
YELLOW_ANCHOR = date(2026, 1, 13)
# Years whose Blue/Yellow alternation has been checked against the city's printed
# calendar. Other years are *projected* by continuing the every-other-week cadence
# and are flagged as unverified. When the city publishes a new annual calendar the
# integration raises a diagnostic so the year can be checked and added here.
VERIFIED_RECYCLING_YEARS = frozenset({2026})

# Built-in fallback: city-published 2026 / Jan 2027 holiday shifts. Used only when
# the live holiday page cannot be read and nothing is cached yet.
BUILTIN_SHIFTS: tuple[HolidayShift, ...] = (
    HolidayShift(date(2026, 1, 1), date(2026, 1, 2), "New Year's Day"),
    HolidayShift(date(2026, 1, 2), date(2026, 1, 3), "New Year's Day"),
    HolidayShift(date(2026, 11, 26), date(2026, 11, 27), "Thanksgiving Day"),
    HolidayShift(date(2026, 11, 27), date(2026, 11, 28), "Day After Thanksgiving"),
    HolidayShift(date(2026, 12, 25), date(2026, 12, 26), "Christmas"),
    HolidayShift(date(2027, 1, 1), date(2027, 1, 2), "New Year's Day 2027"),
)
# Backwards-compatible view: original date -> adjusted date.
OVERRIDES = {s.original: s.adjusted for s in BUILTIN_SHIFTS}


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


def recycling_verified(day: date) -> bool:
    return day.year in VERIFIED_RECYCLING_YEARS


def recycling_week(day: date, group: str, project: bool = False) -> bool:
    """True when `day` falls in the group's recycling week.

    Outside verified years this returns False unless `project` is set, in which
    case the every-other-week cadence is continued from the 2026 anchors.
    """
    if not recycling_verified(day) and not project:
        return False
    anchor = BLUE_ANCHOR if group == "blue" else YELLOW_ANCHOR
    return ((day - anchor).days // 7) % 2 == 0


@dataclass(frozen=True)
class Pickup:
    service: str
    date: date
    original_date: date
    holiday: str | None = None
    verified: bool = True

    @property
    def shifted(self) -> bool:
        return self.date != self.original_date


def _shift_index(overrides) -> dict[date, list[HolidayShift]]:
    index: dict[date, list[HolidayShift]] = {}
    if isinstance(overrides, Mapping):
        items: Iterable[HolidayShift] = (
            v if isinstance(v, HolidayShift) else HolidayShift(k, v, "Holiday")
            for k, v in overrides.items()
        )
    else:
        items = overrides
    for shift in items:
        index.setdefault(shift.original, []).append(shift)
    return index


def create_schedule(
    routes: dict,
    today: date,
    horizon: int = 45,
    overrides: Mapping[date, date] | Mapping[date, HolidayShift] | Iterable[HolidayShift] | None = None,
    project_recycling: bool = False,
) -> list[Pickup]:
    if not (1 <= horizon <= 366):
        raise ValueError("horizon must be between 1 and 366")
    shifts = _shift_index(BUILTIN_SHIFTS if overrides is None else overrides)
    weekdays = {
        "trash": weekday_number(routes["trash"]["T_DAY"]),
        "brush": weekday_number(routes["brush"]["B_DAY"]),
        "recycling": weekday_number(routes["recycling"]["R_DAY"]),
    }
    group = recycle_group(routes["recycling"])
    last = today + timedelta(days=horizon)
    items = []
    # Start a few days back so a pickup pushed forward into the window is kept.
    for offset in range(-3, horizon + 1):
        original = today + timedelta(days=offset)
        for service, weekday in weekdays.items():
            if original.weekday() != weekday:
                continue
            verified = True
            if service == "recycling":
                if not recycling_week(original, group, project_recycling):
                    continue
                verified = recycling_verified(original)
            shift = next((s for s in shifts.get(original, ()) if service in s.services), None)
            actual = shift.adjusted if shift else original
            if today <= actual <= last:
                items.append(Pickup(service, actual, original, shift.holiday if shift else None, verified))
    return sorted(items, key=lambda x: (x.date, x.service))


__all__ = [
    "ALL_SERVICES", "BLUE_ANCHOR", "BUILTIN_SHIFTS", "OVERRIDES", "Pickup",
    "VERIFIED_RECYCLING_YEARS", "YELLOW_ANCHOR", "create_schedule",
    "recycle_group", "recycling_verified", "recycling_week", "weekday_number",
]
