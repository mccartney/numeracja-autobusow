# Numeracja autobusów WTP (ZTM Warszawa)

**Live: https://mccartney.github.io/numeracja-autobusow/**

A single 2D grid of Warsaw's main bus fleet (MZA, Mobilis, PKS Grodzisk, ReloBus;
numbers 1000–9999). Columns are the number prefixes `10xx`–`99xx` grouped by
carrier, rows are the suffixes `00`–`99`, and each cell is coloured by a hash of
(producent, typ). Data comes from the
[ZTM vehicle database](https://www.ztm.waw.pl/baza-danych-pojazdow/?ztm_traction=1).

## Build locally

```
python3 build.py
```

Writes `numeracja.html` (the grid) and `vehicles.json` (raw scrape). Only the
Python standard library is required. Fetched pages are cached under `.cache/`.

## Publishing

`.github/workflows/publish.yml` rebuilds and deploys to GitHub Pages daily and on
every push to `main`. The raw data is also served at
[`vehicles.json`](https://mccartney.github.io/numeracja-autobusow/vehicles.json).
