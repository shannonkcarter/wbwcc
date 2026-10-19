"""Bundle downloaded GPX files into docs/routes.json for the map.

Usage: python3 build_routes.py   (after strava_fetch.py)
Each route is keyed by shop + date so it survives row inserts in the sheet. Start/end ~150 m are
trimmed off activities (recorded runs) so nobody's doorstep shows up if they ran from home.
"""
import csv, json, math, os, re

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
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0, None
        for i in range(a + 1, b):
            d = abs(dy * (xy[i][0] - ax) - dx * (xy[i][1] - ay)) / norm
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


def main():
    routes = []
    for m in csv.DictReader(open(os.path.join(HERE, "routes", "strava_manifest.csv"))):
        if m["status"] != "ok":
            continue
        gpx = open(os.path.join(HERE, m["file"])).read()
        pts = [(float(a), float(b)) for a, b in re.findall(r'<trkpt[^>]*lat="([-\d.]+)"[^>]*lon="([-\d.]+)"', gpx)]
        if len(pts) < 2:
            continue
        if m["kind"] == "activities":
            pts = trim(pts, TRIM_M)
        pts = simplify(pts, TOLERANCE_M)
        routes.append({
            "shop": m["location"], "date": m["date"],
            "coords": [[round(a, 5), round(b, 5)] for a, b in pts],
        })
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    out = os.path.join(HERE, "docs", "routes.json")
    json.dump(routes, open(out, "w"), separators=(",", ":"))
    print(f"{len(routes)} routes, {sum(len(r['coords']) for r in routes)} points, {os.path.getsize(out) // 1024} KB -> docs/routes.json")


if __name__ == "__main__":
    main()
