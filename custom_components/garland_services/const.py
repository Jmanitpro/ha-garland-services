"""Garland waste collection constants."""
DOMAIN = "garland_services"
BASE_URL = "https://maps.garlandtx.gov/arcgis/rest/services/WebApps/MyGarland/MapServer"
HOLIDAY_URL = "https://www.garlandtx.gov/3694/Holiday-Closure-Information"
CALENDAR_PAGE_URL = "https://www.garlandtx.gov/3814/Calendar"
SERVICES = ("trash", "recycling", "brush")
LAYERS = {"trash": (6, "T_DAY"), "brush": (7, "B_DAY"), "recycling": (8, "R_DAY")}
LABELS = {"trash": "Trash", "recycling": "Recycling", "brush": "Brush and bulky"}
ATTRIBUTION = "City of Garland, TX GIS and Sanitation"

CONF_PROJECT_RECYCLING = "project_recycling"
DEFAULT_PROJECT_RECYCLING = True

EVENT_SCHEDULE_CHANGED = f"{DOMAIN}_schedule_changed"
EVENT_NEW_RECYCLING_CALENDAR = f"{DOMAIN}_new_recycling_calendar"

STORAGE_VERSION = 1
UPDATE_HOURS = 6
HORIZON_DAYS = 45
