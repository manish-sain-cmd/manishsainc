"""MongoDB Atlas persistence for tiffin customers, plans, and pauses."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from billing import (
    Pause,
    Subscription,
    normalize_phone,
    pause_subscription,
    prorate_bill,
    resume_subscription,
)

DEFAULT_PLANS = [
    {"name": "Home-style veg", "monthly_price": "3000.00"},
    {"name": "Home-style plus", "monthly_price": "4200.00"},
]


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_optional_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    return _as_date(value)


class TiffinStore:
    def __init__(self, db: Database):
        self.db = db
        self.plans: Collection = db.plans
        self.customers: Collection = db.customers
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.customers.create_index("phone", unique=True)
        self.plans.create_index("name", unique=True)

    def seed_plans(self) -> None:
        for plan in DEFAULT_PLANS:
            self.plans.update_one(
                {"name": plan["name"]},
                {"$setOnInsert": plan},
                upsert=True,
            )

    def list_plans(self) -> list[dict]:
        return list(self.plans.find({}, {"_id": 0}).sort("monthly_price", 1))

    def get_plan(self, name: str) -> dict:
        plan = self.plans.find_one({"name": name}, {"_id": 0})
        if not plan:
            raise ValueError("Unknown plan")
        return plan

    def subscribe(self, name: str, phone: str, plan_name: str, subscribed_on: date) -> dict:
        phone = normalize_phone(phone)
        display_name = name.strip()
        if not display_name:
            raise ValueError("Customer name is required")
        plan = self.get_plan(plan_name)
        doc = {
            "name": display_name,
            "phone": phone,
            "plan_name": plan["name"],
            "monthly_price": str(plan["monthly_price"]),
            "subscribed_on": subscribed_on.isoformat(),
            "pauses": [],
        }
        try:
            self.customers.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ValueError("A customer with this phone already has a plan") from exc
        return self.get_customer(phone)

    def get_customer(self, phone: str) -> dict:
        phone = normalize_phone(phone)
        doc = self.customers.find_one({"phone": phone}, {"_id": 0})
        if not doc:
            raise ValueError("No customer with that phone")
        return doc

    def _to_subscription(self, doc: dict) -> Subscription:
        pauses = [
            Pause(start=_as_date(p["start"]), end=_as_optional_date(p.get("end")))
            for p in doc.get("pauses", [])
        ]
        return Subscription(
            phone=doc["phone"],
            name=doc["name"],
            plan_name=doc["plan_name"],
            monthly_price=Decimal(str(doc["monthly_price"])),
            subscribed_on=_as_date(doc["subscribed_on"]),
            pauses=pauses,
        )

    def pause(self, phone: str, start: date, end: Optional[date] = None) -> dict:
        customer = self.get_customer(phone)
        pauses = [
            Pause(start=_as_date(p["start"]), end=_as_optional_date(p.get("end")))
            for p in customer.get("pauses", [])
        ]
        updated = pause_subscription(pauses, start, end)
        saved = self.customers.find_one_and_update(
            {"phone": customer["phone"]},
            {
                "$set": {
                    "pauses": [
                        {"start": p.start.isoformat(), "end": p.end.isoformat() if p.end else None}
                        for p in updated
                    ]
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return saved

    def resume(self, phone: str, on: date) -> dict:
        customer = self.get_customer(phone)
        pauses = [
            Pause(start=_as_date(p["start"]), end=_as_optional_date(p.get("end")))
            for p in customer.get("pauses", [])
        ]
        updated = resume_subscription(pauses, on)
        saved = self.customers.find_one_and_update(
            {"phone": customer["phone"]},
            {
                "$set": {
                    "pauses": [
                        {"start": p.start.isoformat(), "end": p.end.isoformat() if p.end else None}
                        for p in updated
                    ]
                }
            },
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        return saved

    def status(self, phone: str, on: date) -> dict:
        customer = self.get_customer(phone)
        sub = self._to_subscription(customer)
        return {
            **customer,
            "status": sub.status_on(on),
        }

    def list_by_status(self, on: date, status: Optional[str] = None) -> list[dict]:
        rows = []
        for doc in self.customers.find({}, {"_id": 0}).sort("name", 1):
            sub = self._to_subscription(doc)
            current = sub.status_on(on)
            if status and current != status:
                continue
            rows.append({**doc, "status": current})
        return rows

    def bill(self, phone: str, year: int, month: int) -> dict:
        customer = self.get_customer(phone)
        return prorate_bill(self._to_subscription(customer), year, month)

    def month_end_bills(self, year: int, month: int) -> list[dict]:
        bills = []
        for doc in self.customers.find({}, {"_id": 0}).sort("name", 1):
            bills.append(prorate_bill(self._to_subscription(doc), year, month))
        return bills


def connect(uri: str, db_name: str):
    if uri.startswith("mongomock"):
        from mongomock import MongoClient as MockClient

        client = MockClient()
    else:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    store = TiffinStore(client[db_name])
    store.seed_plans()
    return client, store
