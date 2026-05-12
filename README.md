# Thai DR Premium / Discount Dashboard

Local dashboard for comparing Thai-listed DR prices with the implied price of their foreign underlying.

Formula:

```text
Fair DR price = underlying price x FX to THB / DR per 1 underlying share
Implied underlying = DR price x DR per 1 underlying share / FX to THB
Diff % = DR price / Fair DR price - 1
```

## Run

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:8765
```

The first full refresh can take a few minutes because the app confirms DR profiles from SET factsheet pages and caches conversion ratios in `data/cache/dr_profiles.json`.

## GitHub Pages

This project can run online for free as a static GitHub Pages site. GitHub Actions builds `data/dashboard.json` and `data/dashboard.csv` every 10 minutes.

```powershell
python scripts/build_static_data.py
```

The workflow is in `.github/workflows/update-dashboard.yml`.

To publish, create a GitHub repository, push this folder to `main`, then in GitHub go to:

```text
Settings > Pages > Source: GitHub Actions
```

## Data Design

- DR universe and Thai DR last price: StockAnalysis SET list.
- DR profile and true conversion ratio: SET DR factsheet page for each DR symbol.
- Underlying live quote and currency: Yahoo Finance quote endpoint.
- FX to THB: Yahoo Finance FX pairs such as `USDTHB=X`, `HKDTHB=X`, `JPYTHB=X`.
- Manual mapping for non-US or unusual underlying symbols: `data/underlying_map.csv`.

## Future New DR

Click `Refresh` to scan the SET symbol universe again. If a new symbol looks like a DR, the app fetches its SET factsheet; if SET confirms `securityType = X` and provides a conversion ratio, it appears in the dashboard.

If a new DR's underlying ticker cannot be resolved on Yahoo Finance, add one row to `data/underlying_map.csv`:

```csv
set_underlying,dr_symbol,yahoo_symbol,note
TENCENT,,0700.HK,Tencent Hong Kong
```

Use `dr_symbol` only when the mapping differs by issuer-specific DR symbol. Otherwise mapping by `set_underlying` is cleaner.
