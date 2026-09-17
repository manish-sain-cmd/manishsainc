"""Owner console for a weekday tiffin service."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for

from store import connect

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "tiffin-dev-secret")

    uri = os.environ.get("MONGODB_URI", "").strip()
    db_name = os.environ.get("MONGODB_DB", "tiffin_service")
    if not uri:
        raise RuntimeError("Set MONGODB_URI in .env to your MongoDB Atlas connection string")

    client, store = connect(uri, db_name)
    app.tiffin_store = store
    app.mongo_client = client

    def today() -> date:
        raw = request.args.get("as_of") or request.form.get("as_of")
        if raw:
            return date.fromisoformat(raw)
        return date.today()

    def parse_day(value: str, field: str) -> date:
        if not value:
            raise ValueError(f"{field} is required")
        return date.fromisoformat(value)

    @app.context_processor
    def inject_today():
        now = today()
        return {"today": now.isoformat(), "today_date": now}

    @app.get("/")
    def dashboard():
        now = today()
        customers = store.list_by_status(now)
        active = [c for c in customers if c["status"] == "active"]
        paused = [c for c in customers if c["status"] == "paused"]
        bills = store.month_end_bills(now.year, now.month)
        total = sum(Decimal(str(b["amount"])) for b in bills)
        return render_template(
            "dashboard.html",
            plans=store.list_plans(),
            customers=customers,
            active=active,
            paused=paused,
            bills=bills,
            total=total,
            year=now.year,
            month=now.month,
        )

    @app.post("/subscribe")
    def subscribe():
        try:
            store.subscribe(
                name=request.form.get("name", ""),
                phone=request.form.get("phone", ""),
                plan_name=request.form.get("plan_name", ""),
                subscribed_on=parse_day(request.form.get("subscribed_on", ""), "Start date"),
            )
            flash("Customer subscribed. Lunches will be billed only for weekdays served.", "ok")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/pause")
    def pause():
        try:
            end_raw = (request.form.get("end") or "").strip()
            store.pause(
                phone=request.form.get("phone", ""),
                start=parse_day(request.form.get("start", ""), "Pause from"),
                end=date.fromisoformat(end_raw) if end_raw else None,
            )
            flash("Pause saved. Those days will not be billed.", "ok")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/resume")
    def resume():
        try:
            store.resume(
                phone=request.form.get("phone", ""),
                on=parse_day(request.form.get("on", ""), "Resume date"),
            )
            flash("Deliveries resumed. Billing starts again from this date.", "ok")
        except Exception as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.get("/lookup")
    def lookup():
        phone = request.args.get("phone", "")
        now = today()
        try:
            customer = store.status(phone, now)
            bill = store.bill(customer["phone"], now.year, now.month)
            return render_template(
                "lookup.html",
                customer=customer,
                bill=bill,
                plans=store.list_plans(),
            )
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))

    @app.get("/bills")
    def bills():
        now = today()
        year = int(request.args.get("year", now.year))
        month = int(request.args.get("month", now.month))
        rows = store.month_end_bills(year, month)
        total = sum(Decimal(str(b["amount"])) for b in rows)
        return render_template("bills.html", bills=rows, total=total, year=year, month=month)

    @app.get("/health")
    def health():
        store.db.command("ping")
        return {"ok": True}

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=int(os.environ.get("PORT", "5000")))
