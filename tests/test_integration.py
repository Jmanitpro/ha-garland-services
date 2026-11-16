"""End-to-end setup against mocked city endpoints. Run with: pytest tests -q"""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.garland_services.const import (
    BASE_URL, CALENDAR_PAGE_URL, DOMAIN, EVENT_NEW_RECYCLING_CALENDAR, EVENT_SCHEDULE_CHANGED, HOLIDAY_URL,
)

FIXTURES = Path(__file__).parent / "fixtures"
HOLIDAY_HTML = (FIXTURES / "holiday_2026.html").read_text(encoding="utf-8")
CALENDAR_HTML = (FIXTURES / "calendar_page.html").read_text(encoding="utf-8")
GIS = {6: {"T_DAY": "Thursday"}, 7: {"B_DAY": "Friday"}, 8: {"R_DAY": "Thursday", "COLOR": "Blue"}}
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=dt_util.get_time_zone("America/Chicago"))


def mock_city(aioclient_mock, holiday=HOLIDAY_HTML, calendar=CALENDAR_HTML):
    aioclient_mock.clear_requests()
    for layer, attrs in GIS.items():
        aioclient_mock.get(f"{BASE_URL}/{layer}/query", json={"features": [{"attributes": attrs}]})
    aioclient_mock.get(HOLIDAY_URL, text=holiday)
    aioclient_mock.get(CALENDAR_PAGE_URL, text=calendar)


async def setup(hass, aioclient_mock):
    await hass.config.async_set_time_zone("America/Chicago")
    mock_city(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data={"latitude": 32.9, "longitude": -96.6})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_and_entities(hass, aioclient_mock, freezer, enable_custom_integrations):
    freezer.move_to(NOW)
    await setup(hass, aioclient_mock)
    trash = hass.states.get("sensor.garland_waste_collection_next_trash_pickup")
    assert trash.state == "2026-11-27"
    assert trash.attributes["holiday"] == "Thanksgiving Day"
    nxt = hass.states.get("sensor.garland_waste_collection_next_collection")
    assert nxt.state == "2026-11-27"
    assert "moved for Thanksgiving Day" in nxt.attributes["message"]
    assert "Blue week recycling" in nxt.attributes["message"]
    assert hass.states.get("sensor.garland_waste_collection_holiday_schedule_source").state == "live"
    assert hass.states.get("sensor.garland_waste_collection_recycling_calendar_year").state == "2026"
    assert hass.states.get("binary_sensor.garland_waste_collection_new_recycling_calendar").state == "off"
    assert hass.states.get("binary_sensor.garland_waste_collection_city_data_source_problem").state == "off"
    assert hass.states.get("calendar.garland_waste_collection") is not None


async def test_change_detection_and_new_calendar(hass, aioclient_mock, freezer, enable_custom_integrations):
    freezer.move_to(NOW)
    entry = await setup(hass, aioclient_mock)
    changes, calendars = [], []
    hass.bus.async_listen(EVENT_SCHEDULE_CHANGED, changes.append)
    hass.bus.async_listen(EVENT_NEW_RECYCLING_CALENDAR, calendars.append)

    # City moves Christmas pickup to Monday and posts the 2027 calendar.
    moved = HOLIDAY_HTML.replace("normally scheduled on <strong>Friday will move to Saturday.&nbsp;</strong><br><em>Please have your carts out by 7 a.m.</em></p><p><strong>New Year's Day 2027",
                                 "normally scheduled on <strong>Friday will move to Monday.&nbsp;</strong><br><em>Please have your carts out by 7 a.m.</em></p><p><strong>New Year's Day 2027")
    assert moved != HOLIDAY_HTML
    cal = CALENDAR_HTML + '<a href="/DocumentCenter/View/24001/2027-BYCalendar-Eng-Spa">2027</a>'
    mock_city(aioclient_mock, moved, cal)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(changes) == 1
    assert changes[0].data["upcoming"][0]["new_date"] == "2026-12-28"
    assert "Christmas" in changes[0].data["message"]
    assert hass.states.get("sensor.garland_waste_collection_holiday_schedule_last_changed").state not in ("unknown", "unavailable")
    assert len(calendars) == 1 and calendars[0].data["year"] == 2027
    assert hass.states.get("binary_sensor.garland_waste_collection_new_recycling_calendar").state == "on"
    assert hass.states.get("sensor.garland_waste_collection_recycling_calendar_year").state == "2027"

    # Same data again: no duplicate events.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(changes) == 1 and len(calendars) == 1


async def test_city_site_down_uses_fallback(hass, aioclient_mock, freezer, enable_custom_integrations):
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("America/Chicago")
    for layer, attrs in GIS.items():
        aioclient_mock.get(f"{BASE_URL}/{layer}/query", json={"features": [{"attributes": attrs}]})
    aioclient_mock.get(HOLIDAY_URL, status=503)
    aioclient_mock.get(CALENDAR_PAGE_URL, status=503)
    entry = MockConfigEntry(domain=DOMAIN, data={"latitude": 32.9, "longitude": -96.6})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garland_waste_collection_holiday_schedule_source").state == "built-in"
    assert hass.states.get("sensor.garland_waste_collection_next_trash_pickup").state == "2026-11-27"
    assert hass.states.get("binary_sensor.garland_waste_collection_city_data_source_problem").state == "on"


async def test_options_flow(hass, aioclient_mock, freezer, enable_custom_integrations):
    freezer.move_to(NOW)
    entry = await setup(hass, aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"project_recycling": False})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].project_recycling is False
