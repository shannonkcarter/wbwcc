"""Download GPX for every Strava link in the run log.

Usage: python3 strava_fetch.py
First run opens a browser to approve access; the token is cached in .strava_token.json.
Writes routes/gpx/<row>.gpx and routes/strava_manifest.csv (one line per Strava row + status).
"""
import csv, glob, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, ".strava_token.json")
OUT_DIR = os.path.join(HERE, "routes", "gpx")
PORT = 8723
API = "https://www.strava.com/api/v3"


def load_creds():
    creds = {}
    for line in open(os.path.join(HERE, "credentials.yml")):
        if ":" in line:
            k, v = line.split(":", 1)
            creds[k.strip()] = v.strip().strip("'\"")
    return creds["client_id"], creds["secret"]


def authorize(client_id, secret):
    code = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code["value"] = q.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Strava access approved. You can close this tab.")

        def log_message(self, *a):
            pass

    url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "approval_prompt": "auto",
        "redirect_uri": f"http://localhost:{PORT}/callback",
        "scope": "read,read_all,activity:read_all",
    })
    print("Opening browser to approve Strava access:\n" + url)
    webbrowser.open(url)
    server = HTTPServer(("localhost", PORT), Handler)
    while "value" not in code:
        server.handle_request()
    if not code["value"]:
        sys.exit("Authorization was declined.")
    return token_request(client_id, secret, grant_type="authorization_code", code=code["value"])


def token_request(client_id, secret, **params):
    data = urllib.parse.urlencode({"client_id": client_id, "client_secret": secret, **params}).encode()
    tok = json.load(urllib.request.urlopen("https://www.strava.com/oauth/token", data))
    json.dump(tok, open(TOKEN_FILE, "w"))
    os.chmod(TOKEN_FILE, 0o600)
    return tok


def get_token():
    client_id, secret = load_creds()
    if not os.path.exists(TOKEN_FILE):
        return authorize(client_id, secret)["access_token"]
    tok = json.load(open(TOKEN_FILE))
    if tok["expires_at"] < time.time() + 60:
        tok = token_request(client_id, secret, grant_type="refresh_token", refresh_token=tok["refresh_token"])
    return tok["access_token"]


def api(path, token, raw=False):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(3):
        try:
            body = urllib.request.urlopen(req).read()
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                print("  rate limited, waiting 60s")
                time.sleep(60)
                continue
            raise


def resolve(url):
    """Return ('routes'|'activities', id) for a Strava URL, following strava.app.link short links."""
    m = re.search(r"strava\.com/(routes|activities)/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    if "strava.app.link" in url:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        except Exception:
            return None
        html = urllib.parse.unquote(html)
        m = re.search(r"strava\.com/(routes|activities)/(\d+)", html)
        if m:
            return m.group(1), m.group(2)
    return None


def activity_gpx(act_id, token):
    act = api(f"/activities/{act_id}", token)
    streams = api(f"/activities/{act_id}/streams?keys=latlng,altitude&key_by_type=true", token)
    pts = streams.get("latlng", {}).get("data", [])
    alts = streams.get("altitude", {}).get("data", [None] * len(pts))
    trk = "".join(
        f'<trkpt lat="{lat}" lon="{lon}">' + (f"<ele>{e}</ele>" if e is not None else "") + "</trkpt>"
        for (lat, lon), e in zip(pts, alts)
    )
    name = (act.get("name") or "").replace("&", "&amp;").replace("<", "&lt;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="wbwcc">'
        f"<trk><name>{name}</name><trkseg>{trk}</trkseg></trk></gpx>"
    ).encode()


def main():
    log_csv = glob.glob(os.path.join(HERE, "*Schedule and Assignments.csv"))[0]
    rows = list(csv.reader(open(log_csv, encoding="utf-8-sig")))[1:]
    token = get_token()
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = []
    for i, r in enumerate(rows, start=2):  # sheet row number
        location, leader, url, date = (c.strip() for c in r[:4])
        if "strava" not in url:
            continue
        rec = {"row": i, "location": location, "leader": leader, "date": date, "url": url,
               "kind": "", "strava_id": "", "status": "", "file": ""}
        target = resolve(url)
        if not target:
            rec["status"] = "could not resolve link"
        else:
            rec["kind"], rec["strava_id"] = target
            path = os.path.join(OUT_DIR, f"{i:03d}.gpx")
            try:
                if rec["kind"] == "routes":
                    gpx = api(f"/routes/{rec['strava_id']}/export_gpx", token, raw=True)
                else:
                    gpx = activity_gpx(rec["strava_id"], token)
                open(path, "wb").write(gpx)
                rec["status"], rec["file"] = "ok", os.path.relpath(path, HERE)
            except urllib.error.HTTPError as e:
                rec["status"] = {404: "not found / not yours (404)", 403: "no access (403)"}.get(e.code, f"HTTP {e.code}")
        print(f"row {i:3d}  {location[:28]:28s} {rec['kind'] or '-':10s} {rec['status']}")
        manifest.append(rec)
        time.sleep(0.5)
    with open(os.path.join(HERE, "routes", "strava_manifest.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest[0]))
        w.writeheader()
        w.writerows(manifest)
    ok = sum(m["status"] == "ok" for m in manifest)
    print(f"\n{ok}/{len(manifest)} Strava links downloaded -> routes/gpx/")


if __name__ == "__main__":
    main()
