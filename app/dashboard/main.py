import sys
from pathlib import Path

# When run via `streamlit run app/dashboard/main.py`, only the file's directory
# is on sys.path. Insert the project root so `app`, `database`, `utils` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from app.dashboard.db import load_billing_records, load_subscriptions, monthly_spend_df

st.set_page_config(page_title="SubFlow", page_icon="💳", layout="wide")
st.title("💳 SubFlow — 訂閱管理")

# ── Data ──────────────────────────────────────────────────────────────────────

subs_df = load_subscriptions()

_CYCLE_TO_MONTHLY = {
    "monthly": 1.0,
    "annual": 1 / 12,
    "quarterly": 1 / 3,
    "weekly": 4.33,
    "one_time": 0.0,
}


def _monthly_equiv(row: pd.Series) -> float:
    return row["金額"] * _CYCLE_TO_MONTHLY.get(row["週期"], 1.0)


active_df = subs_df[subs_df["啟用"]].copy() if not subs_df.empty else pd.DataFrame()

if not active_df.empty:
    active_df["月均費用"] = active_df.apply(_monthly_equiv, axis=1)
    monthly_total = active_df["月均費用"].sum()

    cutoff = pd.Timestamp(date.today() + timedelta(days=7))
    upcoming_count = int(
        active_df["下次扣款"]
        .dropna()
        .pipe(lambda s: (pd.to_datetime(s) <= cutoff).sum())
    )
else:
    monthly_total = 0.0
    upcoming_count = 0

# ── Metrics ───────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
col1.metric("啟用訂閱數", len(active_df))
col2.metric("月均支出 (TWD)", f"{monthly_total:,.0f}")
col3.metric("7 天內到期", upcoming_count)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_subs, tab_bills, tab_chart = st.tabs(["📋 訂閱清單", "🧾 帳單紀錄", "📊 月支出圖表"])

# ── Tab 1: Subscriptions ──────────────────────────────────────────────────────

with tab_subs:
    show_all = st.checkbox("顯示停用訂閱", value=False)
    display_df = subs_df if show_all else active_df

    if display_df.empty:
        st.info("尚無訂閱資料。")
    else:
        drop_cols = [c for c in ["id", "月均費用"] if c in display_df.columns]
        st.dataframe(
            display_df.drop(columns=drop_cols),
            use_container_width=True,
            hide_index=True,
        )

    if st.button("🔄 重新整理"):
        load_subscriptions.clear()
        st.rerun()

# ── Tab 2: Billing Records ────────────────────────────────────────────────────

with tab_bills:
    bills_df = load_billing_records()

    if bills_df.empty:
        st.info("尚無帳單紀錄。可呼叫 POST /ops/gmail-import 觸發匯入。")
    else:
        # Date range filter
        min_date = pd.to_datetime(bills_df["扣款時間"]).min().date()
        max_date = pd.to_datetime(bills_df["扣款時間"]).max().date()
        col_a, col_b = st.columns(2)
        date_from = col_a.date_input("起始日期", value=min_date, min_value=min_date, max_value=max_date)
        date_to = col_b.date_input("結束日期", value=max_date, min_value=min_date, max_value=max_date)

        mask = (
            (pd.to_datetime(bills_df["扣款時間"]).dt.date >= date_from)
            & (pd.to_datetime(bills_df["扣款時間"]).dt.date <= date_to)
        )
        filtered = bills_df[mask]

        st.caption(f"顯示 {len(filtered)} / {len(bills_df)} 筆")
        st.dataframe(
            filtered.drop(columns=["id"]),
            use_container_width=True,
            hide_index=True,
        )

    if st.button("🔄 重新整理", key="refresh_bills"):
        load_billing_records.clear()
        st.rerun()

# ── Tab 3: Monthly Spend Chart ────────────────────────────────────────────────

with tab_chart:
    spend_df = monthly_spend_df()

    if spend_df.empty:
        st.info("尚無帳單資料可繪製圖表。")
    else:
        chart = (
            alt.Chart(spend_df)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("月份:O", sort=None, title="月份"),
                y=alt.Y("金額:Q", title="支出金額"),
                color=alt.Color("幣別:N", title="幣別"),
                tooltip=[
                    alt.Tooltip("月份:O", title="月份"),
                    alt.Tooltip("幣別:N", title="幣別"),
                    alt.Tooltip("金額:Q", title="金額", format=",.0f"),
                ],
            )
            .properties(height=380, title="每月帳單支出")
        )
        st.altair_chart(chart, use_container_width=True)
