"""Collection sensors plus diagnostic sensors for the city's published sources."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN, LABELS, SERVICES
from .coordinator import GarlandCoordinator, describe_shift
from .schedule import Pickup


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: GarlandCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for service in SERVICES:
        entities.extend((PickupDate(coordinator, entry, service), DaysUntil(coordinator, entry, service)))
    entities += [
        NextCollection(coordinator, entry),
        RecyclingGroup(coordinator, entry),
        HolidaySchedule(coordinator, entry),
        LastScheduleChange(coordinator, entry),
        RecyclingCalendar(coordinator, entry),
    ]
    async_add_entities(entities)


def device_info(entry) -> dict:
    return {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Garland waste collection",
            "manufacturer": "City of Garland", "model": "Sanitation schedule",
            "configuration_url": "https://www.garlandtx.gov/3694/Holiday-Closure-Information"}


def spoken_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class Base(CoordinatorEntity[GarlandCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_device_info = device_info(entry)

    def _next(self, service: str) -> Pickup | None:
        return next((p for p in self.coordinator.data.pickups if p.service == service), None)


class PickupDate(Base):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coord, entry, service):
        super().__init__(coord, entry)
        self.service = service
        self._attr_name = f"Next {LABELS[service]} pickup"
        self._attr_unique_id = f"{entry.entry_id}_{service}_date"
        self._attr_icon = {"trash": "mdi:trash-can", "recycling": "mdi:recycle",
                           "brush": "mdi:tree"}[service]

    @property
    def native_value(self):
        p = self._next(self.service)
        return p.date if p else None

    @property
    def extra_state_attributes(self):
        p = self._next(self.service)
        if not p:
            return {}
        attrs = {"holiday_shift": p.shifted, "regular_date": p.original_date.isoformat(),
                 "holiday": p.holiday}
        if self.service == "recycling":
            attrs["group"] = self.coordinator.data.group.title()
            attrs["verified"] = p.verified
        return attrs


class DaysUntil(Base):
    _attr_icon = "mdi:calendar-clock"
    _attr_native_unit_of_measurement = "d"

    def __init__(self, coord, entry, service):
        super().__init__(coord, entry)
        self.service = service
        self._attr_name = f"{LABELS[service]} pickup in"
        self._attr_unique_id = f"{entry.entry_id}_{service}_days"

    @property
    def native_value(self):
        p = self._next(self.service)
        return (p.date - dt_util.now().date()).days if p else None


class NextCollection(Base):
    """Everything collected on the next collection day - built for announcements."""

    _attr_name = "Next collection"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:dump-truck"

    def __init__(self, coord, entry):
        super().__init__(coord, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_collection"

    def _day(self) -> list[Pickup]:
        pickups = self.coordinator.data.pickups
        return [p for p in pickups if p.date == pickups[0].date] if pickups else []

    @property
    def native_value(self):
        day = self._day()
        return day[0].date if day else None

    @property
    def extra_state_attributes(self):
        day = self._day()
        if not day:
            return {}
        when = day[0].date
        services = [p.service for p in day]
        labels = [LABELS[s] for s in services]
        if "recycling" in services:
            labels[services.index("recycling")] = f"{self.coordinator.data.group.title()} week recycling"
        days = (when - dt_util.now().date()).days
        relative = "today" if days == 0 else "tomorrow" if days == 1 else f"on {when:%A}"
        holidays = sorted({p.holiday for p in day if p.holiday})
        message = f"{spoken_list(labels)} pickup is {relative}"
        if holidays:
            message += f", moved for {spoken_list(holidays)}"
        return {
            "services": services,
            "days_until": days,
            "holiday_shift": any(p.shifted for p in day),
            "holiday": holidays[0] if holidays else None,
            "message": message + ".",
        }


class RecyclingGroup(Base):
    _attr_name = "Recycling week group"
    _attr_icon = "mdi:recycle"

    def __init__(self, coord, entry):
        super().__init__(coord, entry)
        self._attr_unique_id = f"{entry.entry_id}_group"

    @property
    def native_value(self):
        return self.coordinator.data.group.title()


# ------------------------------------------------------------------ diagnostics
class Diagnostic(Base):
    _attr_entity_category = EntityCategory.DIAGNOSTIC


def _ts(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


class HolidaySchedule(Diagnostic):
    """Where holiday shifts came from: live page, cache, or built-in table."""

    _attr_name = "Holiday schedule source"
    _attr_icon = "mdi:calendar-alert"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["live", "cached", "built-in"]

    def __init__(self, coord, entry):
        super().__init__(coord, entry)
        self._attr_unique_id = f"{entry.entry_id}_holiday_source"

    @property
    def native_value(self):
        return self.coordinator.data.holiday.get("source")

    @property
    def extra_state_attributes(self):
        info = self.coordinator.data.holiday
        today = dt_util.now().date()
        upcoming = [s for s in self.coordinator.data.shifts if s.adjusted >= today]
        return {
            "page_year": info.get("page_year"),
            "last_checked": info.get("last_checked"),
            "last_success": info.get("last_success"),
            "last_changed": info.get("last_changed"),
            "upcoming_shifts": [s.as_dict() | {"summary": describe_shift(s)} for s in upcoming],
            "holidays": info.get("holidays", []),
            "parse_warnings": info.get("warnings", []),
            "error": info.get("error"),
            "source_url": info.get("source_url"),
            "routes_source": self.coordinator.data.routes_source,
        }


class LastScheduleChange(Diagnostic):
    _attr_name = "Holiday schedule last changed"
    _attr_icon = "mdi:calendar-sync"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coord, entry):
        super().__init__(coord, entry)
        self._attr_unique_id = f"{entry.entry_id}_holiday_changed"

    @property
    def native_value(self):
        return _ts(self.coordinator.data.holiday.get("last_changed"))


class RecyclingCalendar(Diagnostic):
    """Newest annual Blue/Yellow calendar the city has published."""

    _attr_name = "Recycling calendar year"
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coord, entry):
        super().__init__(coord, entry)
        self._attr_unique_id = f"{entry.entry_id}_recycling_calendar"

    @property
    def native_value(self):
        return self.coordinator.data.calendar.get("latest_year")

    @property
    def extra_state_attributes(self):
        info = self.coordinator.data.calendar
        latest = info.get("latest_year")
        published = info.get("published") or {}
        return {
            "status": info.get("status"),
            "verified_years": info.get("verified_years"),
            "new_years": info.get("new_years"),
            "calendar_urls": published.get(str(latest), []) if latest else [],
            "published_years": sorted(int(y) for y in published),
            "detected": info.get("detected", {}),
            "projecting_recycling": self.coordinator.data.project_recycling,
            "last_checked": info.get("last_checked"),
            "error": info.get("error"),
            "source_url": info.get("source_url"),
        }
