"""Date and days-until sensors."""
from datetime import date
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, LABELS, SERVICES, ATTRIBUTION

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator=hass.data[DOMAIN][entry.entry_id]
    entities=[]
    for service in SERVICES:
        entities.extend((PickupDate(coordinator,entry,service), DaysUntil(coordinator,entry,service)))
    entities.append(RecyclingGroup(coordinator,entry))
    async_add_entities(entities)

class Base(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name=True
    _attr_attribution=ATTRIBUTION
    def __init__(self,coordinator,entry):
        super().__init__(coordinator)
        self._attr_device_info={"identifiers":{(DOMAIN,entry.entry_id)},"name":"Garland waste collection","manufacturer":"City of Garland"}
    def _next(self,service):
        return next((p for p in self.coordinator.data["pickups"] if p.service==service),None)

class PickupDate(Base):
    _attr_device_class=SensorDeviceClass.DATE
    def __init__(self,coord,entry,service):
        super().__init__(coord,entry);self.service=service
        self._attr_name=f"Next {LABELS[service]} pickup"
        self._attr_unique_id=f"{entry.entry_id}_{service}_date"
    @property
    def native_value(self):
        p=self._next(self.service)
        return p.date if p else None
    @property
    def extra_state_attributes(self):
        p=self._next(self.service)
        return {"holiday_shift":p.shifted,"regular_date":p.original_date.isoformat()} if p else {}

class DaysUntil(Base):
    _attr_icon="mdi:calendar-clock"
    def __init__(self,coord,entry,service):
        super().__init__(coord,entry);self.service=service
        self._attr_name=f"{LABELS[service]} pickup in"
        self._attr_unique_id=f"{entry.entry_id}_{service}_days"
        self._attr_native_unit_of_measurement="d"
    @property
    def native_value(self):
        p=self._next(self.service)
        return (p.date-date.today()).days if p else None

class RecyclingGroup(Base):
    _attr_name="Recycling week group"
    _attr_icon="mdi:recycle"
    def __init__(self,coord,entry):
        super().__init__(coord,entry);self._attr_unique_id=f"{entry.entry_id}_group"
    @property
    def native_value(self):
        return self.coordinator.data["group"].title()
