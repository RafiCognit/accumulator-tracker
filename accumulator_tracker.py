"""
SP Accumulator Tracker
----------------------
Tracks daily accumulation for a structured-product accumulator on a stock or
commodity (Yahoo Finance data) and computes the cash the client needs on the
settlement date to pay for the shares fixed for delivery.

Run:  streamlit run accumulator_tracker.py
"""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

st.set_page_config(page_title="Accumulator Tracker", layout="wide")
st.markdown(
    "<style>[data-testid='stMetricValue']{font-size:1.45rem;white-space:normal;}"
    "[data-testid='stMetricValue'] > div{white-space:normal;overflow:visible;}</style>",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Data helpers
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=3600, show_spinner=False)
def search_securities(query: str) -> list[dict]:
    """Search Yahoo Finance by name or ticker."""
    if not query.strip():
        return []
    try:
        quotes = yf.Search(query, max_results=15, news_count=0).quotes
    except Exception:
        return []
    out = []
    for q in quotes:
        sym = q.get("symbol")
        if not sym:
            continue
        out.append(
            {
                "symbol": sym,
                "name": q.get("longname") or q.get("shortname") or sym,
                "exchange": q.get("exchDisp") or q.get("exchange") or "",
                "type": q.get("typeDisp") or q.get("quoteType") or "",
            }
        )
    return out


@st.cache_data(ttl=900, show_spinner=False)
def load_prices(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Daily closes between start and end (inclusive)."""
    df = yf.download(
        symbol,
        start=start,
        end=end + timedelta(days=1),
        interval="1d",
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        return pd.DataFrame(columns=["Close"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Close"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "Date"
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def security_info(symbol: str) -> dict:
    try:
        fi = yf.Ticker(symbol).fast_info
        return {"currency": fi.get("currency") or "", "last": fi.get("lastPrice")}
    except Exception:
        return {"currency": "", "last": None}


# --------------------------------------------------------------------------- #
# Accumulator engine
# --------------------------------------------------------------------------- #
def run_accumulator(
    prices: pd.DataFrame,
    strike: float,
    daily_qty: float,
    gear: float,
    gear_inclusive: bool,
    ko_level: float | None,
    ko_inclusive: bool,
) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Build the daily accumulation schedule from observed closes."""
    rows = []
    knocked_out_on = None
    cum = 0.0
    for dt, px in prices["Close"].items():
        px = float(px)
        if knocked_out_on is None and ko_level is not None:
            if (px >= ko_level) if ko_inclusive else (px > ko_level):
                knocked_out_on = dt

        if knocked_out_on is not None:
            status, mult = ("Knocked out" if dt == knocked_out_on else "After KO"), 0.0
        else:
            geared = (px <= strike) if gear_inclusive else (px < strike)
            status, mult = ("Geared" if geared else "Normal"), (gear if geared else 1.0)

        qty = daily_qty * mult
        cum += qty
        rows.append(
            {
                "Date": dt,
                "Close": px,
                "Status": status,
                "Multiplier": mult,
                "Qty": qty,
                "Cumulative Qty": cum,
                "Cost @ Strike": qty * strike,
                "Discount vs Close": (px - strike) * qty,
            }
        )
    return pd.DataFrame(rows), knocked_out_on


def fmt_money(x: float, ccy: str) -> str:
    return f"{ccy} {x:,.2f}".strip()


def fmt_qty(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
st.title("SP Accumulator Tracker")
st.caption(
    "Daily accumulation at strike, geared purchases when the underlying closes "
    "below strike, and the cash required on settlement. Data: Yahoo Finance (daily close)."
)

with st.sidebar:
    st.header("1 · Underlying")
    query = st.text_input(
        "Search name or ticker",
        value="Apple",
        help="e.g. 'Apple', 'HSBC', '0700.HK', 'gold', 'crude oil', 'GC=F'",
    )
    results = search_securities(query)
    options = [
        f"{r['symbol']}  —  {r['name']}  ({r['exchange']}, {r['type']})" for r in results
    ]
    manual = st.checkbox("Enter ticker manually", value=not options)
    if manual or not options:
        symbol = st.text_input("Yahoo ticker", value=query.strip().upper()).strip()
        sec_name = symbol
    else:
        choice = st.selectbox("Select security", options)
        sel = results[options.index(choice)]
        symbol, sec_name = sel["symbol"], sel["name"]

    st.header("2 · Contract terms")
    strike = st.number_input("Strike price", min_value=0.0, value=200.0, step=0.5, format="%.4f")
    daily_qty = st.number_input(
        "Daily quantity (shares/units per observation day)", min_value=0.0, value=100.0, step=1.0
    )

    gear_choice = st.selectbox(
        "Gearing when below strike", ["2x (double)", "1x (none)", "1.5x", "3x", "Custom"]
    )
    gear = {"2x (double)": 2.0, "1x (none)": 1.0, "1.5x": 1.5, "3x": 3.0}.get(gear_choice)
    if gear is None:
        gear = st.number_input("Custom gearing multiplier", min_value=0.0, value=2.0, step=0.25)
    gear_inclusive = st.radio(
        "Gearing trigger",
        ["Close < strike", "Close ≤ strike"],
        horizontal=True,
    ) == "Close ≤ strike"

    use_ko = st.checkbox("Knock-out barrier", value=False)
    ko_level, ko_inclusive = None, True
    if use_ko:
        ko_level = st.number_input("Knock-out level", min_value=0.0, value=230.0, step=0.5, format="%.4f")
        ko_inclusive = st.radio(
            "KO trigger", ["Close ≥ KO", "Close > KO"], horizontal=True
        ) == "Close ≥ KO"
        st.caption("Accumulation stops from the KO day onward (KO day not accumulated).")

    st.header("3 · Dates")
    today = date.today()
    start_d = st.date_input("Start date (first observation)", value=today - timedelta(days=90))
    end_d = st.date_input("End date (contract maturity)", value=today + timedelta(days=90))
    fixing_d = st.date_input(
        "Fixing date for delivery",
        value=today,
        help="Observations from the start date up to and including this date are delivered on the settlement date.",
    )
    settle_d = st.date_input("Settlement / delivery date", value=today + timedelta(days=2))

# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
errors = []
if not symbol:
    errors.append("Choose a security.")
if strike <= 0:
    errors.append("Strike must be greater than zero.")
if not (start_d <= fixing_d <= end_d):
    errors.append("Dates must satisfy: start ≤ fixing ≤ end.")
if settle_d < fixing_d:
    errors.append("Settlement date must be on or after the fixing date.")
if use_ko and ko_level is not None and ko_level <= strike:
    errors.append("Knock-out level should be above the strike.")
if errors:
    for e in errors:
        st.error(e)
    st.stop()

# --------------------------------------------------------------------------- #
# Data + calculation
# --------------------------------------------------------------------------- #
with st.spinner(f"Loading {symbol} from Yahoo Finance…"):
    prices = load_prices(symbol, start_d, min(end_d, today))
    info = security_info(symbol)
ccy = info["currency"]

if prices.empty:
    if start_d > today:
        prices = pd.DataFrame(columns=["Close"])
    else:
        st.error(f"No price data returned for **{symbol}** in that period.")
        st.stop()

sched, ko_date = run_accumulator(
    prices, strike, daily_qty, gear, gear_inclusive, ko_level, ko_inclusive
)

# Split into this delivery (≤ fixing) and later
if not sched.empty:
    fix_ts = pd.Timestamp(fixing_d)
    delivery = sched[sched["Date"] <= fix_ts]
    after_fix = sched[sched["Date"] > fix_ts]
else:
    delivery = after_fix = sched

last_obs = sched["Date"].max().date() if not sched.empty else None
last_close = float(prices["Close"].iloc[-1]) if not prices.empty else (info["last"] or 0.0)

# Remaining observation days not yet in the data (future business days)
def future_bdays(a: date, b: date) -> int:
    if b < a:
        return 0
    return len(pd.bdate_range(a, b))

# First day with no data yet: the day after today (or after last observation), never before start
next_day = max(start_d, max(last_obs or today, today) + timedelta(days=1))
alive = ko_date is None
rem_to_fix = future_bdays(next_day, fixing_d) if alive else 0
rem_to_end = future_bdays(next_day, end_d) if alive else 0

fixed_qty = float(delivery["Qty"].sum()) if not delivery.empty else 0.0
fixed_cash = fixed_qty * strike
proj_min_qty = fixed_qty + rem_to_fix * daily_qty
proj_max_qty = fixed_qty + rem_to_fix * daily_qty * max(gear, 1.0)

# --------------------------------------------------------------------------- #
# Headline: cash needed on settlement
# --------------------------------------------------------------------------- #
st.subheader(f"{sec_name}  ·  {symbol}")
c_info = st.columns(4)
c_info[0].metric("Last close", fmt_money(last_close, ccy), help=f"As of {last_obs}")
c_info[1].metric("Strike", fmt_money(strike, ccy),
                 f"{(strike / last_close - 1) * 100:+.2f}% vs last" if last_close else None,
                 delta_color="off")
c_info[2].metric("Gearing", f"{gear:g}x below strike")
c_info[3].metric("Status", f"Knocked out {ko_date.date()}" if ko_date is not None else "Live")

st.divider()
if rem_to_fix == 0:
    st.markdown(f"### Cash required on settlement ({settle_d:%d %b %Y})")
    m = st.columns(3)
    m[0].metric("Shares fixed for delivery", fmt_qty(fixed_qty))
    m[1].metric("Cash required (qty × strike)", fmt_money(fixed_cash, ccy))
    mv = fixed_qty * last_close
    m[2].metric("Market value at last close", fmt_money(mv, ccy),
                f"{fmt_money(mv - fixed_cash, ccy)} MTM vs strike")
else:
    st.markdown(f"### Cash required on settlement ({settle_d:%d %b %Y}) — fixing still in progress")
    st.info(
        f"{rem_to_fix} observation day(s) remain until the fixing date ({fixing_d:%d %b %Y}). "
        "The final amount will fall between the minimum (all remaining days above strike) "
        "and the maximum (all remaining days geared)."
    )
    m = st.columns(3)
    m[0].metric("Accumulated so far", fmt_qty(fixed_qty), fmt_money(fixed_cash, ccy), delta_color="off")
    m[1].metric("Minimum at fixing", fmt_qty(proj_min_qty), fmt_money(proj_min_qty * strike, ccy), delta_color="off")
    m[2].metric("Maximum at fixing (worst case)", fmt_qty(proj_max_qty), fmt_money(proj_max_qty * strike, ccy), delta_color="off")

# Breakdown
if not delivery.empty:
    n_norm = int((delivery["Status"] == "Normal").sum())
    n_gear = int((delivery["Status"] == "Geared").sum())
    q_norm = float(delivery.loc[delivery["Status"] == "Normal", "Qty"].sum())
    q_gear = float(delivery.loc[delivery["Status"] == "Geared", "Qty"].sum())
    b = st.columns(4)
    b[0].metric("Days at/above strike", n_norm, f"{fmt_qty(q_norm)} shares", delta_color="off")
    b[1].metric("Geared days (below strike)", n_gear, f"{fmt_qty(q_gear)} shares", delta_color="off")
    b[2].metric("Extra shares from gearing", fmt_qty(q_gear - n_gear * daily_qty),
                fmt_money((q_gear - n_gear * daily_qty) * strike, ccy), delta_color="off")
    avg_px = float(delivery["Close"].mean())
    b[3].metric("Avg close in fixing period", fmt_money(avg_px, ccy))

# Whole-contract view
with st.expander("Whole contract (start → end) outlook", expanded=False):
    total_obs_qty = float(sched["Qty"].sum()) if not sched.empty else 0.0
    w = st.columns(3)
    w[0].metric("Accumulated to date (all observations)", fmt_qty(total_obs_qty),
                fmt_money(total_obs_qty * strike, ccy), delta_color="off")
    w[1].metric("Projected max to end (all geared)",
                fmt_qty(total_obs_qty + rem_to_end * daily_qty * max(gear, 1.0)),
                fmt_money((total_obs_qty + rem_to_end * daily_qty * max(gear, 1.0)) * strike, ccy),
                delta_color="off")
    w[2].metric("Projected min to end", fmt_qty(total_obs_qty + rem_to_end * daily_qty),
                fmt_money((total_obs_qty + rem_to_end * daily_qty) * strike, ccy), delta_color="off")
    if not after_fix.empty:
        st.caption(
            f"{len(after_fix)} observation(s) after the fixing date "
            f"({fmt_qty(after_fix['Qty'].sum())} shares) belong to a later delivery."
        )
    st.caption("Future days are estimated with weekday business days; exchange holidays are not excluded.")

# --------------------------------------------------------------------------- #
# Chart
# --------------------------------------------------------------------------- #
if not sched.empty:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=sched["Date"], y=sched["Close"], name="Close",
                             line=dict(color="#2a6fdb", width=2)), secondary_y=False)
    g = sched[sched["Status"] == "Geared"]
    fig.add_trace(go.Scatter(x=g["Date"], y=g["Close"], mode="markers", name=f"Geared day ({gear:g}x)",
                             marker=dict(color="#d64545", size=7)), secondary_y=False)
    fig.add_hline(y=strike, line=dict(color="#d64545", dash="dash"),
                  annotation_text=f"Strike {strike:,.2f}", annotation_position="bottom right")
    if ko_level:
        fig.add_hline(y=ko_level, line=dict(color="#2e9e5b", dash="dot"),
                      annotation_text=f"KO {ko_level:,.2f}", annotation_position="top right")
    fig.add_trace(go.Scatter(x=sched["Date"], y=sched["Cumulative Qty"], name="Cumulative qty",
                             line=dict(color="#888", width=1.5, shape="hv")), secondary_y=True)
    fig.add_vline(x=pd.Timestamp(fixing_d), line=dict(color="#999", dash="dot"))
    fig.update_layout(height=460, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.08), hovermode="x unified")
    fig.update_yaxes(title_text=f"Price ({ccy})", secondary_y=False)
    fig.update_yaxes(title_text="Cumulative quantity", secondary_y=True, showgrid=False)
    st.plotly_chart(fig, use_container_width=True)

    # ----------------------------------------------------------------------- #
    # Schedule table
    # ----------------------------------------------------------------------- #
    st.markdown("#### Daily accumulation schedule")
    show = sched.copy()
    show["Date"] = show["Date"].dt.date
    show["Delivery"] = ["This delivery" if d <= fixing_d else "Later" for d in show["Date"]]
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Close": st.column_config.NumberColumn(format="%.4f"),
            "Multiplier": st.column_config.NumberColumn(format="%.2fx"),
            "Qty": st.column_config.NumberColumn(format="%.2f"),
            "Cumulative Qty": st.column_config.NumberColumn(format="%.2f"),
            "Cost @ Strike": st.column_config.NumberColumn(format="%.2f"),
            "Discount vs Close": st.column_config.NumberColumn(format="%.2f"),
        },
    )
    st.download_button(
        "Download schedule (CSV)",
        show.to_csv(index=False).encode(),
        file_name=f"accumulator_{symbol}_{start_d}_{fixing_d}.csv",
        mime="text/csv",
    )
else:
    st.info("No observations yet — the contract has not started.")
