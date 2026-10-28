# Trade Gap Tracker

Where declared mineral exports and partner-recorded imports disagree, across EITI implementing countries, 2010 to present.

**Source:** UN Comtrade, annual merchandise trade statistics (HS), via the [UN Comtrade API](https://comtradeplus.un.org/).

The dashboard makes **no API calls at runtime**. Data is pulled once by `prefetch.py`, written to `data/` as Parquet, and committed to the repo. Open the app and it is ready.

---

## Files

```
app.py                 single-page dashboard, reads the cache only
prefetch.py            parallel Comtrade pull, writes data/
verify.py              diagnostics — run before trusting any headline figure
cache.py               atomic writes, corruption-tolerant reads, cache assembly
comtrade.py            API client, used only by prefetch
gaps.py                gap computation and the written summary
config.py              countries, HS chapters, year range, paths
requirements.txt
.streamlit/config.toml theme
data/raw/              one pull per country, gitignored
data/*.parquet         the published cache, committed
```

Flat by design — no package folder, so there is nothing to get nested wrong.

---

## Part 1 — Run it locally

### 1. Set up

```bash
cd ~/totga
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Get a Comtrade API key

Register at [comtradeplus.un.org](https://comtradeplus.un.org/) and copy your subscription key. The free tier allows 500 calls per day, which is enough for a full run.

```bash
export COMTRADE_API_KEY=your_key_here
```

Keep the key out of the repo. It is only ever used by `prefetch.py`, never by the deployed app.

### 3. Build the cache

```bash
python prefetch.py
```

Roughly 230 API calls for all 59 countries, five in parallel, about 8 minutes. Each country is written the moment it lands.

- **Interrupting is safe.** Writes are atomic. Rerun the same command and it skips what is cached.
- **Big exporters come first** — Philippines, Indonesia, Ghana, Zambia, Peru, DRC.

Other options:

```bash
python prefetch.py 608 360 288     # selected M49 codes
python prefetch.py --workers 2     # back off if the API rate-limits
python prefetch.py --rebuild       # reassemble from existing pulls, no API calls
```

### 4. Verify before trusting anything

```bash
python verify.py 608
```

Checks for duplicate keys, aggregate reporters leaking in, thin reporter coverage in the latest year, how much of the gap sits with partners that were never declared to (origin-based reporting rather than under-declaration), and declared exports against published national statistics.

For the Philippines, declared exports should land near the MGB/PSA mineral export figures of **$7.32bn (2023)** and **$7.38bn (2024)**. If they do, the export side is sound.

### 5. Open it

```bash
streamlit run app.py
```

Goes to `http://localhost:8501`. You can run this while `prefetch.py` is still going — countries appear as they land, and the caption tells you how many are cached.

---

## Part 2 — Push to GitHub

### 1. Confirm what will be committed

```bash
git init
git status
```

`data/raw/` and `venv/` should be excluded by `.gitignore`. The three published files in `data/` — `gaps_country_year.parquet`, `gaps_partner.parquet`, `manifest.json` — **must** be committed, or the deployed app will have nothing to read.

```bash
ls -lh data/*.parquet
```

Expect a few MB total. GitHub warns above 50MB per file and blocks above 100MB; if you exceed that, cut the country or chapter list in `config.py` and rebuild.

### 2. Commit

```bash
git add .
git commit -m "Trade Gap Tracker: UN Comtrade mirror analysis for EITI countries"
```

### 3. Create the repo and push

Create an empty repository on GitHub — no README, no .gitignore, since you already have both. Then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/trade-gap-tracker.git
git branch -M main
git push -u origin main
```

### 4. Check the key is not in the history

```bash
git log -p | grep -i "subscription-key\|COMTRADE_API_KEY=" | grep -v "os.getenv"
```

Should return nothing. If a key appears, rotate it on the Comtrade portal before going public — removing it from the working tree does not remove it from history.

---

## Part 3 — Deploy on Streamlit Community Cloud

### 1. Connect

Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub. Authorise access to the repository.

### 2. Create the app

Click **New app**, then:

| Field | Value |
|---|---|
| Repository | `YOUR_USERNAME/trade-gap-tracker` |
| Branch | `main` |
| Main file path | `app.py` |

### 3. Deploy

Click **Deploy**. First build takes two or three minutes while it installs from `requirements.txt`. You get a URL like `https://trade-gap-tracker.streamlit.app`.

**No secrets are needed.** The API key is only used by `prefetch.py`, which never runs on the server.

### 4. If it fails

- **"No cached dataset found"** — the Parquet files were not committed. Check `git ls-files data/`.
- **Build error on install** — pin the failing package in `requirements.txt` to the version you have locally (`pip freeze | grep <package>`).
- **Memory limits** — Community Cloud allows about 1GB. If the cache is large, drop HS chapters or countries in `config.py` and rebuild.

### 5. Refresh the data later

```bash
rm -rf data/raw
export COMTRADE_API_KEY=your_key
python prefetch.py
python verify.py 608
git add data && git commit -m "Refresh cache" && git push
```

Streamlit Cloud redeploys automatically on push.

---

## What it computes

```
Gap = partner-recorded imports − declared exports
```

A positive gap means partners record receiving more than the exporter declares sending. A negative gap means the reverse.

Only partners that report the matching flow enter the comparison, so headline totals cover less than exports to the world. The coverage share is stated in the dashboard summary.

Self-trade rows and aggregate partner codes — World, the EU bloc (which reports alongside its member states), "Areas, nes", bunkers, free zones and the regional residuals — are removed before anything is computed. They have no mirror counterpart and would otherwise register as a one-sided gap.

No CIF/FOB, entrepôt or timing adjustment is applied. This is the raw gap, kept deliberately transparent — the methodological corrections belong in a paper, not a screening tool.

---

## Scope

- **Countries:** 59 EITI implementing countries — edit `EITI_COUNTRIES` in `config.py`
- **Commodities:** HS 26 (ores), 71 (precious metals), 72–81 (base metals)
- **Years:** 2010 to the latest Comtrade release

HS 71 is included because gold dominates the trade-gap picture for several EITI countries. Drop it from `COMMODITY_GROUPS` for ores and base metals only.

---

## Disclaimer

A trade gap is not evidence of wrongdoing. Origin-versus-destination recording, CIF/FOB valuation, entrepôt routing, year-boundary timing, classification differences and confidentiality suppression all produce discrepancies in the ordinary course of trade, and several are mechanical.

This is a screening tool. It indicates where bilateral statistics disagree and therefore where closer examination may be warranted. Establishing misinvoicing in any particular transaction requires customs investigation and firm-level audit.

Figures inherit any errors, revisions, suppressions and gaps in national reporting to UN Comtrade. The most recent year is typically incomplete. The analysis is independent of, and not endorsed by, the United Nations, UN Comtrade, the EITI or any government.
