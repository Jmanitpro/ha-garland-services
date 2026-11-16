"""Diagnostic binary sensors: new recycling calendar published, city sources reachable."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .sensor import device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NewRecyclingCalendar(coordinator, entry), SourceProblem(coordinator, entry)])


class _Base(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_device_info = device_info(entry)


class NewRecyclingCalendar(_Base):
    """On when the city has published a recycling calendar for a year not yet verified."""

    _attr_name = "New recycling calendar"
    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_new_recycling_calendar"

    @property
    def is_on(self):
        return bool(self.coordinator.data.calendar.get("new_years"))

    @property
    def extra_state_attributes(self):
        info = self.coordinator.data.calendar
        published = info.get("published") or {}
        new = info.get("new_years") or []
        return {
            "new_years": new,
            "calendar_urls": [u for y in new for u in published.get(str(y), [])],
            "verified_years": info.get("verified_years"),
        }


class SourceProblem(_Base):
    """On when a city page could not be read and cached/built-in data is in use."""

    _attr_name = "City data source problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_source_problem"

    @property
    def is_on(self):
        data = self.coordinator.data
        return bool(data.holiday.get("error") or data.calendar.get("error") or data.routes_source != "live")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        return {
            "gis": data.routes_source,
            "holiday_page": data.holiday.get("error") or "ok",
            "calendar_page": data.calendar.get("error") or "ok",
        }
