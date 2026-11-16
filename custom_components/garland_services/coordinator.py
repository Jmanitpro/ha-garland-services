"""DataUpdateCoordinator for Garland waste collection."""
from datetime import timedelta, date
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import GarlandApiError, GarlandClient
from .schedule import create_schedule, recycle_group
from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)

class GarlandCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, client: GarlandClient, latitude: float, longitude: float):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(hours=12))
        self.client, self.latitude, self.longitude = client, latitude, longitude

    async def _async_update_data(self):
        try:
            routes = await self.client.get_routes(self.latitude, self.longitude)
            return {"routes":routes, "group":recycle_group(routes["recycling"]),
                    "pickups":create_schedule(routes,date.today(),horizon=45)}
        except (GarlandApiError, ValueError, KeyError) as err:
            raise UpdateFailed(str(err)) from err
