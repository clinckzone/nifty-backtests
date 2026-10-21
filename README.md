# Nifty backtests

Backtests of monthly investing strategies on **Nifty 50**, **Nifty Next 50** and **Nifty Midcap 150**, using daily data from NSE Indices.

Open [`index.html`](index.html) in a browser to explore the results. It is a single static file with the data embedded, so it works straight from disk or on GitHub Pages (Settings → Pages → deploy from the `main` branch, root folder).

## Strategies tested

All strategies invest ₹1 lakh on the first trading day of every month.

| Strategy | Rule |
|---|---|
| Monthly SIP | Invest in the index every month, always. |
| 200-DMA switch | Above the 200-day average: everything in the index. Below it: sell the whole portfolio into a 6% FD and keep adding to the FD until the index is back above, then move it all back. |
| 200-DMA divert | Never sell. While the index is below its 200-day average, only the new ₹1 lakh goes to the FD; the FD balance moves into the index once it is back above. |
| FD only | Benchmark: everything in a 6% FD. |

Each is run over the last 10, 15 and 20 years, on the Total Return Index (with dividends) and the price index, before and after tax. A rolling-window study tests every possible 5, 10 and 15-year start month.

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python fetch_data.py       # refresh data/ from niftyindices.com (optional; data is committed)
python backtest.py         # writes results.json and prints a summary
python build_dashboard.py  # bakes results.json into index.html
```

Settings such as the SIP amount, FD rate and tax rates are constants at the top of `backtest.py`.

## Method

- **Data:** daily close and Total Return Index from [NSE Indices](https://www.niftyindices.com/reports/historical-data). Nifty 50 and Next 50 from 2004; Nifty Midcap 150 from its April 2005 launch.
- **Signal:** 200-trading-day simple average of the price index, read from the previous day's close and acted on at that day's close, so there is no look-ahead. The rule is checked only on investment days.
- **FD:** 6% a year, compounded daily.
- **Tax (post-tax view):** today's rules applied to the whole history as a what-if. Equity: 20% short-term, 12.5% long-term with ₹1.25 lakh exempt per financial year. FD interest at 31.2%. Post-tax values assume everything is sold on the last day.
- **Not modelled:** fund expense ratio, tracking error, exit loads, stamp duty.
- **Drawdown:** measured on time-weighted unit value, so new contributions do not mask falls.

## Layout

```
data/                  NSE daily data, one CSV per index (date, close, tri)
fetch_data.py          downloads data/
backtest.py            strategy engine, writes results.json
build_dashboard.py     results.json + dashboard/template.html -> index.html
dashboard/template.html
index.html             generated dashboard, committed so it works on GitHub Pages
```

## Adding a strategy

1. Add a branch for it in `run()` in `backtest.py` and include its key in the `strategies` list in `main()`.
2. Add it to `NAMES` in `build_dashboard.py` and to `STRATS` in `dashboard/template.html` (each entry takes the next series color).
3. Re-run `backtest.py` and `build_dashboard.py`.
