# Weekday tiffin ledger

Owner console for a home-style weekday lunch (tiffin) service. Customers subscribe to a monthly plan, pause for travel or festivals, and are billed only for weekdays they were actually served.

Stack: **Python 3.12**, **Flask**, **HTML/CSS**, **MongoDB Atlas** (or `mongomock` for a local demo).

## Billing rule

```
bill = monthly_plan_price × (weekdays_served / weekdays_in_that_month)
```

A day is served only if it is Monday–Friday, on or after the subscribe date, and not covered by a pause. Weekends are never billed.

Example (September 2026 has 22 weekdays): ₹3000 plan, paused Mon–Fri 14–18 Sep → **17 / 22 → ₹2318.18**.

## Setup

1. Install Python 3.12+.
2. Clone this repository and create a virtual environment:

```powershell
cd tiffin-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Copy environment settings:

```powershell
copy .env.example .env
```

4. Put your **MongoDB Atlas** URI in `.env`:

```
MONGODB_URI=mongodb+srv://USER:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=tiffin_service
SECRET_KEY=change-me
PORT=5000
```

Atlas checklist:

- Create a free M0 cluster.
- Create a database user.
- Network Access → allow your IP, or `0.0.0.0/0` for a laptop demo.
- Connect → Drivers → copy the `mongodb+srv://` string.
- If the password contains `@`, `#`, or `%`, URL-encode it (`@` → `%40`).

On first run the app creates database `tiffin_service` and collections `plans` and `customers`, and seeds two plans (`Home-style veg` ₹3000, `Home-style plus` ₹4200).

Local demo without Atlas (data is in-memory and is lost when the process stops):

```
MONGODB_URI=mongomock://demo
```

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000

The owner can:

- Subscribe a customer (name, 10-digit phone, plan, start date).
- Pause (date range, or open-ended until resume).
- Resume (billing starts again on that date).
- Look up by phone.
- See who is **active** vs **paused** today.
- Open the month-end bill sheet.

## Debug

| Symptom | What to check |
| --- | --- |
| `Set MONGODB_URI in .env` | `.env` is missing or empty. Copy `.env.example`. |
| Atlas timeout / `ServerSelectionTimeoutError` | Cluster paused, wrong URI, or Network Access does not include this machine. |
| `Authentication failed` | Database username/password. Encode special characters in the password. |
| `Phone must be a 10-digit mobile number` | Strip spaces; `+91` and a leading `0` are accepted and normalised. |
| Duplicate phone | One subscription per phone. |
| `Already paused` | Resume before starting another open pause. |
| Flask debug double POST / empty mongomock data | `app.py` runs with `use_reloader=False` so the debugger does not fork a second in-memory database. |
| Wrong bill | Only weekdays count. Confirm pause dates and subscribe date. Optional: `GET /lookup?phone=...&as_of=YYYY-MM-DD`. |

Flask debug is on when you run `python app.py`. Interactive debugger PIN is printed in the terminal.

Tests (no Atlas required):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

## API endpoints

HTML forms use `application/x-www-form-urlencoded`. Flash errors redirect back to `/`. Optional `as_of=YYYY-MM-DD` on GET routes freezes “today” for status and current-month bills.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Owner dashboard: subscribe/pause/resume forms, active vs paused, this month’s bills. |
| `POST` | `/subscribe` | Start a plan. Body: `name`, `phone`, `plan_name`, `subscribed_on` (`YYYY-MM-DD`). |
| `POST` | `/pause` | Pause deliveries. Body: `phone`, `start`, optional `end`. Omit `end` to pause until resume. |
| `POST` | `/resume` | Resume deliveries. Body: `phone`, `on`. Last paused day is the day before `on`. |
| `GET` | `/lookup` | Customer by phone. Query: `phone` (required), `as_of` (optional). |
| `GET` | `/bills` | Month-end sheet. Query: `year`, `month` (default: current). |
| `GET` | `/health` | JSON `{ "ok": true }` after a MongoDB ping. |
| `GET` | `/static/style.css` | Stylesheet. |

## Project layout

```
billing.py      # weekday / pause / pro-rate rules (no database)
store.py        # MongoDB Atlas (or mongomock) persistence
app.py          # Flask owner console
templates/      # HTML
static/         # CSS
test_*.py       # unit and Flask tests
.env.example    # Atlas / mongomock settings
```

## Evaluation files

- `README.md` — this file
- `REASONING.md` — design, tests, and fixes
- `AI_LOGS.md` — Cursor conversation transcript, copied as-is
