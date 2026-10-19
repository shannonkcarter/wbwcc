"""Build one-row-per-shop list from the run log and geocode it via Photon (OpenStreetMap).

Usage: python3 geocode_shops.py
Writes shops.csv. Rows with review=YES need a human check (fix lat/lon/address by hand).
Rerunning keeps any rows already marked review=OK.
"""
import csv, difflib, glob, json, math, os, re, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shops.csv")
HOUSTON = (29.76, -95.37)
NOT_SHOPS = {"eureka's turkey 5k @ 11am"}
FIELDS = ["shop", "visits", "first_visit", "last_visit", "leaders",
          "matched_name", "address", "lat", "lon", "score", "review"]


def km(a, b):
    dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("&", "and"))


POI_KEYS = {"amenity", "shop", "craft", "leisure", "tourism"}
BAD_VALUES = {"parking", "bank", "school", "university", "college", "park", "fuel", "pharmacy"}


def photon(q):
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode(
        {"q": q, "lat": HOUSTON[0], "lon": HOUSTON[1], "limit": 8, "lang": "en"})
    req = urllib.request.Request(url, headers={"User-Agent": "wbwcc-run-club-map"})
    time.sleep(1)
    return json.load(urllib.request.urlopen(req, timeout=20))["features"]


def similarity(shop, cand):
    a, b = norm(shop), norm(cand)
    sim = difflib.SequenceMatcher(None, a, b).ratio()
    core = norm(re.sub(r"\(.*?\)| - .*", "", shop)).strip()  # drop "(MKT trail)", "- Levy Park"
    if core and (re.search(rf"\b{re.escape(core)}\b", b) or re.search(rf"\b{re.escape(b)}\b", core)):
        sim = max(sim, 0.9)
    return sim


def best_match(shop):
    best = None
    base = re.sub(r"\(.*?\)", "", shop).replace(" / ", " ").strip()
    for q in [base + " Houston", base + " coffee Houston", base + " cafe Houston"]:
        for f in photon(q):
            p = f["properties"]
            if p.get("osm_key") not in POI_KEYS or p.get("osm_value") in BAD_VALUES:
                continue
            lon, lat = f["geometry"]["coordinates"]
            if km(HOUSTON, (lat, lon)) > 35:
                continue
            sim = similarity(shop, p.get("name", ""))
            if best is None or sim > best[0]:
                addr = " ".join(filter(None, [p.get("housenumber"), p.get("street")]))
                addr = ", ".join(filter(None, [addr, p.get("city"), p.get("postcode")]))
                best = (sim, p.get("name", ""), addr, lat, lon)
        if best and best[0] >= 0.9:
            break
    return best


def main():
    log_csv = glob.glob(os.path.join(HERE, "*Schedule and Assignments.csv"))[0]
    shops = {}
    for r in list(csv.reader(open(log_csv, encoding="utf-8-sig")))[1:]:
        name, leader, _, date = (c.strip() for c in r[:4])
        if not name or name.lower() in NOT_SHOPS:
            continue
        s = shops.setdefault(name, {"shop": name, "dates": [], "leaders": []})
        s["dates"].append(date)
        if leader and leader not in s["leaders"]:
            s["leaders"].append(leader)

    kept = {}
    if os.path.exists(OUT):
        kept = {r["shop"]: r for r in csv.DictReader(open(OUT)) if r["review"] == "OK"}

    rows = []
    for name, s in shops.items():
        row = {"shop": name, "visits": len(s["dates"]), "first_visit": s["dates"][0],
               "last_visit": s["dates"][-1], "leaders": "; ".join(s["leaders"])}
        if name in kept:
            row.update({k: kept[name][k] for k in ["matched_name", "address", "lat", "lon", "score", "review"]})
        else:
            m = best_match(name)
            if m:
                sim, mname, addr, lat, lon = m
                row.update(matched_name=mname, address=addr, lat=round(lat, 6), lon=round(lon, 6),
                           score=round(sim, 2), review="" if sim >= 0.85 else "YES")
            else:
                row.update(matched_name="", address="", lat="", lon="", score=0, review="YES")
        print(f"{row['review'] or 'ok':4s} {row['score']!s:5s} {name[:30]:30s} -> {row['matched_name'][:30]:30s} {row['address']}")
        rows.append(row)

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} shops, {sum(r['review'] == 'YES' for r in rows)} need review -> shops.csv")


if __name__ == "__main__":
    main()
