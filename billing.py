"""Weekday tiffin billing: monthly plans, pauses, pro-rated served days."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

MONEY = Decimal("0.01")


@dataclass(frozen=True)
class Pause:
    start: date
    end: Optional[date] = None  # None means still paused

    def covers(self, day: date) -> bool:
        if day < self.start:
            return False
        if self.end is None:
            return True
        return day <= self.end


@dataclass
class Subscription:
    phone: str
    name: str
    plan_name: str
    monthly_price: Decimal
    subscribed_on: date
    pauses: list[Pause] = field(default_factory=list)

    def is_paused_on(self, day: date) -> bool:
        return any(p.covers(day) for p in self.pauses)

    def status_on(self, day: date) -> str:
        if day < self.subscribed_on:
            return "not_started"
        return "paused" if self.is_paused_on(day) else "active"


def weekdays_in_month(year: int, month: int) -> list[date]:
    day = date(year, month, 1)
    days: list[date] = []
    while day.month == month:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def was_served(sub: Subscription, day: date) -> bool:
    if day.weekday() >= 5:
        return False
    if day < sub.subscribed_on:
        return False
    if sub.is_paused_on(day):
        return False
    return True


def served_weekdays(sub: Subscription, year: int, month: int) -> list[date]:
    return [d for d in weekdays_in_month(year, month) if was_served(sub, d)]


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def prorate_bill(sub: Subscription, year: int, month: int) -> dict:
    """Bill = monthly plan price × (served weekdays / weekdays in that month)."""
    deliverable = weekdays_in_month(year, month)
    served = served_weekdays(sub, year, month)
    total_days = len(deliverable)
    served_count = len(served)
    if total_days == 0:
        amount = Decimal("0.00")
    else:
        amount = money(sub.monthly_price * Decimal(served_count) / Decimal(total_days))
    return {
        "phone": sub.phone,
        "name": sub.name,
        "plan_name": sub.plan_name,
        "monthly_price": money(sub.monthly_price),
        "year": year,
        "month": month,
        "weekdays_in_month": total_days,
        "days_served": served_count,
        "days_not_served": total_days - served_count,
        "amount": amount,
        "served_dates": [d.isoformat() for d in served],
    }


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Phone must be a 10-digit mobile number")
    return digits


def pause_subscription(pauses: list[Pause], start: date, end: Optional[date] = None) -> list[Pause]:
    if end is not None and end < start:
        raise ValueError("Pause end cannot be before pause start")
    open_pause = next((p for p in pauses if p.end is None), None)
    if open_pause is not None:
        raise ValueError("Already paused — resume before starting another pause")
    return list(pauses) + [Pause(start=start, end=end)]


def resume_subscription(pauses: list[Pause], on: date) -> list[Pause]:
    updated: list[Pause] = []
    resumed = False
    for p in pauses:
        if p.end is None:
            if on < p.start:
                raise ValueError("Cannot resume before the pause started")
            last_paused = on - timedelta(days=1)
            if last_paused < p.start:
                # Resumed the same day it started: drop the empty pause.
                resumed = True
                continue
            updated.append(Pause(start=p.start, end=last_paused))
            resumed = True
        else:
            updated.append(p)
    if not resumed:
        raise ValueError("Not currently paused")
    return updated


def merge_pauses(pauses: Iterable[Pause]) -> list[Pause]:
    return list(pauses)
