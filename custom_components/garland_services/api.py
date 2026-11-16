"""Public Garland ArcGIS polygon lookup, no credentials required."""
from __future__ import annotations
import asyncio
import aiohttp
from .const import BASE_URL, LAYERS

class GarlandApiError(Exception):
    """GIS service unavailable or returned invalid data."""

class OutsideServiceArea(GarlandApiError):
    """Coordinates do not resolve to all required collection routes."""

class GarlandClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_route(self, service: str, latitude: float, longitude: float) -> dict:
        layer, field = LAYERS[service]
        params = {
            "geometry": f"{longitude},{latitude}",
            "geometryType": "esriGeometryPoint", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
            "returnGeometry": "false", "f": "json",
        }
        try:
            async with asyncio.timeout(25):
                async with self.session.get(f"{BASE_URL}/{layer}/query", params=params) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise GarlandApiError(str(exc)) from exc
        if "error" in payload:
            raise GarlandApiError(str(payload["error"]))
        features = payload.get("features") or []
        if not features:
            raise OutsideServiceArea(f"No {service} route contains configured coordinates")
        if len(features) != 1:
            raise GarlandApiError(f"Ambiguous {service} route: {len(features)} polygons intersect")
        attributes = features[0].get("attributes") or {}
        if not attributes.get(field):
            raise GarlandApiError(f"Missing {field} from {service} GIS layer")
        return attributes

    async def get_routes(self, latitude: float, longitude: float) -> dict[str, dict]:
        results = await asyncio.gather(*(self.get_route(s,latitude,longitude) for s in LAYERS))
        return dict(zip(LAYERS, results))

    async def get_page(self, url: str) -> str:
        """Fetch a public garlandtx.gov page as text."""
        try:
            async with asyncio.timeout(25):
                async with self.session.get(url, headers=PAGE_HEADERS) as response:
                    response.raise_for_status()
                    return await response.text()
        except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError) as exc:
            raise GarlandApiError(f"{url}: {exc}") from exc


PAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant-garland_services; +https://github.com/Jmanitpro/ha-garland-services)",
    "Accept": "text/html,application/xhtml+xml",
}
