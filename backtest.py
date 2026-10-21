"""
SIP vs 200-DMA switching backtest on Nifty 50, Nifty Next 50, Nifty Midcap 150.

Data: NSE Indices (niftyindices.com) daily close + Total Return Index, in ./data.
Run:  python backtest.py            -> writes results.json
"""
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SIP = 100_000                 # ₹1 lakh per month
FD_RATE = 0.06                # 6% p.a. effective
SMA_DAYS = 200
END = None                    # None = last date in data

# Tax assumptions (current Indian rules, applied to the whole history as a "what if")
FD_TAX = 0.312                # 30% slab + 4% cess on FD interest
STCG, LTCG, LTCG_EXEMPT = 0.20, 0.125, 125_000

INDICES = {
    "Nifty 50": "NIFTY_50.csv",
    "Nifty Next 50": "NIFTY_NEXT_50.csv",
    "Nifty Midcap 150": "NIFTY_MIDCAP_150.csv",
}


def load(fn):
    df = pd.read_csv(HERE / "data" / fn, parse_dates=["date"]).set_index("date").sort_index()
    df["sma"] = df["close"].rolling(SMA_DAYS).mean()
    # Signal uses the PREVIOUS day's close vs its 200-DMA, so we trade at today's close
    # without look-ahead.
    df["above"] = (df["close"] > df["sma"]).shift(1)
    df.loc[df["sma"].shift(1).isna(), "above"] = pd.NA
    return df


def sip_dates(df, start, n_months):
    """First trading day of each month, starting at `start` month, n_months long."""
    firsts = df.groupby(df.index.to_period("M")).head(1).index
    firsts = firsts[firsts >= pd.Timestamp(start)]
    return list(firsts[:n_months])


def fy(d):
    return d.year if d.month >= 4 else d.year - 1


def xirr(flows):
    """flows: list of (date, amount). Bisection on NPV."""
    t0 = flows[0][0]
    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365.0) for d, a in flows)
    lo, hi = -0.99, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


class Lots:
    """FIFO equity lots for capital-gains tax."""
    def __init__(self):
        self.lots = []          # [date, units, cost]
        self.exempt_used = {}   # FY -> LTCG exemption used

    def buy(self, d, units, cost):
        self.lots.append([d, units, cost])

    def sell_all_tax(self, d, price):
        st = lt = 0.0
        for ld, u, c in self.lots:
            g = u * price - c
            if (d - ld).days > 365:
                lt += g
            else:
                st += g
        self.lots = []
        if st < 0:
            lt += st
            st = 0
        lt = max(lt, 0)
        y = fy(d)
        ex = min(lt, LTCG_EXEMPT - self.exempt_used.get(y, 0))
        self.exempt_used[y] = self.exempt_used.get(y, 0) + ex
        return st * STCG + (lt - ex) * LTCG


def run(df, dates, strategy, col="tri", taxed=False, end=None):
    """
    strategy:
      'sip'    – invest ₹1L every month, always.
      'switch' – (Strategy 2) on each SIP date: index above 200-DMA -> everything in index
                 (move any FD balance in) + ₹1L; below -> sell everything to FD + ₹1L to FD.
      'divert' – (Strategy 2, gentler reading) only the new ₹1L goes to FD while below the
                 200-DMA; existing units are never sold. FD pile is moved into the index
                 when it's back above.
      'fd'     – everything in FD (benchmark).
    """
    end = end or df.index[-1]
    fd_r = FD_RATE * (1 - FD_TAX) if taxed else FD_RATE
    days = df.loc[dates[0]:end]
    sipset = set(dates)
    idx = days.index
    px = days[col].to_numpy()
    abv = days["above"].to_numpy()
    units = fd = 0.0
    lots = Lots()
    nav, prev_v = 1.0, None
    peak, mdd = 1.0, 0.0
    flows, curve = [], []
    months_in, exits, tax_paid = 0, 0, 0.0
    last = None
    for i, d in enumerate(idx):
        p = px[i]
        if last is not None:
            fd *= (1 + fd_r) ** ((d - last).days / 365.0)
        last = d
        cf = 0.0
        if d in sipset:
            cf = SIP
            flows.append((d, -SIP))
            above = bool(abv[i]) if strategy in ("switch", "divert") else True
            if strategy == "fd":
                fd += SIP
            elif strategy == "sip" or above:
                amt = SIP + fd
                lots.buy(d, amt / p, amt)
                units += amt / p
                fd = 0.0
                months_in += 1
            else:  # below 200-DMA
                if strategy == "switch" and units > 0:
                    proceeds = units * p
                    if taxed:
                        t = lots.sell_all_tax(d, p)
                        tax_paid += t
                        proceeds -= t
                    else:
                        lots.lots = []
                    fd += proceeds
                    units = 0.0
                    exits += 1
                fd += SIP
        v = units * p + fd
        if prev_v:
            nav *= (v - cf) / prev_v
        prev_v = v
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        curve.append((d, v))
    final = units * px[-1] + fd
    if taxed and units > 0:
        t = lots.sell_all_tax(idx[-1], px[-1])
        tax_paid += t
        final -= t
    flows.append((idx[-1], final))
    invested = SIP * len(dates)
    return {
        "invested": invested,
        "final": final,
        "multiple": final / invested,
        "xirr": xirr(flows),
        "max_dd": mdd,
        "months_in_equity": months_in,
        "months": len(dates),
        "exits": exits,
        "tax_paid": tax_paid,
        "curve": curve,
    }


def monthly(curve):
    s = pd.Series(dict(curve))
    s = s.groupby(s.index.to_period("M")).last()
    return [[str(k), round(v)] for k, v in s.items()]


def main():
    out = {"meta": {}, "periods": {}, "rolling": {}, "signal": {}}
    strategies = ["sip", "switch", "divert", "fd"]
    for name, fn in INDICES.items():
        df = load(fn)
        end = df.index[-1]
        out["meta"][name] = {"first": str(df.index[0].date()), "last": str(end.date())}

        # --- fixed lookbacks ending today ---
        for yrs in (10, 15, 20):
            start = date(end.year - yrs, end.month, 1) + pd.offsets.MonthBegin(1)
            ds = sip_dates(df, start, yrs * 12)
            res = {}
            for basis in ("tri", "close"):
                for taxed in (False, True):
                    for s in strategies:
                        r = run(df, ds, s, col=basis, taxed=taxed)
                        key = f"{s}|{basis}|{'tax' if taxed else 'pre'}"
                        if basis == "tri" and not taxed:
                            r["curve"] = monthly(r["curve"])
                        else:
                            r.pop("curve")
                        res[key] = r
            res["start"] = str(ds[0].date())
            out["periods"].setdefault(name, {})[yrs] = res

        # --- rolling windows: every possible start month ---
        first_ok = df["above"].first_valid_index()
        firsts = df.groupby(df.index.to_period("M")).head(1).index
        firsts = firsts[firsts >= first_ok]
        for yrs in (5, 10, 15):
            n = yrs * 12
            rows = []
            for i in range(len(firsts) - n):
                ds = list(firsts[i:i + n])
                wend = firsts[i + n] - pd.Timedelta(days=1)
                wend = df.loc[:wend].index[-1]
                r = {s: run(df, ds, s, end=wend)["xirr"] for s in ("sip", "switch", "divert")}
                rows.append([str(ds[0].date())[:7], r["sip"], r["switch"], r["divert"]])
            out["rolling"].setdefault(name, {})[yrs] = rows

        # --- signal chart data (monthly) ---
        m = df.groupby(df.index.to_period("M")).last()
        out["signal"][name] = [[str(k), round(r.close, 2), None if pd.isna(r.sma) else round(r.sma, 2)]
                               for k, r in m.iterrows()]
        # share of trading days above 200-DMA
        a = (df["close"] > df["sma"])[df["sma"].notna()]
        out["meta"][name]["pct_days_above"] = float(a.mean())

    (HERE / "results.json").write_text(json.dumps(out, default=str))

    # console summary
    for name in INDICES:
        print(f"\n=== {name} (TRI, pre-tax) ===")
        for yrs in (10, 15, 20):
            r = out["periods"][name][yrs]
            line = f"{yrs}y from {r['start']}: "
            for s in strategies:
                x = r[f"{s}|tri|pre"]
                line += f"{s}: ₹{x['final']/1e7:.2f}Cr {x['xirr']*100:.1f}% dd{x['max_dd']*100:.0f}% | "
            print(line)
            x = r["switch|tri|pre"]
            print(f"     switch: {x['exits']} exits, in equity {x['months_in_equity']}/{x['months']} months")
            line = "     post-tax: "
            for s in strategies:
                x = r[f"{s}|tri|tax"]
                line += f"{s}: ₹{x['final']/1e7:.2f}Cr {x['xirr']*100:.1f}% | "
            print(line)
        for yrs in (10, 15):
            rows = out["rolling"][name][yrs]
            w = sum(1 for r in rows if r[2] > r[1])
            w2 = sum(1 for r in rows if r[3] > r[1])
            print(f"  rolling {yrs}y ({len(rows)} windows): switch beat SIP {w}, divert beat SIP {w2}")


if __name__ == "__main__":
    main()
