import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from app.dashboard.db import (
    activate_subscription,
    apply_proposed_change,
    create_subscription,
    deactivate_subscription,
    delete_subscription,
    load_billing_records,
    load_subscriptions,
    mark_non_subscription,
    monthly_spend_df,
    update_subscription,
    update_subscription_note,
)

st.set_page_config(page_title="SubFlow", page_icon="💳", layout="wide")
st.title("💳 SubFlow — 訂閱管理")

if "proposed_changes" not in st.session_state:
    st.session_state.proposed_changes = []

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


def _build_billing_summary(bills_df: pd.DataFrame) -> pd.DataFrame:
    df = bills_df.copy()
    df["年月"] = pd.to_datetime(df["扣款時間"]).dt.to_period("M")
    summary = (
        df.groupby(["subscription_id", "服務名稱", "類型"])
        .agg(帳單次數=("id", "count"), 月份數=("年月", "nunique"), 最近帳單=("扣款時間", "max"))
        .reset_index()
    )
    # latest billing details (金額, 幣別, 郵件主旨) per subscription
    latest = (
        df.sort_values("扣款時間")
        .groupby("subscription_id")
        .last()[["金額", "幣別", "郵件主旨"]]
        .reset_index()
    )
    summary = summary.merge(latest, on="subscription_id", how="left")
    summary["狀態"] = summary.apply(
        lambda row: "💳 一次性消費" if row["類型"] == "一次性消費"
        else ("🆕 新訂閱" if row["月份數"] <= 1 else f"🔄 連續 {row['月份數']} 個月"),
        axis=1,
    )
    summary["最近帳單"] = pd.to_datetime(summary["最近帳單"]).dt.date
    _subs = load_subscriptions()
    active_ids = set(_subs[_subs["啟用"]]["id"].tolist()) if not _subs.empty else set()
    summary["已在訂閱清單"] = summary["subscription_id"].isin(active_ids)
    summary["選取"] = False
    return (
        summary[[
            "選取", "服務名稱", "帳單次數", "狀態", "最近帳單",
            "金額", "幣別", "已在訂閱清單", "subscription_id", "郵件主旨",
        ]]
        .sort_values("最近帳單", ascending=False)
        .reset_index(drop=True)
    )


active_df = subs_df[subs_df["啟用"]].copy() if not subs_df.empty else pd.DataFrame()
inactive_df = subs_df[~subs_df["啟用"]].copy() if not subs_df.empty else pd.DataFrame()

if not active_df.empty:
    active_df["月均費用"] = active_df.apply(_monthly_equiv, axis=1)
    monthly_total = active_df["月均費用"].sum()
    cutoff = pd.Timestamp(date.today() + timedelta(days=7))
    upcoming_count = int(
        active_df["下次扣款"].dropna().pipe(lambda s: (pd.to_datetime(s) <= cutoff).sum())
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

_CYCLES = ["monthly", "annual", "quarterly", "weekly", "one_time"]
_CURRENCIES = ["TWD", "USD", "EUR", "JPY"]

_TABLE_COLS   = ["id", "選取", "名稱", "週期", "金額", "幣別", "最近扣款", "郵件主旨", "備註"]
_DISABLED_COLS = ["名稱", "週期", "金額", "幣別", "最近扣款", "郵件主旨"]


# ── Tab 1: Subscriptions ──────────────────────────────────────────────────────

with tab_subs:

    # Refresh at top
    if st.button("🔄 重新整理", key="refresh_subs"):
        load_subscriptions.clear()
        st.rerun()

    # ── Section 1: Active ─────────────────────────────────────────────────────
    st.subheader(f"訂閱中（{len(active_df)} 項）")

    if active_df.empty:
        st.info("尚無啟用訂閱。")
    else:
        editor_data = active_df.copy()
        editor_data["選取"] = False
        available = [c for c in _TABLE_COLS if c in editor_data.columns]
        editor_data = editor_data[available]

        edited_active = st.data_editor(
            editor_data,
            column_config={
                "id": None,
                "選取": st.column_config.CheckboxColumn("選取", default=False),
                "最近扣款": st.column_config.DatetimeColumn("最近扣款", disabled=True, format="YYYY-MM-DD"),
                "郵件主旨": st.column_config.TextColumn("郵件主旨", disabled=True, width="large"),
                "備註": st.column_config.TextColumn("備註", width="medium"),
            },
            disabled=_DISABLED_COLS,
            hide_index=True,
            use_container_width=True,
            key="active_subs_editor",
        )

        selected_ids = (
            edited_active[edited_active["選取"] == True]["id"].tolist()
            if "id" in edited_active.columns else []
        )
        n_sel = len(selected_ids)

        act1, act2, _, save_col = st.columns([2, 2, 2, 2])

        if act1.button(
            f"⛔ 已停訂（{n_sel}）" if n_sel else "⛔ 已停訂",
            disabled=n_sel == 0,
            help="將選取項目移至已停用",
        ):
            for sid in selected_ids:
                deactivate_subscription(sid)
            load_subscriptions.clear()
            st.rerun()

        if act2.button(
            f"🗑️ 非訂閱項目（{n_sel}）" if n_sel else "🗑️ 非訂閱項目",
            disabled=n_sel == 0,
            help="標記為一次性消費並移至已停用",
        ):
            for sid in selected_ids:
                mark_non_subscription(sid)
            load_subscriptions.clear()
            st.rerun()

        if save_col.button("💾 儲存備註"):
            orig_notes = active_df.set_index("id")["備註"]
            new_notes = edited_active.set_index("id")["備註"]
            changed = [
                (sub_id, str(new_notes.loc[sub_id] or ""))
                for sub_id in orig_notes.index
                if sub_id in new_notes.index
                and (orig_notes.loc[sub_id] or "") != str(new_notes.loc[sub_id] or "")
            ]
            if changed:
                for sub_id, note in changed:
                    update_subscription_note(sub_id, note or None)
                load_subscriptions.clear()
                st.success(f"已儲存 {len(changed)} 筆備註")
                st.rerun()
            else:
                st.info("沒有偵測到備註變更")

    st.divider()

    # ── Section 2: Inactive ───────────────────────────────────────────────────
    st.subheader(f"已停用（{len(inactive_df)} 項）")
    st.caption("停用訂閱不計入月均費用統計。如需重新啟用，請使用下方「編輯 / 刪除訂閱」。")

    if inactive_df.empty:
        st.info("無停用訂閱。")
    else:
        hide = [c for c in ["id", "月均費用", "啟用", "服務商", "下次扣款", "訂閱開始"] if c in inactive_df.columns]
        st.dataframe(inactive_df.drop(columns=hide), use_container_width=True, hide_index=True)

    st.divider()

    # ── Add subscription ──────────────────────────────────────────────────────

    with st.expander("➕ 新增訂閱"):
        with st.form("add_sub_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("服務名稱 *")
            new_provider = c2.text_input("服務商")
            c3, c4, c5 = st.columns(3)
            new_cycle = c3.selectbox("計費週期", _CYCLES)
            new_amount = c4.number_input("金額 *", min_value=0.0, step=1.0, format="%.2f")
            new_currency = c5.selectbox("幣別", _CURRENCIES)
            col_d1, col_d2 = st.columns(2)
            new_since = col_d1.date_input("訂閱開始日（選填）", value=None)
            new_nbd = col_d2.date_input("下次扣款日（選填）", value=None)
            new_note = st.text_area("備註", height=80)
            add_submitted = st.form_submit_button("新增")

        if add_submitted:
            if not new_name or new_amount <= 0:
                st.error("服務名稱與金額（> 0）為必填")
            else:
                create_subscription({
                    "name": new_name,
                    "provider": new_provider,
                    "billing_cycle": new_cycle,
                    "amount": new_amount,
                    "currency": new_currency,
                    "subscribed_since": new_since,
                    "next_billing_date": new_nbd,
                    "note": new_note,
                })
                load_subscriptions.clear()
                st.success(f"已新增「{new_name}」")
                st.rerun()

    # ── Edit / Delete subscription ────────────────────────────────────────────

    with st.expander("✏️ 編輯 / 刪除訂閱"):
        if subs_df.empty:
            st.info("尚無訂閱資料。")
        else:
            sub_ids = subs_df["id"].tolist()
            sel_id = st.selectbox(
                "選擇訂閱",
                sub_ids,
                format_func=lambda i: subs_df.loc[subs_df["id"] == i, "名稱"].iloc[0],
                key="edit_sel",
            )
            sel = subs_df[subs_df["id"] == sel_id].iloc[0]

            with st.form("edit_sub_form"):
                ec1, ec2 = st.columns(2)
                ed_name = ec1.text_input("服務名稱 *", value=sel["名稱"])
                ed_provider = ec2.text_input("服務商", value=sel["服務商"])
                ec3, ec4, ec5 = st.columns(3)
                cycle_idx = _CYCLES.index(sel["週期"]) if sel["週期"] in _CYCLES else 0
                ed_cycle = ec3.selectbox("計費週期", _CYCLES, index=cycle_idx)
                ed_amount = ec4.number_input("金額 *", value=float(sel["金額"]), min_value=0.0, step=1.0, format="%.2f")
                curr_idx = _CURRENCIES.index(sel["幣別"]) if sel["幣別"] in _CURRENCIES else 0
                ed_currency = ec5.selectbox("幣別", _CURRENCIES, index=curr_idx)
                col_ed1, col_ed2 = st.columns(2)
                since_raw = sel.get("訂閱開始") if "訂閱開始" in sel.index else None
                since_val = since_raw if pd.notna(since_raw) else None
                ed_since = col_ed1.date_input("訂閱開始日", value=since_val)
                nbd_raw = sel["下次扣款"]
                nbd_val = nbd_raw if pd.notna(nbd_raw) else date.today()
                ed_nbd = col_ed2.date_input("下次扣款日", value=nbd_val)
                ed_active = st.checkbox("啟用", value=bool(sel["啟用"]))
                ed_note = st.text_area("備註", value=sel["備註"], height=80)
                save_btn = st.form_submit_button("💾 儲存變更")

            if save_btn:
                if not ed_name or ed_amount <= 0:
                    st.error("服務名稱與金額（> 0）為必填")
                else:
                    update_subscription(int(sel_id), {
                        "name": ed_name,
                        "provider": ed_provider,
                        "billing_cycle": ed_cycle,
                        "amount": ed_amount,
                        "currency": ed_currency,
                        "subscribed_since": ed_since,
                        "next_billing_date": ed_nbd,
                        "is_active": ed_active,
                        "note": ed_note,
                    })
                    load_subscriptions.clear()
                    st.success("已儲存變更")
                    st.rerun()

            st.divider()
            confirm_del = st.checkbox(
                "確認刪除（關聯帳單紀錄也將一併移除，無法復原）",
                key="confirm_del",
            )
            if st.button("🗑️ 刪除此訂閱", disabled=not confirm_del, type="secondary"):
                delete_subscription(int(sel_id))
                load_subscriptions.clear()
                load_billing_records.clear()
                st.success(f"已刪除「{sel['名稱']}」")
                st.rerun()


# ── Tab 2: Billing Records ────────────────────────────────────────────────────

with tab_bills:
    bills_df = load_billing_records()

    # ── Top action buttons ────────────────────────────────────────────────────
    col_refresh, col_scan = st.columns([1, 3])
    if col_refresh.button("🔄 重新整理", key="refresh_bills"):
        load_billing_records.clear()
        st.rerun()

    if col_scan.button("📧 觸發 Gmail 掃描"):
        with st.spinner("掃描中，請稍候…"):
            try:
                from app.parsers.importer import run_gmail_import
                from database.session import SessionLocal
                with SessionLocal() as db:
                    result = run_gmail_import(db)
                st.success(
                    f"完成：抓取 {result.total_fetched} 封 ／ "
                    f"新增 {result.inserted} 筆 ／ "
                    f"重複略過 {result.skipped_duplicate} 筆"
                )
                if result.proposed_changes:
                    st.session_state.proposed_changes = [
                        {
                            "sub_id": c.subscription_id,
                            "服務名稱": c.subscription_name,
                            "目前金額": c.current_amount,
                            "目前幣別": c.current_currency,
                            "新金額": c.new_amount,
                            "新幣別": c.new_currency,
                            "郵件主旨": c.raw_subject,
                        }
                        for c in result.proposed_changes
                    ]
                load_billing_records.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"掃描失敗：{exc}")

    if bills_df.empty:
        st.info("尚無帳單紀錄。可點擊上方「觸發 Gmail 掃描」匯入。")
    else:
        _RANGE_OPTIONS = ["1個月", "1季", "半年", "1年", "所有"]
        _range_delta = {"1個月": 30, "1季": 90, "半年": 180, "1年": 365}
        today = date.today()
        data_min = pd.to_datetime(bills_df["扣款時間"]).min().date()

        if "bills_range_sel" not in st.session_state:
            st.session_state.bills_range_sel = "所有"
        if "bills_date_from" not in st.session_state:
            st.session_state.bills_date_from = data_min
        if "bills_date_to" not in st.session_state:
            st.session_state.bills_date_to = today

        range_sel = st.radio(
            "快速選擇",
            _RANGE_OPTIONS,
            index=_RANGE_OPTIONS.index(st.session_state.bills_range_sel),
            horizontal=True,
        )

        if range_sel != st.session_state.bills_range_sel:
            st.session_state.bills_range_sel = range_sel
            st.session_state.bills_date_from = (
                data_min if range_sel == "所有"
                else today - timedelta(days=_range_delta[range_sel])
            )
            st.session_state.bills_date_to = today

        col_a, col_b = st.columns(2)
        date_from = col_a.date_input("起始日期", key="bills_date_from")
        date_to = col_b.date_input("結束日期", key="bills_date_to")

        mask = (
            (pd.to_datetime(bills_df["扣款時間"]).dt.date >= date_from)
            & (pd.to_datetime(bills_df["扣款時間"]).dt.date <= date_to)
        )
        filtered = bills_df[mask]

        st.caption(f"共 {len(filtered)} 筆紀錄（{date_from} ～ {date_to}），依服務彙整如下：")
        st.caption("勾選想加入「訂閱清單」的服務，再點擊下方按鈕。")

        summary_df = _build_billing_summary(filtered)
        edited_summary = st.data_editor(
            summary_df.drop(columns=["subscription_id"]),
            column_config={
                "選取": st.column_config.CheckboxColumn("選取", default=False),
                "已在訂閱清單": st.column_config.CheckboxColumn("已在訂閱清單", disabled=True),
            },
            disabled=["服務名稱", "帳單次數", "狀態", "最近帳單", "金額", "幣別", "郵件主旨"],
            hide_index=True,
            use_container_width=True,
            key="billing_summary_editor",
        )

        selected_names = edited_summary[edited_summary["選取"]]["服務名稱"].tolist()
        n_sel = len(selected_names)
        btn_label = f"📋 加入訂閱清單（已選 {n_sel} 項）" if n_sel else "📋 加入訂閱清單"

        if st.button(btn_label, disabled=n_sel == 0, type="primary"):
            sel_ids = (
                summary_df[summary_df["服務名稱"].isin(selected_names)]["subscription_id"]
                .dropna().astype(int).tolist()
            )
            for sid in sel_ids:
                activate_subscription(sid)
            load_subscriptions.clear()
            st.success(f"已確認 {len(sel_ids)} 項服務加入訂閱清單（啟用狀態）")
            st.rerun()

    # ── Proposed changes review ───────────────────────────────────────────────
    if st.session_state.proposed_changes:
        st.divider()
        st.subheader("🔍 訂閱金額異動審查")
        st.warning(
            f"Gmail 掃描偵測到 **{len(st.session_state.proposed_changes)}** 項訂閱扣款金額與清單不符，"
            "請逐筆確認是否更新。"
        )
        for i, chg in enumerate(list(st.session_state.proposed_changes)):
            cols = st.columns([3, 2, 2, 3, 1, 1])
            cols[0].write(f"**{chg['服務名稱']}**")
            cols[1].write(f"{chg['目前金額']} {chg['目前幣別']}")
            cols[2].write(f"→ **{chg['新金額']} {chg['新幣別']}**")
            cols[3].caption(
                chg["郵件主旨"][:50] + "…" if len(chg["郵件主旨"]) > 50 else chg["郵件主旨"]
            )
            if cols[4].button("✅", key=f"approve_{i}", help="更新為新金額"):
                apply_proposed_change(chg["sub_id"], chg["新金額"], chg["新幣別"])
                st.session_state.proposed_changes.pop(i)
                load_subscriptions.clear()
                st.rerun()
            if cols[5].button("❌", key=f"reject_{i}", help="略過，不更新"):
                st.session_state.proposed_changes.pop(i)
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
