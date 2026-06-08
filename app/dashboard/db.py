import pandas as pd
import streamlit as st

from database.models import BillingRecord, Subscription
from database.session import SessionLocal
from sqlalchemy import select


@st.cache_data(ttl=60)
def load_subscriptions() -> pd.DataFrame:
    with SessionLocal() as db:
        rows = db.execute(select(Subscription)).scalars().all()
        return pd.DataFrame([
            {
                "id": r.id,
                "名稱": r.name,
                "服務商": r.provider or "",
                "週期": r.billing_cycle.value,
                "金額": float(r.amount),
                "幣別": r.currency,
                "下次扣款": r.next_billing_date,
                "啟用": r.is_active,
                "備註": r.note or "",
            }
            for r in rows
        ])


@st.cache_data(ttl=60)
def load_billing_records() -> pd.DataFrame:
    with SessionLocal() as db:
        rows = db.execute(
            select(BillingRecord, Subscription.name.label("service_name"))
            .join(Subscription, BillingRecord.subscription_id == Subscription.id)
            .order_by(BillingRecord.billed_at.desc())
        ).all()
        return pd.DataFrame([
            {
                "id": r.BillingRecord.id,
                "服務名稱": r.service_name,
                "金額": float(r.BillingRecord.amount),
                "幣別": r.BillingRecord.currency,
                "扣款時間": r.BillingRecord.billed_at,
                "來源": r.BillingRecord.source.value,
                "郵件主旨": r.BillingRecord.raw_subject or "",
            }
            for r in rows
        ])


def monthly_spend_df() -> pd.DataFrame:
    df = load_billing_records()
    if df.empty:
        return df
    df = df.copy()
    df["月份"] = pd.to_datetime(df["扣款時間"]).dt.to_period("M").astype(str)
    return df.groupby(["月份", "幣別"])["金額"].sum().reset_index()
