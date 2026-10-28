"""Pull Comtrade bilateral flows and build the cache the dashboard reads.

    export COMTRADE_API_KEY=...

    python prefetch.py                  all EITI countries, priority order
    python prefetch.py 608 360 288      selected M49 codes
    python prefetch.py --workers 2      fewer threads if the API pushes back
    python prefetch.py --rebuild        reassemble from existing pulls, no API calls

Each country is written as soon as it lands, so the dashboard is usable while the
rest is still running. Reruns skip whatever is already cached.
"""

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import cache
import comtrade
import gaps
from config import (
    COMMODITY_GROUPS,
    EITI_COUNTRIES,
    END_YEAR,
    PERIOD_CHUNK,
    RAW_DIR,
    START_YEAR,
)

YEARS = list(range(START_YEAR, END_YEAR + 1))
CHUNKS = [YEARS[i:i + PERIOD_CHUNK] for i in range(0, len(YEARS), PERIOD_CHUNK)]
CODES = list(COMMODITY_GROUPS)

# Big mineral exporters first, so the dashboard has something worth looking at early
PRIORITY = [
    "608", "360", "288", "894", "604", "180", "398", "496", "854", "324",
    "566", "152", "484", "170", "834", "800", "120", "384", "450", "508",
]

print_lock = threading.Lock()


def log(msg):
    with print_lock:
        print(msg, flush=True)


def pull(code, name):
    raw_path = RAW_DIR / f"{code}.parquet"
    if raw_path.exists():
        return code, name, "cached", 0.0

    started = time.monotonic()
    exports, mirrors = [], []
    for chunk in CHUNKS:
        exports.append(comtrade.exports_by_partner(code, CODES, chunk))
        mirrors.append(comtrade.mirror_imports(code, CODES, chunk))

    exports = pd.concat(exports, ignore_index=True)
    mirrors = pd.concat(mirrors, ignore_index=True)

    if exports.empty and mirrors.empty:
        return code, name, "no data", time.monotonic() - started

    partner_gaps = gaps.build_partner_gaps(exports, mirrors, code)
    cache.write_atomic(partner_gaps, raw_path)
    cache.write_atomic(gaps.world_totals(exports, code), RAW_DIR / f"{code}_world.parquet")

    return code, name, len(partner_gaps), time.monotonic() - started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("countries", nargs="*")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    if args.rebuild:
        manifest = cache.publish()
        if not manifest:
            sys.exit("no country pulls found in data/raw")
        print(f"Rebuilt from {len(manifest['countries'])} countries, "
              f"{manifest['partner_rows']:,} partner rows")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.countries:
        wanted = args.countries
        unknown = [c for c in wanted if c not in EITI_COUNTRIES]
        if unknown:
            sys.exit(f"unknown country codes: {unknown}")
    else:
        rest = [c for c in EITI_COUNTRIES if c not in PRIORITY]
        wanted = [c for c in PRIORITY if c in EITI_COUNTRIES] + rest

    todo = [c for c in wanted if not (RAW_DIR / f"{c}.parquet").exists()]
    done = len(wanted) - len(todo)

    print(f"{len(wanted)} countries, {START_YEAR}-{END_YEAR}, {len(CODES)} HS chapters")
    print(f"{done} already cached, {len(todo)} to fetch, {args.workers} workers\n")

    if not todo:
        print("Nothing to fetch.")
    else:
        started = time.monotonic()
        finished = 0

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(pull, c, EITI_COUNTRIES[c]): c for c in todo}
            try:
                for future in as_completed(futures):
                    finished += 1
                    try:
                        _, name, rows, secs = future.result()
                    except Exception as e:
                        log(f"  [{finished}/{len(todo)}] "
                            f"{EITI_COUNTRIES[futures[future]]}: failed — {e}")
                        continue

                    elapsed = time.monotonic() - started
                    eta = elapsed / finished * (len(todo) - finished)
                    detail = f"{rows:,} rows" if isinstance(rows, int) else rows
                    log(f"  [{finished}/{len(todo)}] {name}: {detail} "
                        f"({secs:.0f}s, ~{eta / 60:.0f}m left)")
            except KeyboardInterrupt:
                log("\nStopping. Completed countries are saved — rerun to continue.")
                pool.shutdown(wait=False, cancel_futures=True)

    manifest = cache.publish()
    if not manifest:
        sys.exit("\nNo usable data. Check COMTRADE_API_KEY and try one country first.")

    print(f"\nCache: {len(manifest['countries'])} countries, "
          f"{manifest['aggregate_rows']:,} country-year-commodity rows, "
          f"{manifest['partner_rows']:,} partner rows")


if __name__ == "__main__":
    main()
