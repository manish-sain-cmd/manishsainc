"""MongoDB Atlas persistence for tiffin customers, plans, and pauses."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

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
        self.users: Collection = db.users
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.customers.create_index("phone", unique=True)
        self.plans.create_index("name", unique=True)
        self.users.create_index("email", unique=True)

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

    def register_owner(self, name: str, email: str, password: str) -> dict:
        display = name.strip()
        mail = email.strip().lower()
        if not display:
            raise ValueError("Name is required")
        if "@" not in mail:
            raise ValueError("A valid email is required")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        doc = {
            "name": display,
            "email": mail,
            "password_hash": generate_password_hash(password),
        }
        try:
            self.users.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ValueError("An owner with this email already exists") from exc
        return {"name": display, "email": mail}

    def login_owner(self, email: str, password: str) -> dict:
        mail = email.strip().lower()
        doc = self.users.find_one({"email": mail})
        if not doc or not check_password_hash(doc.get("password_hash", ""), password):
            raise ValueError("Invalid email or password")
        return {"name": doc["name"], "email": doc["email"]}

    def search_customers(
        self,
        on: date,
        q: str = "",
        status: Optional[str] = None,
        sort: str = "name",
        order: str = "asc",
        page: int = 1,
        per_page: int = 10,
    ) -> dict:
        allowed = {"name", "phone", "status", "plan_name", "subscribed_on"}
        key = sort if sort in allowed else "name"
        rows = self.list_by_status(on, status if status in ("active", "paused") else None)
        needle = q.strip().lower()
        if needle:
            rows = [
                r
                for r in rows
                if needle in r["name"].lower()
                or needle in r["phone"]
                or needle in r["plan_name"].lower()
                or needle in r.get("status", "")
            ]
        reverse = order == "desc"
        rows.sort(key=lambda r: str(r.get(key, "")).lower(), reverse=reverse)
        return _page(rows, page, per_page, key, "desc" if reverse else "asc", q)

    def search_bills(
        self,
        year: int,
        month: int,
        q: str = "",
        sort: str = "name",
        order: str = "asc",
        page: int = 1,
        per_page: int = 10,
    ) -> dict:
        allowed = {"name", "phone", "plan_name", "days_served", "amount"}
        key = sort if sort in allowed else "name"
        rows = self.month_end_bills(year, month)
        needle = q.strip().lower()
        if needle:
            rows = [
                r
                for r in rows
                if needle in r["name"].lower() or needle in r["phone"] or needle in r["plan_name"].lower()
            ]
        reverse = order == "desc"

        def sort_val(row):
            value = row.get(key)
            if key in ("days_served", "amount"):
                return Decimal(str(value))
            return str(value).lower()

        rows.sort(key=sort_val, reverse=reverse)
        return _page(rows, page, per_page, key, "desc" if reverse else "asc", q)


def _page(rows: list, page: int, per_page: int, sort: str, order: str, q: str) -> dict:
    total = len(rows)
    page = max(1, int(page or 1))
    per_page = min(50, max(1, int(per_page or 10)))
    pages = max(1, (total + per_page - 1) // per_page)
    if page > pages:
        page = pages
    start = (page - 1) * per_page
    return {
        "items": rows[start : start + per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "sort": sort,
        "order": order,
        "q": q,
    }


def connect(uri: str, db_name: str):
    if uri.startswith("mongomock"):
        from mongomock import MongoClient as MockClient

        client = MockClient()
    else:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    store = TiffinStore(client[db_name])
    store.seed_plans()
    return client, store
