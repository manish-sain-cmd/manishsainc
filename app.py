"""Owner console for a weekday tiffin service."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from store import connect

load_dotenv()


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


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

    def current_owner():
        return session.get("owner")

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_owner():
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Login required"}), 401
                flash("Register or log in to open the ledger.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    @app.context_processor
    def inject_today():
        now = today()
        return {"today": now.isoformat(), "today_date": now, "owner": current_owner()}

    @app.get("/")
    def landing():
        return render_template("landing.html")

    @app.get("/register")
    def register():
        if current_owner():
            return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.post("/register")
    def register_post():
        try:
            owner = store.register_owner(
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
            )
            session["owner"] = owner
            flash("Account created. Welcome to the ledger.", "ok")
            return redirect(url_for("dashboard"))
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("register"))

    @app.get("/login")
    def login():
        if current_owner():
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/login")
    def login_post():
        try:
            session["owner"] = store.login_owner(
                request.form.get("email", ""),
                request.form.get("password", ""),
            )
            flash("Logged in.", "ok")
            return redirect(url_for("dashboard"))
        except Exception as exc:
            flash(str(exc), "error")
            return redirect(url_for("login"))

    @app.post("/logout")
    def logout():
        session.clear()
        flash("Logged out.", "ok")
        return redirect(url_for("landing"))

    @app.get("/app")
    @login_required
    def dashboard():
        now = today()
        q = request.args.get("q", "")
        status = request.args.get("status", "")
        sort = request.args.get("sort", "name")
        order = request.args.get("order", "asc")
        page = int(request.args.get("page", 1))
        listing = store.search_customers(now, q=q, status=status or None, sort=sort, order=order, page=page)
        all_customers = store.list_by_status(now)
        active = [c for c in all_customers if c["status"] == "active"]
        paused = [c for c in all_customers if c["status"] == "paused"]
        bills = store.month_end_bills(now.year, now.month)
        total = sum(Decimal(str(b["amount"])) for b in bills)
        return render_template(
            "dashboard.html",
            plans=store.list_plans(),
            listing=listing,
            active=active,
            paused=paused,
            bills=bills[:10],
            total=total,
            year=now.year,
            month=now.month,
            q=q,
            status_filter=status,
            sort=listing["sort"],
            order=listing["order"],
        )

    @app.post("/subscribe")
    @login_required
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
    @login_required
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
    @login_required
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
    @login_required
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
    @login_required
    def bills():
        now = today()
        year = int(request.args.get("year", now.year))
        month = int(request.args.get("month", now.month))
        listing = store.search_bills(
            year,
            month,
            q=request.args.get("q", ""),
            sort=request.args.get("sort", "name"),
            order=request.args.get("order", "asc"),
            page=int(request.args.get("page", 1)),
        )
        all_rows = store.month_end_bills(year, month)
        total = sum(Decimal(str(b["amount"])) for b in all_rows)
        return render_template(
            "bills.html",
            listing=listing,
            total=total,
            year=year,
            month=month,
            q=listing["q"],
            sort=listing["sort"],
            order=listing["order"],
        )

    def api_body():
        return request.get_json(silent=True) or {}

    @app.post("/api/register")
    def api_register():
        body = api_body()
        try:
            owner = store.register_owner(body.get("name", ""), body.get("email", ""), body.get("password", ""))
            session["owner"] = owner
            return jsonify({"owner": owner}), 201
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/login")
    def api_login():
        body = api_body()
        try:
            owner = store.login_owner(body.get("email", ""), body.get("password", ""))
            session["owner"] = owner
            return jsonify({"owner": owner})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 401

    @app.post("/api/logout")
    def api_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/me")
    @login_required
    def api_me():
        return jsonify({"owner": current_owner()})

    @app.get("/api/plans")
    @login_required
    def api_plans():
        return jsonify({"plans": store.list_plans()})

    @app.get("/api/customers")
    @login_required
    def api_customers():
        listing = store.search_customers(
            today(),
            q=request.args.get("q", ""),
            status=request.args.get("status") or None,
            sort=request.args.get("sort", "name"),
            order=request.args.get("order", "asc"),
            page=int(request.args.get("page", 1)),
            per_page=int(request.args.get("per_page", 10)),
        )
        return jsonify(_jsonable(listing))

    @app.post("/api/customers")
    @login_required
    def api_subscribe():
        body = api_body()
        try:
            customer = store.subscribe(
                body.get("name", ""),
                body.get("phone", ""),
                body.get("plan_name", ""),
                parse_day(body.get("subscribed_on", ""), "Start date"),
            )
            return jsonify(_jsonable(customer)), 201
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/customers/<phone>")
    @login_required
    def api_get_customer(phone):
        try:
            now = today()
            customer = store.status(phone, now)
            bill = store.bill(customer["phone"], now.year, now.month)
            return jsonify(_jsonable({"customer": customer, "bill": bill}))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/customers/<phone>/pause")
    @login_required
    def api_pause(phone):
        body = api_body()
        try:
            end_raw = (body.get("end") or "").strip() if isinstance(body.get("end"), str) else body.get("end")
            saved = store.pause(
                phone,
                parse_day(body.get("start", ""), "Pause from"),
                date.fromisoformat(end_raw) if end_raw else None,
            )
            return jsonify(_jsonable(saved))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/customers/<phone>/resume")
    @login_required
    def api_resume(phone):
        body = api_body()
        try:
            saved = store.resume(phone, parse_day(body.get("on", ""), "Resume date"))
            return jsonify(_jsonable(saved))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/bills")
    @login_required
    def api_bills():
        now = today()
        year = int(request.args.get("year", now.year))
        month = int(request.args.get("month", now.month))
        listing = store.search_bills(
            year,
            month,
            q=request.args.get("q", ""),
            sort=request.args.get("sort", "name"),
            order=request.args.get("order", "asc"),
            page=int(request.args.get("page", 1)),
            per_page=int(request.args.get("per_page", 10)),
        )
        listing["year"] = year
        listing["month"] = month
        return jsonify(_jsonable(listing))

    @app.get("/health")
    def health():
        store.db.command("ping")
        return jsonify({"ok": True})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=int(os.environ.get("PORT", "5000")))
