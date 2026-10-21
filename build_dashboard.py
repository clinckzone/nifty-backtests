"""
Bake results.json into a single self-contained dashboard.html.

The page loads d3 from cdnjs and carries all data inline, so it opens straight
from disk (file://) or from GitHub Pages without a server.
Run:  python build_dashboard.py      (after backtest.py)
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
NAMES = {"sip": "Monthly SIP", "switch": "200-DMA switch", "divert": "200-DMA divert", "fd": "FD only"}


def flatten(R):
    summary, curves, rolling, signal = [], [], [], []
    for ix, per in R["periods"].items():
        for yrs, res in per.items():
            for k, r in res.items():
                if k == "start":
                    continue
                s, basis, tax = k.split("|")
                summary.append({
                    "id": f"{ix}|{yrs}|{s}|{basis}|{tax}", "index": ix, "years": int(yrs), "start": res["start"],
                    "strategy": s, "strategy_name": NAMES[s], "basis": basis, "tax": tax,
                    "invested": r["invested"], "final": round(r["final"]), "multiple": round(r["multiple"], 4),
                    "xirr": round(r["xirr"], 5), "max_dd": round(r["max_dd"], 4),
                    "months_in_equity": r["months_in_equity"], "months": r["months"],
                    "exits": r["exits"], "tax_paid": round(r["tax_paid"]),
                })
            cs = {s: dict(res[f"{s}|tri|pre"]["curve"]) for s in NAMES}
            for i, m in enumerate(cs["sip"]):
                curves.append({"index": ix, "years": int(yrs), "month": m, "invested": 100000 * (i + 1),
                               **{s: cs[s][m] for s in NAMES}})
    for ix, per in R["rolling"].items():
        for yrs, rows in per.items():
            for st, a, b, c in rows:
                rolling.append({"index": ix, "years": int(yrs), "start": st,
                                "sip": round(a, 5), "switch": round(b, 5), "divert": round(c, 5)})
    for ix, rows in R["signal"].items():
        for m, c, s in rows:
            signal.append({"index": ix, "month": m, "close": c, "sma200": s})
    return {"summary": summary, "curves": curves, "rolling": rolling, "signal": signal,
            "asof": max(v["last"] for v in R["meta"].values())}


def main():
    R = json.loads((HERE / "results.json").read_text())
    data = json.dumps(flatten(R), separators=(",", ":")).replace("</", "<\\/")
    tpl = (HERE / "dashboard" / "template.html").read_text()
    out = tpl.replace("/*__DATA__*/{}", data)
    (HERE / "dashboard.html").write_text(out)
    print(f"dashboard.html: {len(out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
