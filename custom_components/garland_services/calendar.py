"""Unified future pickup calendar."""
from datetime import timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LABELS
from .schedule import create_schedule
from .sensor import device_info


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([GarlandCalendar(hass.data[DOMAIN][entry.entry_id], entry)])


class GarlandCalendar(CoordinatorEntity, CalendarEntity):
    _attr_name = None  # use the device name: calendar.garland_waste_collection
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = device_info(entry)

    @property
    def event(self):
        items = self.coordinator.data.pickups
        return self._event(items[0]) if items else None

    def _event(self, p):
        label = LABELS[p.service]
        if p.service == "recycling":
            label = f"{self.coordinator.data.group.title()} week recycling"
        suffix = f" (moved for {p.holiday})" if p.shifted and p.holiday else \
            " (holiday adjusted)" if p.shifted else ""
        notes = [f"Regular date: {p.original_date.isoformat()}"]
        if not p.verified:
            notes.append("Projected from the every-other-week cadence; "
                         "check the city's annual recycling calendar.")
        return CalendarEvent(start=p.date, end=p.date + timedelta(days=1),
                             summary=f"{label} pickup{suffix}", description="\n".join(notes))

    async def async_get_events(self, hass, start_date, end_date):
        tz = dt_util.get_default_time_zone()
        start = start_date.astimezone(tz).date()
        end = end_date.astimezone(tz).date()
        horizon = min(max((end - start).days + 2, 1), 366)
        data = self.coordinator.data
        items = create_schedule(data.routes, start, horizon, data.shifts, data.project_recycling)
        return [self._event(p) for p in items if start <= p.date < end]
