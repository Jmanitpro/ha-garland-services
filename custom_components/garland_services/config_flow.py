"""UI flow using Home Assistant's home location or custom coordinates."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_PROJECT_RECYCLING, DEFAULT_PROJECT_RECYCLING, DOMAIN


class GarlandConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            latitude, longitude = user_input["latitude"], user_input["longitude"]
            await self.async_set_unique_id(f"{latitude:.6f},{longitude:.6f}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Garland waste collection", data=user_input)
        schema = vol.Schema({
            vol.Required("latitude", default=round(self.hass.config.latitude, 6)):
                vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
            vol.Required("longitude", default=round(self.hass.config.longitude, 6)):
                vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GarlandOptionsFlow()


class GarlandOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_PROJECT_RECYCLING, DEFAULT_PROJECT_RECYCLING)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_PROJECT_RECYCLING, default=current): bool,
        }))
