import time
import requests
import pandas as pd

from config import API_BASE, API_KEY, REQUEST_DELAY

FIELDS = {
    "refYear": "year",
    "reporterCode": "reporter",
    "reporterDesc": "reporter_name",
    "partnerCode": "partner",
    "partnerDesc": "partner_name",
    "cmdCode": "commodity",
    "primaryValue": "value",
    "netWgt": "weight",
}


class ComtradeError(Exception):
    pass


def _get(params, retries=4):
    params = dict(params)
    params["subscription-key"] = API_KEY

    for attempt in range(retries):
        try:
            r = requests.get(API_BASE, params=params, timeout=90)
        except requests.exceptions.RequestException as e:
            time.sleep(REQUEST_DELAY * (attempt + 1))
            if attempt == retries - 1:
                raise ComtradeError(str(e))
            continue

        if r.status_code == 200:
            payload = r.json()
            return payload.get("data") or []
        if r.status_code == 429:
            time.sleep(30 * (attempt + 1))
            continue
        if r.status_code in (500, 502, 503, 504):
            time.sleep(10 * (attempt + 1))
            continue
        raise ComtradeError(f"HTTP {r.status_code}: {r.text[:200]}")

    raise ComtradeError("exhausted retries")


def _frame(rows):
    if not rows:
        return pd.DataFrame(columns=list(FIELDS.values()))

    df = pd.DataFrame(rows)
    df = df[[c for c in FIELDS if c in df.columns]].rename(columns=FIELDS)

    for col in ("value", "weight"):
        df[col] = pd.to_numeric(df.get(col), errors="coerce").fillna(0)

    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    for col in ("reporter", "partner"):
        df[col] = df[col].astype(str).str.zfill(3)
    df["commodity"] = df["commodity"].astype(str)
    for col in ("reporter_name", "partner_name"):
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    df = df.dropna(subset=["year"])

    # Comtrade can return several rows per key (quantity units, sub-breakdowns).
    # Collapse them, or the mirror merge fans out and inflates both sides.
    keys = ["year", "reporter", "partner", "commodity"]
    return df.groupby(keys, as_index=False).agg(
        reporter_name=("reporter_name", "first"),
        partner_name=("partner_name", "first"),
        value=("value", "sum"),
        weight=("weight", "sum"),
    )


def exports_by_partner(country, commodities, years):
    """What `country` declares exporting, broken down by destination."""
    rows = _get({
        "reporterCode": country,
        "cmdCode": ",".join(commodities),
        "flowCode": "X",
        "period": ",".join(str(y) for y in years),
        "partner2Code": 0,
        "customsCode": "C00",
        "motCode": 0,
        "includeDesc": "true",
    })
    return _frame(rows)


def mirror_imports(country, commodities, years):
    """What every reporting partner declares importing from `country`."""
    rows = _get({
        "partnerCode": country,
        "cmdCode": ",".join(commodities),
        "flowCode": "M",
        "period": ",".join(str(y) for y in years),
        "partner2Code": 0,
        "customsCode": "C00",
        "motCode": 0,
        "includeDesc": "true",
    })
    return _frame(rows)
