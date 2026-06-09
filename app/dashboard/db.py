from datetime import date as _date

import pandas as pd
import streamlit as st
from sqlalchemy import and_, func, select

from database.models import BillingCycle, BillingRecord, Subscription
from database.session import SessionLocal


@st.cache_data(ttl=60)
def load_subscriptions() -> pd.DataFrame:
    with SessionLocal() as db:
        subs = db.execute(select(Subscription)).scalars().all()
        if not subs:
            return pd.DataFrame()

        # Latest billing record per subscription — subquery JOIN (2 queries total)
        latest_sq = (
            select(
                BillingRecord.subscription_id,
                func.max(BillingRecord.billed_at).label("max_at"),
            )
            .group_by(BillingRecord.subscription_id)
            .subquery()
        )
        latest_rows = db.execute(
            select(
                BillingRecord.subscription_id,
                BillingRecord.raw_subject,
                latest_sq.c.max_at,
            )
            .join(
                latest_sq,
                and_(
                    BillingRecord.subscription_id == latest_sq.c.subscription_id,
                    BillingRecord.billed_at == latest_sq.c.max_at,
                )
            )
        ).all()

        max_at = {r.subscription_id: r.max_at for r in latest_rows}
        subject: dict[int, str] = {}
        for r in latest_rows:
            subject.setdefault(r.subscription_id, r.raw_subject or "")

        return pd.DataFrame([
            {
                "id": r.id,
                "名稱": r.name,
                "服務商": r.provider or "",
                "週期": r.billing_cycle.value,
                "金額": float(r.amount),
                "幣別": r.currency,
                "最近扣款": max_at.get(r.id),
                "郵件主旨": subject.get(r.id, ""),
                "下次扣款": r.next_billing_date,
                "訂閱開始": r.subscribed_since,
                "啟用": r.is_active,
                "備註": r.note or "",
            }
            for r in subs
        ])


@st.cache_data(ttl=60)
def load_billing_records() -> pd.DataFrame:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                BillingRecord,
                Subscription.name.label("service_name"),
                Subscription.billing_cycle.label("sub_billing_cycle"),
            )
            .join(Subscription, BillingRecord.subscription_id == Subscription.id)
            .order_by(BillingRecord.billed_at.desc())
        ).all()
        return pd.DataFrame([
            {
                "id": r.BillingRecord.id,
                "subscription_id": r.BillingRecord.subscription_id,
                "服務名稱": r.service_name,
                "金額": float(r.BillingRecord.amount),
                "幣別": r.BillingRecord.currency,
                "扣款時間": r.BillingRecord.billed_at,
                "類型": "一次性消費" if r.sub_billing_cycle == BillingCycle.one_time else "訂閱費",
                "來源": r.BillingRecord.source.value,
                "郵件主旨": r.BillingRecord.raw_subject or "",
            }
            for r in rows
        ])


def create_subscription(data: dict) -> int:
    with SessionLocal() as db:
        sub = Subscription(
            name=data["name"],
            provider=data.get("provider") or None,
            billing_cycle=BillingCycle(data["billing_cycle"]),
            amount=data["amount"],
            currency=data["currency"],
            subscribed_since=data.get("subscribed_since") or None,
            next_billing_date=data.get("next_billing_date"),
            is_active=data.get("is_active", True),
            note=data.get("note") or None,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub.id


def update_subscription(sub_id: int, data: dict) -> None:
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if sub is None:
            return
        sub.name = data["name"]
        sub.provider = data.get("provider") or None
        sub.billing_cycle = BillingCycle(data["billing_cycle"])
        sub.amount = data["amount"]
        sub.currency = data["currency"]
        sub.subscribed_since = data.get("subscribed_since") or None
        sub.next_billing_date = data.get("next_billing_date")
        sub.is_active = data.get("is_active", True)
        sub.note = data.get("note") or None
        db.commit()


def update_subscription_note(sub_id: int, note: str | None) -> None:
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if sub is not None:
            sub.note = note or None
            db.commit()


def delete_subscription(sub_id: int) -> None:
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if sub is not None:
            db.delete(sub)
            db.commit()


def activate_subscription(sub_id: int) -> None:
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if sub is not None and not sub.is_active:
            sub.is_active = True
            db.commit()


def deactivate_subscription(sub_id: int) -> None:
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if sub is not None and sub.is_active:
            sub.is_active = False
            db.commit()


def mark_non_subscription(sub_id: int) -> None:
    """Mark as one-time purchase and deactivate."""
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if sub is not None:
            sub.billing_cycle = BillingCycle.one_time
            sub.is_active = False
            db.commit()


def apply_proposed_change(sub_id: int, amount: float, currency: str) -> None:
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if sub is not None:
            sub.amount = amount
            sub.currency = currency
            db.commit()


def monthly_spend_df() -> pd.DataFrame:
    df = load_billing_records()
    if df.empty:
        return df
    df = df.copy()
    df["月份"] = pd.to_datetime(df["扣款時間"]).dt.to_period("M").astype(str)
    return df.groupby(["月份", "幣別"])["金額"].sum().reset_index()
