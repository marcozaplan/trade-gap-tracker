import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import cache
import gaps
from config import (
    ANOMALY_THRESHOLD,
    COMMODITY_GROUPS,
    DEFAULT_COUNTRY,
    EITI_COUNTRIES,
    END_YEAR,
    START_YEAR,
)

st.set_page_config(page_title="Tool on Trade Gap Analysis", page_icon="◫", layout="wide")

INK = "#1b2430"
MUTED = "#6b7785"
DECLARED = "#2f6f9f"
MIRROR = "#c2553f"
GRID = "#e7eaee"

SOURCE = "UN Comtrade, annual merchandise trade statistics (HS)"
SOURCE_URL = "https://comtradeplus.un.org/"


def _streamlit_version():
    parts = []
    for chunk in st.__version__.split(".")[:2]:
        parts.append(int(chunk) if chunk.isdigit() else 0)
    return tuple(parts)


# width="stretch" landed in Streamlit 1.49; older builds need use_container_width
FILL = (
    {"width": "stretch"} if _streamlit_version() >= (1, 49)
    else {"use_container_width": True}
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 2.5rem; max-width: 1200px;}
      [data-testid="stMetric"] {
          background: #fbfcfd; border: 1px solid #e7eaee;
          border-radius: 8px; padding: 14px 16px;
      }
      [data-testid="stMetricLabel"] p {color: #6b7785; font-size: 0.82rem;}
      h3 {margin-top: 1.7rem;}
      footer, #MainMenu {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False, ttl=300)
def load():
    return cache.load()


def hbar(frame, labels, values, height, axis_title):
    fig = go.Figure(go.Bar(
        y=frame[labels], x=frame[values], orientation="h",
        marker_color=[MIRROR if v >= 0 else DECLARED for v in frame[values]],
        hovertemplate="%{y}<br>%{x:$,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=height, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=0, r=0, t=10, b=0), font=dict(color=INK), showlegend=False,
        xaxis=dict(title=axis_title, gridcolor=GRID, zerolinecolor="#c9ced6", tickprefix="$"),
        yaxis=dict(gridcolor="white", automargin=True),
    )
    return fig


aggregate, partners, manifest = load()

if aggregate is None:
    st.title("Tool on Trade Gap Analysis")
    st.error("No cached dataset found.")
    st.code("export COMTRADE_API_KEY=...\npython prefetch.py", language="bash")
    st.caption(
        "The dashboard reads only from the prefetched cache and makes no API calls at "
        "runtime. Countries appear as they land, so you can leave the fetch running and refresh."
    )
    st.stop()

available = [c for c in EITI_COUNTRIES if c in set(aggregate["country"])]
if not available:
    st.error("The cache contains no recognised countries.")
    st.stop()

st.title("Tool on Trade Gap Analysis")
st.markdown(
    f"<p style='color:{MUTED}; margin-top:-0.6rem; font-size:1.02rem;'>"
    "Data on declared mineral exports and partner-recorded imports· "
    f"<a href='{SOURCE_URL}' style='color:{MUTED};'>{SOURCE}</a>, {START_YEAR}–{END_YEAR}"
    "</p>",
    unsafe_allow_html=True,
)

pick = st.columns([2, 2, 3])
with pick[0]:
    country = st.selectbox(
        "Country",
        available,
        index=available.index(DEFAULT_COUNTRY) if DEFAULT_COUNTRY in available else 0,
        format_func=lambda c: EITI_COUNTRIES[c],
    )
with pick[1]:
    present = sorted(set(aggregate.loc[aggregate["country"] == country, "commodity"]))
    commodity = st.selectbox(
        "Commodity",
        ["ALL"] + present,
        format_func=lambda c: "All minerals and metals" if c == "ALL"
        else f"HS {c} — {COMMODITY_GROUPS.get(c, c)}",
    )

scope_agg = gaps.filter_scope(aggregate, country, commodity)
scope_partners = gaps.filter_scope(partners, country, commodity)
country_agg = gaps.filter_scope(aggregate, country, "ALL")

if scope_agg.empty:
    st.warning("No matched bilateral flows for this selection.")
    st.stop()

by_year = gaps.collapse_years(scope_agg)
by_partner = gaps.collapse_partners(scope_partners)
by_commodity = gaps.collapse_commodities(country_agg)

country_name = EITI_COUNTRIES[country]
commodity_label = (
    "minerals and metals" if commodity == "ALL"
    else COMMODITY_GROUPS.get(commodity, commodity).lower()
)

total_ex = by_year["exports"].sum()
total_mirror = by_year["mirror"].sum()
total_gap = total_mirror - total_ex
gap_pct = (total_gap / total_ex * 100) if total_ex else 0
span = f"{int(by_year.year.min())}–{int(by_year.year.max())}"

st.markdown("")
k = st.columns(4)
k[0].metric("Declared exports", gaps.usd(total_ex),
            help=f"As reported by {country_name}, {span}")
k[1].metric("Partner-recorded imports", gaps.usd(total_mirror),
            help="Mirror flows, as reported by partners that record the matching import")
k[2].metric("Cumulative gap", gaps.usd(total_gap), delta=f"{gap_pct:+.1f}% of declared")

material = by_partner[
    (by_partner["exports"] > 0) & (by_partner["gap_pct"].abs() > ANOMALY_THRESHOLD)
]
k[3].metric(
    f"Partners over {ANOMALY_THRESHOLD:.0f}% gap",
    f"{len(material)} of {len(by_partner)}",
    help="Destinations where the two sides disagree by more than the flagging "
         "threshold, out of all partners with declared exports",
)

reporting = (
    scope_partners[scope_partners["mirror"] > 0].groupby("year")["counterpart"].nunique()
)
if len(reporting) > 3:
    latest, typical = reporting.iloc[-1], reporting.iloc[:-1].median()
    if latest < typical * 0.75:
        st.warning(
            f"{int(reporting.index[-1])} has only {latest} reporting partners against a "
            f"typical {typical:.0f}. The latest year is still filling in — treat it as provisional."
        )

st.markdown("### Declared exports against partner records")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=by_year["year"], y=by_year["exports"], name="Declared exports",
    line=dict(color=DECLARED, width=2.5), mode="lines+markers", marker=dict(size=6),
))
fig.add_trace(go.Scatter(
    x=by_year["year"], y=by_year["mirror"], name="Partner-recorded imports",
    line=dict(color=MIRROR, width=2.5), mode="lines+markers", marker=dict(size=6),
    fill="tonexty", fillcolor="rgba(194,85,63,0.12)",
))
fig.update_layout(
    height=360, hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
    margin=dict(l=0, r=0, t=10, b=0),
    legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)"),
    font=dict(color=INK),
    yaxis=dict(title="USD", gridcolor=GRID, zerolinecolor=GRID, tickprefix="$"),
    xaxis=dict(gridcolor="white", dtick=1),
)
st.plotly_chart(fig, **FILL)

left, right = st.columns(2)

with left:
    st.markdown("### Annual gap")
    bars = go.Figure(go.Bar(
        x=by_year["year"], y=by_year["gap"],
        marker_color=[MIRROR if v >= 0 else DECLARED for v in by_year["gap"]],
        hovertemplate="%{x}<br>%{y:$,.0f}<extra></extra>",
    ))
    bars.update_layout(
        height=330, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=0, r=0, t=10, b=0), font=dict(color=INK), showlegend=False,
        yaxis=dict(title="Gap (USD)", gridcolor=GRID, zerolinecolor="#c9ced6", tickprefix="$"),
        xaxis=dict(gridcolor="white", dtick=2),
    )
    st.plotly_chart(bars, **FILL)

with right:
    st.markdown("### Gap by commodity")
    st.caption("All chapters, regardless of the filter above — where to look next.")
    st.plotly_chart(
        hbar(by_commodity.iloc[::-1], "label", "gap", 330, "Cumulative gap (USD)"), **FILL
    )

st.markdown("### Gap by trading partner")
st.plotly_chart(
    hbar(by_partner.head(15).iloc[::-1], "counterpart_name", "gap", 420,
         "Cumulative gap (USD)"),
    **FILL,
)

st.markdown("### What the numbers say")
st.markdown(gaps.narrate(by_year, by_partner, country_name, commodity_label))

with st.expander("Full partner breakdown"):
    table = by_partner[["counterpart_name", "exports", "mirror", "gap", "gap_pct"]].copy()
    table.columns = ["Partner", "Declared exports", "Partner-recorded", "Gap", "Gap %"]
    for col in ("Declared exports", "Partner-recorded", "Gap"):
        table[col] = table[col].map(gaps.usd)
    table["Gap %"] = table["Gap %"].map(lambda v: f"{v:+.1f}%")
    st.dataframe(table, hide_index=True, **FILL)

    st.download_button(
        "Download partner data (CSV)",
        by_partner.to_csv(index=False).encode(),
        file_name=f"trade_gap_{country}_{commodity}.csv",
        mime="text/csv",
    )

st.divider()
st.markdown("## Methodology")

st.markdown(
    f"""
**Source.** All trade figures come from [{SOURCE}]({SOURCE_URL}), accessed through the
UN Comtrade API. No other data source is used. Figures are nominal US dollars, not
adjusted for inflation.

**Scope.** HS chapters 26 (ores, slag and ash), 71 (precious metals and stones) and
72–81 (base metals), {START_YEAR} to {END_YEAR}, for EITI implementing countries.

**The calculation.** For each country, commodity and year, declared exports to a given
partner are compared against what that partner declares importing from the same country:

```
Gap = partner-recorded imports − declared exports
```

A **positive gap** means partners record receiving more than the exporter declares
sending. A **negative gap** means the reverse. Only partners that report the matching
flow enter the comparison, so headline totals cover less than exports to the world; the
coverage share is stated in the summary above.

Self-trade rows and aggregate partner codes — World, the EU bloc (which reports
alongside its own member states), "Areas, nes", bunkers, free zones and the regional
residuals — are removed before anything is computed. They have no mirror counterpart and
would otherwise register as a one-sided gap.

No CIF/FOB, entrepôt or timing adjustment is applied. This is the raw gap, kept
deliberately transparent.
"""
)

st.markdown("### Why gaps appear")

st.markdown(
    """
| Factor | What it is |
|---|---|
| **Origin versus destination** | Imports can be recorded by country of origin, exports by country of destination. Goods sold through a trader may be counted on both legs. |
| **CIF versus FOB valuation** | Exports are recorded free on board, imports inclusive of cost, insurance and freight, which adds a few percentage points to the import side by construction. |
| **Entrepôt and re-export routing** | Trade passing through a hub can be attributed differently by each side. |
| **Timing** | Shipments crossing the year boundary may be recorded in different years by each side. |
| **Classification** | The two sides can assign different HS codes to the same goods. |
| **Confidentiality and non-reporting** | Suppressed or absent flows leave one side blank. |
| **Misinvoicing** | Under- or over-declaration of value. |

These factors can combine in different proportions for different countries and
commodities, and this dashboard does not attribute a given gap to any one of them.
"""
)

st.markdown("### Disclaimer")

st.markdown(
    """
**A trade gap is not evidence of wrongdoing.** The factors above produce discrepancies in
the ordinary course of trade, and several of them are mechanical. Nothing shown here
identifies, implicates or accuses any country, company or individual of misinvoicing,
smuggling, tax evasion or any other offence.

This dashboard is a **screening tool**. It indicates where bilateral statistics disagree
and therefore where closer examination may be warranted. Establishing misinvoicing in any
particular transaction requires customs investigation, firm-level audit and access to
records that are not public.

Figures are derived from data reported by national statistical authorities to UN Comtrade
and inherit any errors, revisions, suppressions and gaps in that reporting. The most
recent year is typically incomplete, as partners report on different schedules. Nothing
here constitutes legal, financial or investment advice, and the analysis is independent
of, and not endorsed by, the United Nations, UN Comtrade, the EITI or any government.
"""
)

built = manifest.get("built", "")
note = (
    f"{SOURCE} · HS chapters {', '.join(manifest.get('commodities', [])) or '—'} · "
    f"{span} · {len(available)} countries cached · built {built[:10] or 'unknown'}"
)
if manifest.get("partial"):
    note += " · fetch still in progress, refresh for more countries"
st.caption(note)
