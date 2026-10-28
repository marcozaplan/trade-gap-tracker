import numpy as np
import pandas as pd

from config import AGGREGATE_PARTNERS, ANOMALY_THRESHOLD, COMMODITY_GROUPS


def build_partner_gaps(exports, mirrors, country):
    """Match declared exports against partner-declared imports, partner by partner."""
    drop = AGGREGATE_PARTNERS | {country}
    ex = exports[~exports["partner"].isin(drop)].copy()
    ex = ex.rename(columns={
        "partner": "counterpart", "partner_name": "counterpart_name",
        "value": "exports", "weight": "exports_kg",
    })
    ex = ex[["year", "commodity", "counterpart", "counterpart_name", "exports", "exports_kg"]]

    mirrors = mirrors[~mirrors["reporter"].isin(drop)]
    im = mirrors.rename(columns={
        "reporter": "counterpart", "reporter_name": "counterpart_name",
        "value": "mirror", "weight": "mirror_kg",
    })
    im = im[["year", "commodity", "counterpart", "counterpart_name", "mirror", "mirror_kg"]]

    merged = ex.merge(
        im, on=["year", "commodity", "counterpart"], how="outer", suffixes=("", "_im")
    )
    merged["counterpart_name"] = (
        merged["counterpart_name"].replace("", pd.NA)
        .fillna(merged.pop("counterpart_name_im"))
        .fillna(merged["counterpart"])
    )
    numeric = ["exports", "exports_kg", "mirror", "mirror_kg"]
    merged[numeric] = merged[numeric].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    merged["country"] = country
    merged["gap"] = merged["mirror"] - merged["exports"]
    merged["year"] = merged["year"].astype(int)
    return merged


def world_totals(exports, country):
    """Declared exports to the world, used to express mirror coverage."""
    world = exports[exports["partner"] == "000"].copy()
    world = world.rename(columns={"value": "exports_world"})
    world["country"] = country
    world["year"] = world["year"].astype(int)
    return world[["country", "year", "commodity", "exports_world"]]


def aggregate(partner_gaps, world):
    agg = partner_gaps.groupby(["country", "year", "commodity"], as_index=False).agg(
        exports=("exports", "sum"),
        mirror=("mirror", "sum"),
        exports_kg=("exports_kg", "sum"),
        mirror_kg=("mirror_kg", "sum"),
    )
    agg = agg.merge(world, on=["country", "year", "commodity"], how="left")

    agg["gap"] = agg["mirror"] - agg["exports"]
    agg["gap_pct"] = np.where(agg["exports"] > 0, agg["gap"] / agg["exports"] * 100, 0)
    agg["coverage_pct"] = np.where(
        agg["exports_world"].notna() & (agg["exports_world"] > 0),
        agg["exports"] / agg["exports_world"] * 100,
        np.nan,
    )
    agg["anomaly"] = agg["gap_pct"].abs() > ANOMALY_THRESHOLD
    return agg


def filter_scope(df, country, commodity):
    out = df[df["country"] == country]
    if commodity != "ALL":
        out = out[out["commodity"] == commodity]
    return out


def collapse_years(df):
    out = df.groupby("year", as_index=False).agg(
        exports=("exports", "sum"),
        mirror=("mirror", "sum"),
        exports_world=("exports_world", "sum"),
    )
    out.loc[out["exports_world"] <= 0, "exports_world"] = np.nan
    out["gap"] = out["mirror"] - out["exports"]
    out["gap_pct"] = np.where(out["exports"] > 0, out["gap"] / out["exports"] * 100, 0)
    out["coverage_pct"] = np.where(
        out["exports_world"] > 0, out["exports"] / out["exports_world"] * 100, np.nan
    )
    return out.sort_values("year")


def collapse_partners(df, top=None):
    out = df.groupby(["counterpart", "counterpart_name"], as_index=False).agg(
        exports=("exports", "sum"),
        mirror=("mirror", "sum"),
        gap=("gap", "sum"),
    )
    out["gap_pct"] = np.where(out["exports"] > 0, out["gap"] / out["exports"] * 100, 0)
    out = out.sort_values("gap", ascending=False).reset_index(drop=True)
    return out.head(top) if top else out


def collapse_commodities(df):
    out = df.groupby("commodity", as_index=False).agg(
        exports=("exports", "sum"),
        mirror=("mirror", "sum"),
    )
    out["gap"] = out["mirror"] - out["exports"]
    out["gap_pct"] = np.where(out["exports"] > 0, out["gap"] / out["exports"] * 100, 0)
    out["label"] = out["commodity"].map(lambda c: COMMODITY_GROUPS.get(c, f"HS {c}"))
    return out.sort_values("gap", ascending=False).reset_index(drop=True)


def trend_direction(series):
    valid = series.dropna().abs()
    if len(valid) < 3:
        return "flat", 0.0
    x = np.arange(len(valid))
    slope = np.polyfit(x, valid.values, 1)[0]
    if abs(slope) < 0.5:
        return "flat", slope
    return ("widening" if slope > 0 else "narrowing"), slope


def narrate(by_year, by_partner, country_name, commodity_label):
    if by_year.empty:
        return "No matched bilateral flows are available for this selection."

    total_ex = by_year["exports"].sum()
    total_mirror = by_year["mirror"].sum()
    total_gap = total_mirror - total_ex
    pct = (total_gap / total_ex * 100) if total_ex else 0
    first, last = int(by_year.year.min()), int(by_year.year.max())

    direction, _ = trend_direction(by_year["gap_pct"])
    worst = by_year.loc[by_year["gap_pct"].abs().idxmax()]

    if total_gap > 0:
        reading = (
            f"Over this period, partners recorded receiving more than {country_name} "
            "declared sending. See the methodology below for the range of factors that "
            "can produce this."
        )
    elif total_gap < 0:
        reading = (
            f"Over this period, {country_name} declared sending more than partners "
            "recorded receiving. See the methodology below for the range of factors that "
            "can produce this."
        )
    else:
        reading = "Declared exports and partner-recorded imports are closely aligned."

    lines = [
        f"Between {first} and {last}, {country_name} declared {md(total_ex)} of "
        f"{commodity_label} exports to partners that also report the matching import. "
        f"Those partners recorded {md(total_mirror)}, a cumulative gap of "
        f"{md(total_gap)} — {pct:+.1f}% of declared value.",
        reading,
        f"The annual gap is **{direction}** over the period, widest in "
        f"**{int(worst.year)}** at {worst.gap_pct:+.1f}% of declared exports.",
    ]

    if not by_partner.empty:
        biggest = by_partner.reindex(by_partner["gap"].abs().sort_values(ascending=False).index)
        top = biggest.iloc[0]
        share = (top["gap"] / total_gap * 100) if total_gap else 0
        lines.append(
            f"The largest single discrepancy sits with **{top['counterpart_name']}**, "
            f"accounting for {md(top['gap'])} ({share:.0f}% of the total gap) on "
            f"{md(top['exports'])} of declared exports."
        )

    coverage = by_year["coverage_pct"].dropna()
    if not coverage.empty:
        lines.append(
            f"Matched partners represent {coverage.mean():.0f}% of declared exports to the "
            "world on average; the remainder goes to destinations that do not report "
            "comparable bilateral data."
        )

    return "\n\n".join(lines)


def md(x):
    """Bold a currency figure for markdown, escaping the $ so Streamlit does not read it as LaTeX."""
    return "**" + usd(x).replace("$", r"\$") + "**"


def usd(x):
    if pd.isna(x):
        return "—"
    sign = "-" if x < 0 else ""
    x = abs(x)
    for unit, div in (("bn", 1e9), ("m", 1e6), ("k", 1e3)):
        if x >= div:
            return f"{sign}${x / div:,.2f}{unit}"
    return f"{sign}${x:,.0f}"
