"""Garland City Services integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GarlandClient
from .const import CONF_PROJECT_RECYCLING, DEFAULT_PROJECT_RECYCLING, DOMAIN
from .coordinator import GarlandCoordinator

PLATFORMS = ["sensor", "binary_sensor", "calendar"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = GarlandClient(async_get_clientsession(hass))
    coordinator = GarlandCoordinator(
        hass, client, entry.entry_id, entry.data["latitude"], entry.data["longitude"],
        entry.options.get(CONF_PROJECT_RECYCLING, DEFAULT_PROJECT_RECYCLING),
    )
    await coordinator.async_load()
    entry.async_on_unload(coordinator.async_shutdown_listeners)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if result:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return result
