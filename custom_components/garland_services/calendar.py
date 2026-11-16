"""Unified future pickup calendar."""
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
from homeassistant.components.calendar import CalendarEntity,CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN,LABELS
from .schedule import create_schedule
TZ=ZoneInfo("America/Chicago")

async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([GarlandCalendar(hass.data[DOMAIN][entry.entry_id],entry)])

class GarlandCalendar(CoordinatorEntity,CalendarEntity):
    _attr_name="Garland waste collection"
    _attr_has_entity_name=True
    def __init__(self,coordinator,entry):
        super().__init__(coordinator)
        self._attr_unique_id=f"{entry.entry_id}_calendar"
        self._attr_device_info={"identifiers":{(DOMAIN,entry.entry_id)},"name":"Garland waste collection","manufacturer":"City of Garland"}
    @property
    def event(self):
        items=self.coordinator.data["pickups"]
        return self._event(items[0]) if items else None
    def _event(self,p):
        suffix=" (holiday adjusted)" if p.shifted else ""
        return CalendarEvent(start=p.date,end=p.date+timedelta(days=1),
                             summary=f"{LABELS[p.service]} pickup{suffix}",
                             description=f"Regular date: {p.original_date.isoformat()}")
    async def async_get_events(self,hass,start_date,end_date):
        start=start_date.astimezone(TZ).date()
        end=end_date.astimezone(TZ).date()
        horizon=min(max((end-start).days+2,1),366)
        items=create_schedule(self.coordinator.data["routes"],start,horizon)
        return [self._event(p) for p in items if start<=p.date<end]
