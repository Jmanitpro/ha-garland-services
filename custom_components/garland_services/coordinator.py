"""DataUpdateCoordinator for Garland waste collection.

Each refresh:
1. Looks up the address's routes in the city's public ArcGIS service (cached so a
   GIS outage does not take the schedule offline).
2. Reads the city's Holiday Closure Information page and turns it into holiday
   shifts. Changes compared with the previous read fire
   ``garland_services_schedule_changed``.
3. Reads the city's recycling calendar page and flags a new annual Blue/Yellow
   calendar (diagnostic entities, ``garland_services_new_recycling_calendar``
   event and a Repairs issue).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GarlandApiError, GarlandClient
from .const import (
    CALENDAR_PAGE_URL, DOMAIN, EVENT_NEW_RECYCLING_CALENDAR, EVENT_SCHEDULE_CHANGED,
    HOLIDAY_URL, HORIZON_DAYS, LABELS, STORAGE_VERSION, UPDATE_HOURS,
)
from .holidays import HolidayFeed, HolidayShift, merge_shifts, parse_calendar_page, parse_holiday_page
from .schedule import BUILTIN_SHIFTS, VERIFIED_RECYCLING_YEARS, Pickup, create_schedule, recycle_group

_LOGGER = logging.getLogger(__name__)


@dataclass
class GarlandData:
    routes: dict
    group: str
    shifts: list[HolidayShift]
    pickups: list[Pickup]
    project_recycling: bool
    holiday: dict = field(default_factory=dict)
    calendar: dict = field(default_factory=dict)
    routes_source: str = "live"


def describe_shift(shift: HolidayShift) -> str:
    services = ", ".join(LABELS[s] for s in ("trash", "recycling", "brush") if s in shift.services)
    return (f"{shift.holiday}: {services} moves from {shift.original:%A, %B} {shift.original.day} "
            f"to {shift.adjusted:%A, %B} {shift.adjusted.day}")


class GarlandCoordinator(DataUpdateCoordinator[GarlandData]):
    def __init__(self, hass: HomeAssistant, client: GarlandClient, entry_id: str,
                 latitude: float, longitude: float, project_recycling: bool):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(hours=UPDATE_HOURS))
        self.client, self.latitude, self.longitude = client, latitude, longitude
        self.entry_id = entry_id
        self.project_recycling = project_recycling
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._stored: dict = {}
        self._unsub_midnight = None

    async def async_load(self) -> None:
        self._stored = await self._store.async_load() or {}
        self._unsub_midnight = async_track_time_change(
            self.hass, self._handle_midnight, hour=0, minute=0, second=5)

    @callback
    def async_shutdown_listeners(self) -> None:
        if self._unsub_midnight:
            self._unsub_midnight()
            self._unsub_midnight = None

    @callback
    def _handle_midnight(self, _now: datetime) -> None:
        """Roll the schedule forward a day without hitting the network."""
        if self.data:
            self.data.pickups = self._pickups(self.data.routes, self.data.shifts)
            self.async_set_updated_data(self.data)

    def _pickups(self, routes: dict, shifts: list[HolidayShift]) -> list[Pickup]:
        return create_schedule(routes, dt_util.now().date(), HORIZON_DAYS, shifts, self.project_recycling)

    # ------------------------------------------------------------------ routes
    async def _routes(self) -> tuple[dict, str]:
        try:
            routes = await self.client.get_routes(self.latitude, self.longitude)
            recycle_group(routes["recycling"])  # validate before caching
        except (GarlandApiError, ValueError, KeyError) as err:
            if cached := self._stored.get("routes"):
                _LOGGER.warning("Garland GIS lookup failed (%s); using cached routes", err)
                return cached, "cached"
            raise UpdateFailed(str(err)) from err
        self._stored["routes"] = routes
        return routes, "live"

    # ---------------------------------------------------------------- holidays
    async def _holidays(self, now: datetime) -> tuple[list[HolidayShift], dict]:
        cached = [HolidayShift.from_dict(d) for d in self._stored.get("shifts") or []]
        fallback = cached or list(BUILTIN_SHIFTS)
        feed: HolidayFeed | None = None
        error = None
        try:
            feed = parse_holiday_page(await self.client.get_page(HOLIDAY_URL))
            if not feed.notices:
                error, feed = "Holiday page had no recognizable holiday notices", None
        except GarlandApiError as err:
            error = str(err)
        if error:
            _LOGGER.warning("Garland holiday page unavailable (%s); using %s schedule",
                            error, "cached" if cached else "built-in")

        shifts = merge_shifts(feed, fallback)
        previous = self._stored.get("shifts")
        current = [s.as_dict() for s in shifts]
        info = dict(self._stored.get("holiday") or {})
        info.update(last_checked=now.isoformat(), error=error, source_url=HOLIDAY_URL)
        if feed is not None:
            info.update(
                source="live", page_year=feed.page_year,
                holidays=[n.as_dict() for n in feed.notices],
                warnings=feed.warnings, last_success=now.isoformat(),
            )
            if previous is not None and previous != current:
                self._fire_schedule_changed(previous, current, now)
                info["last_changed"] = now.isoformat()
            self._stored["shifts"] = current
        else:
            info["source"] = "cached" if cached else "built-in"
        self._stored["holiday"] = info
        return shifts, info

    def _fire_schedule_changed(self, previous: list[dict], current: list[dict], now: datetime) -> None:
        key = lambda d: (d["regular_date"], tuple(d["services"]))  # noqa: E731
        before, after = {key(d): d for d in previous}, {key(d): d for d in current}
        added = [after[k] for k in after if k not in before or before[k] != after[k]]
        removed = [before[k] for k in before if k not in after]
        today = now.date().isoformat()
        upcoming = [d for d in added if d["new_date"] >= today]
        message = "; ".join(describe_shift(HolidayShift.from_dict(d)) for d in upcoming) or \
            "The city updated its holiday collection schedule."
        _LOGGER.info("Garland holiday schedule changed: %s", message)
        self.hass.bus.async_fire(EVENT_SCHEDULE_CHANGED, {
            "entry_id": self.entry_id, "added": added, "removed": removed,
            "upcoming": upcoming, "message": message,
        })

    # ---------------------------------------------------------------- calendar
    async def _calendar(self, now: datetime) -> dict:
        info = dict(self._stored.get("calendar") or {})
        info.update(last_checked=now.isoformat(), source_url=CALENDAR_PAGE_URL, error=None)
        try:
            years = parse_calendar_page(await self.client.get_page(CALENDAR_PAGE_URL), CALENDAR_PAGE_URL)
            if years:
                info["published"] = {str(y): urls for y, urls in years.items()}
                info["last_success"] = now.isoformat()
            else:
                info["error"] = "No annual recycling calendar links found"
        except GarlandApiError as err:
            info["error"] = str(err)
        if info.get("error"):
            _LOGGER.warning("Garland recycling calendar check: %s", info["error"])

        published = {int(y): urls for y, urls in (info.get("published") or {}).items()}
        newest_verified = max(VERIFIED_RECYCLING_YEARS)
        new_years = sorted(y for y in published if y > newest_verified)
        info["latest_year"] = max(published) if published else None
        info["verified_years"] = sorted(VERIFIED_RECYCLING_YEARS)
        info["new_years"] = new_years
        info["status"] = ("new_calendar_available" if new_years
                          else "current" if published else "unknown")

        notified = set(self._stored.get("notified_years") or [])
        for year in new_years:
            url = published[year][0]
            info.setdefault("detected", {}).setdefault(str(year), now.isoformat())
            ir.async_create_issue(
                self.hass, DOMAIN, f"new_recycling_calendar_{year}",
                is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key="new_recycling_calendar",
                translation_placeholders={"year": str(year), "url": url},
                learn_more_url=url,
            )
            if year not in notified:
                notified.add(year)
                self.hass.bus.async_fire(EVENT_NEW_RECYCLING_CALENDAR, {
                    "entry_id": self.entry_id, "year": year, "urls": published[year],
                    "message": f"Garland published its {year} recycling calendar.",
                })
        for year in VERIFIED_RECYCLING_YEARS:
            ir.async_delete_issue(self.hass, DOMAIN, f"new_recycling_calendar_{year}")
        self._stored["notified_years"] = sorted(notified)
        self._stored["calendar"] = info
        return info

    # ------------------------------------------------------------------ update
    async def _async_update_data(self) -> GarlandData:
        now = dt_util.now()
        routes, routes_source = await self._routes()
        shifts, holiday = await self._holidays(now)
        calendar = await self._calendar(now)
        await self._store.async_save(self._stored)
        try:
            return GarlandData(
                routes=routes, group=recycle_group(routes["recycling"]), shifts=shifts,
                pickups=self._pickups(routes, shifts), project_recycling=self.project_recycling,
                holiday=holiday, calendar=calendar, routes_source=routes_source,
            )
        except (ValueError, KeyError) as err:
            raise UpdateFailed(str(err)) from err
