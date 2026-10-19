# We Brake for Wildlife Coffee Club map

Map of every coffee shop the club has run from, with routes and live voting for the shop rotation.
The live site is served from `docs/` by GitHub Pages.

- Shops and the run log are read live from the club Google Sheet (tabs `shop metadata` and `Schedule and Assignments`).
- Votes go through a Google Apps Script web app (`docs/apps_script.gs`) into the sheet's `votes` tab; set its URL in `docs/config.js`.
- Routes: `strava_fetch.py` downloads GPX (needs `credentials.yml` with `client_id` / `secret`), then `build_routes.py` writes `docs/routes.json`.
- Shop locations: `geocode_shops.py`, `place_from_routes.py` and `geocode_addresses.py` were used to fill the sheet's lat/lon columns.
