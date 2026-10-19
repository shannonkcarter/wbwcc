"""Cross-check shops.csv against route start points and fill missing locations.

Usage: python3 place_from_routes.py   (after geocode_shops.py and strava_fetch.py)
Loop routes (start ~= end) almost always start at the shop, so their start point is ground truth:
  - geocode within 300 m of the route start   -> verified
  - no geocode, or flagged geocode far away   -> use route start
  - confident geocode far from route start    -> review=CHECK (one of them is wrong)
Adds a `source` column: osm | osm+route | route.
"""
import csv, math, os, re, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
SHOPS = os.path.join(HERE, "shops.csv")


def km(a, b):
    dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def loop_starts():
    starts = {}
    for m in csv.DictReader(open(os.path.join(HERE, "routes", "strava_manifest.csv"))):
        if m["status"] != "ok":
            continue
        pts = re.findall(r'<trkpt[^>]*lat="([-\d.]+)"[^>]*lon="([-\d.]+)"', open(os.path.join(HERE, m["file"])).read())
        if not pts:
            continue
        s, e = (float(pts[0][0]), float(pts[0][1])), (float(pts[-1][0]), float(pts[-1][1]))
        if km(s, e) < 0.3:
            starts.setdefault(m["location"], []).append(s)
    return {k: (statistics.median(p[0] for p in v), statistics.median(p[1] for p in v)) for k, v in starts.items()}


def main():
    starts = loop_starts()
    rows = list(csv.DictReader(open(SHOPS)))
    for r in rows:
        if r["review"] == "OK":  # hand-confirmed; leave alone
            continue
        r["source"] = "osm" if r["lat"] else ""
        start = starts.get(r["shop"])
        if not start:
            continue
        dist = km(start, (float(r["lat"]), float(r["lon"]))) if r["lat"] else None
        if dist is not None and dist < 0.3:
            r["source"], r["review"] = "osm+route", ""
        elif r["review"] == "YES" or dist is None:
            r.update(lat=round(start[0], 6), lon=round(start[1], 6), matched_name="", address="",
                     source="route", review="")
        else:
            r["review"] = f"CHECK: osm pin is {dist:.1f} km from route start {start[0]:.5f},{start[1]:.5f}"

    fields = list(rows[0].keys()) + ([] if "source" in rows[0] else ["source"])
    with open(SHOPS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    for status in ["CHECK", "YES"]:
        hits = [r for r in rows if r["review"].startswith(status)]
        print(f"\n{status} ({len(hits)}):")
        for r in hits:
            print(f"  {r['shop']:30s} {r['matched_name'][:28]:28s} {r['address']}  {r['review'][6:]}")
    print("\nsources:", {s: sum(r.get("source") == s for r in rows) for s in ["osm", "osm+route", "route", ""]})


if __name__ == "__main__":
    main()
