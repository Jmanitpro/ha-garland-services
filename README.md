# Garland City Services — Home Assistant (experimental)

A Garland, Texas waste collection integration, informed by [ha-okc-services](https://github.com/okie2020/ha-okc-services). **Independent adaptation, not a GitHub-created fork yet.** ArcGIS route lookup produces weekly trash/brush and alternate-week recycling schedules with published holiday shifts.

## Install

Copy `custom_components/garland_services` into `/config/custom_components/garland_services` and restart Home Assistant. Go to **Settings → Devices & Services → Add Integration → Garland City Services**. Your Home Assistant home coordinates are prefilled; verify they are inside Garland. This is an experimental release, so validate dates against the city's MyGarland lookup before relying on notifications.

For a HACS custom repository, first publish this folder to a GitHub repository, add that repository as a custom integration repository in HACS, then install it.

## Data sources

- [Public ArcGIS MapServer](https://maps.garlandtx.gov/arcgis/rest/services/WebApps/MyGarland/MapServer): layers 6 (trash), 7 (brush), 8 (recycling)
- [2026 Recycling Calendar](https://www.garlandtx.gov/DocumentCenter/View/23028/2026-BYCalendar-Eng-Spa)
- [Holiday Collection Notices](https://www.garlandtx.gov/3694/Holiday-Closure-Information)

## Known limitations (important)

- **Holiday changes are currently an explicit, source-verified 2026/January 2027 table, NOT live-parsed.** They will require a code update if the city changes its holiday notices. Do not assume automatic holiday updates in this release.
- **Recycling schedule is only projected for 2026**. The annual Blue/Yellow schedule must be verified for 2027 before enabling 2027 recycling predictions.
- The GIS recycling `ANCORE_DAY` attribute is intentionally not used until validated against multiple route records.
- GIS coordinate boundaries can be ambiguous, and city-side outages may leave entities unavailable.
- This integration uses Home Assistant coordinates; no address lookup / geocoding is needed.
- Calendar forecasts up to 366 days, but recycling is intentionally absent outside 2026.
- Not tested against an installed Home Assistant runtime or a live address-specific GIS response in this environment.

## License / provenance

Original independent implementation informed by the structure of **okie2020/ha-okc-services**. It is not a verbatim copy or licensed derivative of upstream code. Credit remains here as upstream architectural inspiration. See that upstream project's license before transplanting actual upstream code.
