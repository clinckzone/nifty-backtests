"""
Download daily close + Total Return Index for each index from NSE Indices
(niftyindices.com) into ./data/<INDEX>.csv.

The site's API returns at most one year per request, so we walk year by year.
Run:  python fetch_data.py
"""
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
BASE = "https://www.niftyindices.com/BackPage/"
INDICES = ["NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 150"]
FIRST_YEAR = 2004
M = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def fmt(d):
    return f"{d.day:02d}-{M[d.month - 1]}-{d.year}"


def get(endpoint, name, start, end):
    cinfo = "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}" % (name, start, end, name)
    req = urllib.request.Request(
        BASE + endpoint,
        data=json.dumps({"cinfo": cinfo}).encode(),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36",
            "Origin": "https://www.niftyindices.com",
            "Referer": "https://www.niftyindices.com/reports/historical-data",
        },
    )
    j = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return json.loads(j["d"]) if isinstance(j, dict) and "d" in j else j


def parse(s):
    return dt.datetime.strptime(s, "%d %b %Y").date()


def main():
    (HERE / "data").mkdir(exist_ok=True)
    for name in INDICES:
        px, tri = {}, {}
        for y in range(FIRST_YEAR, dt.date.today().year + 1):
            s, e = fmt(dt.date(y, 1, 1)), fmt(dt.date(y, 12, 31))
            for r in get("getHistoricaldatatabletoString", name, s, e):
                px[parse(r["HistoricalDate"])] = float(r["CLOSE"])
            for r in get("getTotalReturnIndexString", name, s, e):
                tri[parse(r["Date"])] = float(r["TotalReturnsIndex"])
        out = HERE / "data" / (name.replace(" ", "_") + ".csv")
        with open(out, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "close", "tri"])
            for d in sorted(px):
                w.writerow([d, px[d], tri.get(d, "")])
        print(f"{out.name}: {len(px)} days, {min(px)} to {max(px)}")


if __name__ == "__main__":
    main()
