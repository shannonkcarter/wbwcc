"""Geocode shops in data/shop_metadata.csv that have an address but no lat/lon.

Usage: python3 geocode_addresses.py
Tries the US Census geocoder, then Photon. Writes data/geocoded_fill.csv (shop, lat, lon, matched)
for pasting back into the sheet's lat/lon columns.
"""
import csv, json, os, re, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wbwcc-run-club-map"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def census(addr):
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + urllib.parse.urlencode(
        {"address": addr, "benchmark": "Public_AR_Current", "format": "json"})
    m = fetch(url)["result"]["addressMatches"]
    if m:
        return m[0]["coordinates"]["y"], m[0]["coordinates"]["x"], "census: " + m[0]["matchedAddress"]


def photon(addr):
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": addr, "lat": 29.76, "lon": -95.37, "limit": 1})
    f = fetch(url)["features"]
    if f:
        lon, lat = f[0]["geometry"]["coordinates"]
        p = f[0]["properties"]
        return lat, lon, "photon: " + " ".join(filter(None, [p.get("housenumber"), p.get("street"), p.get("postcode")]))


def clean(addr):
    addr = re.sub(r"\s*(#|Ste\.?|Suite|Bldg|Unit)\s*\w+", "", addr)  # unit numbers confuse geocoders
    addr = re.sub(r"(?<=[a-z])(?=Houston)", ", ", addr)               # "Suite CHouston" -> ", Houston"
    if "TX" not in addr:
        addr = addr.replace("Houston,", "Houston, TX")
    return addr


rows = list(csv.DictReader(open(os.path.join(HERE, "data", "shop_metadata.csv"))))
out = []
for r in rows:
    if r["lat"] or not r["address"]:
        continue
    addr = clean(r["address"])
    hit = census(addr) or photon(addr)
    time.sleep(1)
    lat, lon, matched = hit if hit else ("", "", "NO MATCH")
    print(f"{r['shop'][:26]:26s} {addr[:45]:45s} -> {matched}")
    out.append({"shop": r["shop"], "lat": round(lat, 6) if lat else "", "lon": round(lon, 6) if lon else "", "matched": matched})
with open(os.path.join(HERE, "data", "geocoded_fill.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["shop", "lat", "lon", "matched"])
    w.writeheader()
    w.writerows(out)
