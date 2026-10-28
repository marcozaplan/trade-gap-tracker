"""Stress-test the cached figures before trusting any headline number.

    python verify.py            Philippines
    python verify.py 288 894    other M49 codes

Checks, in order: duplicate keys, aggregate reporters leaking in, reporter
coverage by year, where the mirror excess actually sits, and declared exports
against the national statistics you can look up independently.
"""

import sys

import pandas as pd

import cache
import gaps
from config import AGGREGATE_PARTNERS, COMMODITY_GROUPS, EITI_COUNTRIES

pd.set_option("display.width", 140)


def usd(x):
    return gaps.usd(x)


def check_duplicates(partners):
    keys = ["country", "year", "commodity", "counterpart"]
    dupes = partners.duplicated(subset=keys).sum()
    print(f"\n1. Duplicate keys: {dupes:,}")
    if dupes:
        print("   PROBLEM — the merge fanned out. Refetch with the current comtrade.py.")
    else:
        print("   Clean. One row per country-year-commodity-partner.")


def check_aggregates(partners):
    leaked = sorted(set(partners["counterpart"]) & AGGREGATE_PARTNERS)
    print(f"\n2. Aggregate partner codes present: {leaked or 'none'}")
    if leaked:
        names = (
            partners[partners["counterpart"].isin(leaked)]
            .groupby("counterpart_name")["mirror"].sum().sort_values(ascending=False)
        )
        for name, value in names.items():
            print(f"   {name}: {usd(value)} of mirror imports — should be excluded")


def check_year_coverage(partners, country):
    print("\n3. Reporters per year (a thin latest year means incomplete data)")
    sub = partners[(partners["country"] == country) & (partners["mirror"] > 0)]
    counts = sub.groupby("year")["counterpart"].nunique()
    median = counts.median()
    for year, n in counts.items():
        flag = "  <-- thin" if n < median * 0.75 else ""
        print(f"   {year}: {n:3d} reporters{flag}")


def check_mirror_excess(partners, country):
    """Where does the mirror exceed declared exports, and is it entrepot-shaped?"""
    sub = partners[partners["country"] == country]
    by_partner = (
        sub.groupby("counterpart_name", as_index=False)
        .agg(exports=("exports", "sum"), mirror=("mirror", "sum"))
    )
    by_partner["gap"] = by_partner["mirror"] - by_partner["exports"]

    total_gap = by_partner["gap"].sum()
    print(f"\n4. Mirror excess: {usd(total_gap)} total")

    positive = by_partner[by_partner["gap"] > 0].sort_values("gap", ascending=False)
    print("\n   Partners recording more than was declared to them:")
    for _, r in positive.head(10).iterrows():
        share = r["gap"] / total_gap * 100 if total_gap else 0
        ratio = r["mirror"] / r["exports"] if r["exports"] else float("inf")
        note = ""
        if r["exports"] == 0:
            note = "  <-- no declared exports at all"
        elif ratio > 3:
            note = f"  <-- {ratio:.1f}x declared, worth a closer look"
        print(f"   {r['counterpart_name']:<28} {usd(r['gap']):>12}  {share:5.1f}%{note}")

    orphans = positive[positive["exports"] == 0]["gap"].sum()
    if total_gap:
        print(f"\n   {usd(orphans)} ({orphans / total_gap * 100:.0f}%) of the excess sits with "
              "partners the country declared no exports to at all.")
        print("   That is one data point among several relevant to interpreting the gap —")
        print("   see the Methodology section in the app for the range of factors that")
        print("   can produce a bilateral discrepancy. A low share here does not rule any")
        print("   of them in or out.")


def check_against_benchmark(aggregate, country):
    print("\n5. Declared exports by year — check these against national statistics")
    sub = aggregate[aggregate["country"] == country]
    by_year = sub.groupby("year", as_index=False).agg(
        exports=("exports", "sum"), mirror=("mirror", "sum")
    )
    by_year["ratio"] = by_year["mirror"] / by_year["exports"]
    for _, r in by_year.iterrows():
        print(f"   {int(r.year)}  declared {usd(r.exports):>10}   "
              f"mirror {usd(r.mirror):>10}   mirror/declared {r.ratio:.2f}x")

    if country == "608":
        print("\n   Philippine benchmark (MGB/PSA mineral exports):")
        print("     2023: $7.32bn      2024: $7.38bn")
        print("   Declared should land near these. The mirror column should not be")
        print("   read as the 'true' figure — see check 4.")


def check_commodities(aggregate, country):
    print("\n6. Gap by commodity")
    sub = gaps.collapse_commodities(aggregate[aggregate["country"] == country])
    for _, r in sub.iterrows():
        print(f"   HS {r.commodity} {COMMODITY_GROUPS.get(r.commodity, ''):<28} "
              f"{usd(r.gap):>12}  {r.gap_pct:+7.1f}%")
    print("\n   Chapters 71 (precious metals) and 74/75 routed through refining or")
    print("   trading hubs will show the largest origin-based inflation.")


def main():
    aggregate, partners, manifest = cache.load()
    if aggregate is None:
        sys.exit("No cache. Run prefetch.py first.")

    countries = sys.argv[1:] or ["608"]

    print(f"Cache: {len(manifest.get('countries', []))} countries, "
          f"{manifest.get('partner_rows', 0):,} partner rows, "
          f"built {manifest.get('built', '?')[:10]}")

    check_duplicates(partners)
    check_aggregates(partners)

    for country in countries:
        name = EITI_COUNTRIES.get(country, country)
        print("\n" + "=" * 70)
        print(name)
        print("=" * 70)
        check_year_coverage(partners, country)
        check_mirror_excess(partners, country)
        check_against_benchmark(aggregate, country)
        check_commodities(aggregate, country)


if __name__ == "__main__":
    main()
