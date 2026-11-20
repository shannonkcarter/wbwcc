# We Brake for Wildlife Coffee Club map

Map of every coffee shop the club has run from, with routes and live voting for the shop rotation.
The live site is served from `docs/` by GitHub Pages.

- Shops and the run log are read live from the club Google Sheet (tabs `shop metadata` and `Schedule and Assignments`).
- Votes go through a Google Apps Script web app (`docs/apps_script.gs`) into the sheet's `votes` tab; set its URL in `docs/config.js`.
- Routes: `strava_fetch.py` downloads GPX (needs `credentials.yml` with `client_id` / `secret`), then `build_routes.py` writes `docs/routes.json`. Both read a CSV export of the `Schedule and Assignments` tab saved in the repo root, so refresh that first.
- Non-Strava routes (On The Go Map, Garmin, etc.): export the GPX, save it as `routes/manual/YYYY-MM-DD.gpx` using the run date, and rerun `build_routes.py`. The shop comes from that date's row in the run log.
- Shop locations: `geocode_shops.py`, `place_from_routes.py` and `geocode_addresses.py` were used to fill the sheet's lat/lon columns.
