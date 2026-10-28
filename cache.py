import json
import os
from datetime import datetime, timezone

import pandas as pd

import gaps
from config import AGGREGATE_FILE, DATA_DIR, MANIFEST_FILE, PARTNER_FILE, RAW_DIR


def write_atomic(df, path):
    """Write via a temp file and rename, so an interrupted run never leaves a corrupt parquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def read_safe(path):
    """Return None instead of raising on a truncated or unreadable file, and clear it."""
    try:
        return pd.read_parquet(path)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        return None


def cached_countries():
    if not RAW_DIR.exists():
        return []
    return sorted(
        p.stem for p in RAW_DIR.glob("*.parquet")
        if not p.stem.endswith("_world") and not p.name.endswith(".tmp")
    )


def build_from_raw():
    """Assemble the dashboard tables from whatever country pulls exist. No API calls."""
    partners, world = [], []

    for code in cached_countries():
        p = read_safe(RAW_DIR / f"{code}.parquet")
        if p is None or p.empty:
            continue
        partners.append(p)

        w = read_safe(RAW_DIR / f"{code}_world.parquet")
        if w is not None and not w.empty:
            world.append(w)

    if not partners:
        return None, None, {}

    partners = pd.concat(partners, ignore_index=True)
    world = (
        pd.concat(world, ignore_index=True) if world
        else pd.DataFrame(columns=["country", "year", "commodity", "exports_world"])
    )
    aggregate = gaps.aggregate(partners, world)

    manifest = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "countries": sorted(aggregate["country"].unique().tolist()),
        "years": [int(aggregate.year.min()), int(aggregate.year.max())],
        "commodities": sorted(aggregate["commodity"].unique().tolist()),
        "partner_rows": len(partners),
        "aggregate_rows": len(aggregate),
    }
    return aggregate, partners, manifest


def publish():
    aggregate, partners, manifest = build_from_raw()
    if aggregate is None:
        return None

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_atomic(partners, PARTNER_FILE)
    write_atomic(aggregate, AGGREGATE_FILE)
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))
    return manifest


def load():
    """Published tables if they exist, otherwise assemble live from partial raw pulls."""
    aggregate = read_safe(AGGREGATE_FILE) if AGGREGATE_FILE.exists() else None
    partners = read_safe(PARTNER_FILE) if PARTNER_FILE.exists() else None

    if aggregate is not None and partners is not None:
        manifest = {}
        if MANIFEST_FILE.exists():
            try:
                manifest = json.loads(MANIFEST_FILE.read_text())
            except json.JSONDecodeError:
                pass
        manifest["partial"] = False
        return aggregate, partners, manifest

    aggregate, partners, manifest = build_from_raw()
    if aggregate is None:
        return None, None, {}

    manifest["partial"] = True
    return aggregate, partners, manifest
