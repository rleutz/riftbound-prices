# Riftbound Prices

Automated daily price updates for the Riftbound Collection Tracker.

## How it works

- **GitHub Actions** runs `scripts/fetch_prices.py` every day at 5:00 PM Eastern
- The script fetches TCGPlayer market prices via [TCGCSV](https://tcgcsv.com) (free, no API key needed)
- Updated prices are committed back to this repo as `prices/riftbound_prices_updated.json`
- The tracker loads prices from this file's public raw URL on startup

## Price data URL

The tracker fetches prices from:

```
https://raw.githubusercontent.com/rleutz/riftbound-prices/main/prices/riftbound_prices_updated.json
```

## Sets tracked

| Code | Set | Type |
|------|-----|------|
| OGN | Origins | Main |
| OGS | Origins: Proving Grounds | Main |
| SFD | Spiritforged | Main |
| UNL | Unleashed | Main |
| VEN | Vendetta | Main |
| RAD | Radiance | Main (upcoming) |
| LGC | Legacy | Main (upcoming) |
| JDG | Judge Promotional Cards | Promo |
| OPP | Organized Play Promotional Cards | Promo |
| PR | Promotional Cards | Promo |
| RWB | Worlds Bundle 2025 | Promo |
| SGN | Secret Garden | Promo |

Promo sets have prices tracked but no completion progress in the tracker.

## New set detection

When the script detects a set not in the known lists, it automatically opens a GitHub Issue with instructions on how to add it to the tracker.

## Manual run

To trigger a price update manually:
1. Go to the **Actions** tab in this repo
2. Click **Update Riftbound Prices**
3. Click **Run workflow**

## Data source

Prices come from [TCGCSV](https://tcgcsv.com), which mirrors TCGPlayer market price data daily. TCGPlayer market price reflects actual recent sales, not just listed prices.
