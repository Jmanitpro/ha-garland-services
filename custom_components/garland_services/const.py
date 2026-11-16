"""Garland waste collection constants."""
DOMAIN = "garland_services"
BASE_URL = "https://maps.garlandtx.gov/arcgis/rest/services/WebApps/MyGarland/MapServer"
HOLIDAY_URL = "https://www.garlandtx.gov/3694/Holiday-Closure-Information"
SERVICES = ("trash", "recycling", "brush")
LAYERS = {"trash": (6, "T_DAY"), "brush": (7, "B_DAY"), "recycling": (8, "R_DAY")}
LABELS = {"trash": "Trash", "recycling": "Recycling", "brush": "Brush and bulky"}
ATTRIBUTION = "City of Garland, TX GIS and Sanitation"
