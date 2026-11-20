"""Bundle downloaded GPX files into docs/routes.json for the map.

Usage: python3 build_routes.py   (after strava_fetch.py)
Also picks up hand-exported GPX (On The Go Map, Garmin, etc.) saved as routes/manual/YYYY-MM-DD.gpx,
named by run date; the shop comes from that date's row in the run log CSV. A manual file replaces
any Strava route for the same run. GPX with timestamps (a recorded run) gets the privacy trim.
Each route is keyed by shop + date so it survives row inserts in the sheet. Start/end ~150 m are
trimmed off activities (recorded runs) so nobody's doorstep shows up if they ran from home.
"""
import csv, datetime, glob, json, math, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
TOLERANCE_M = 8      # simplification tolerance
TRIM_M = 150         # privacy trim for recorded activities


def to_xy(p, lat0):
    return (p[1] * 111320 * math.cos(math.radians(lat0)), p[0] * 110540)


def simplify(pts, tol):
    """Ramer-Douglas-Peucker on lat/lon points, tolerance in metres."""
    if len(pts) < 3:
        return pts
    lat0 = pts[0][0]
    xy = [to_xy(p, lat0) for p in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, idx = 0, None
        for i in range(a + 1, b):
            # loops start and end at the same spot, so fall back to distance from that point
            d = (abs(dy * (xy[i][0] - ax) - dx * (xy[i][1] - ay)) / norm if norm > 1e-6
                 else math.hypot(xy[i][0] - ax, xy[i][1] - ay))
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def trim(pts, metres):
    def cut(seq):
        lat0, total = seq[0][0], 0
        for i in range(1, len(seq)):
            (x1, y1), (x2, y2) = to_xy(seq[i - 1], lat0), to_xy(seq[i], lat0)
            total += math.hypot(x2 - x1, y2 - y1)
            if total >= metres:
                return seq[i:]
        return seq
    return cut(cut(pts)[::-1])[::-1]


def read_points(path):
    gpx = open(path, encoding="utf-8", errors="ignore").read()
    # track points from recordings/courses, route points from planners that export <rte>;
    # attribute order varies by app, so pull lat/lon out of each tag separately
    pts = []
    for tag in re.findall(r'<(?:trkpt|rtept)\b[^>]*>', gpx):
        lat, lon = re.search(r'lat="([-\d.]+)"', tag), re.search(r'lon="([-\d.]+)"', tag)
        if lat and lon:
            pts.append((lat.group(1), lon.group(1)))
    return [(float(a), float(b)) for a, b in pts], "<time>" in gpx


def norm_date(d):
    """'5/29/2026' or '2026-05-29' -> date, else None."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(d.strip(), fmt).date()
        except ValueError:
            pass
    return None


def manual_routes():
    """{(shop, date): (points, recorded)} for routes/manual/YYYY-MM-DD*.gpx."""
    log = glob.glob(os.path.join(HERE, "*Schedule and Assignments.csv"))[0]
    by_date = {}
    for r in list(csv.reader(open(log, encoding="utf-8-sig")))[1:]:
        if len(r) >= 4 and r[0].strip() and norm_date(r[3]):
            by_date[norm_date(r[3])] = (r[0].strip(), r[3].strip())
    out = {}
    for path in sorted(glob.glob(os.path.join(HERE, "routes", "manual", "*.gpx"))):
        name = os.path.basename(path)
        d = norm_date(name[:10])
        if d not in by_date:
            print(f"  skipping {name}: no run on that date in the log (name files YYYY-MM-DD.gpx)")
            continue
        pts, recorded = read_points(path)
        if len(pts) < 2:
            print(f"  skipping {name}: no track or route points found")
            continue
        out[by_date[d]] = (pts, recorded)
        print(f"  manual: {name} -> {by_date[d][0]}")
    return out


def main():
    runs = {}
    for m in csv.DictReader(open(os.path.join(HERE, "routes", "strava_manifest.csv"))):
        if m["status"] != "ok":
            continue
        pts, _ = read_points(os.path.join(HERE, m["file"]))
        runs[(m["location"], m["date"])] = (pts, m["kind"] == "activities")
    runs.update(manual_routes())
    routes = []
    for (shop, date), (pts, recorded) in runs.items():
        if len(pts) < 2:
            continue
        if recorded:
            pts = trim(pts, TRIM_M)
        pts = simplify(pts, TOLERANCE_M)
        routes.append({
            "shop": shop, "date": date,
            "coords": [[round(a, 5), round(b, 5)] for a, b in pts],
        })
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    out = os.path.join(HERE, "docs", "routes.json")
    json.dump(routes, open(out, "w"), separators=(",", ":"))
    print(f"{len(routes)} routes, {sum(len(r['coords']) for r in routes)} points, {os.path.getsize(out) // 1024} KB -> docs/routes.json")


if __name__ == "__main__":
    main()
