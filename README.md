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

On macOS/Linux / GitHub Codespaces:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Copy environment settings:

```powershell
copy .env.example .env
```

```bash
cp .env.example .env
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
- Network Access → allow your IP, or `0.0.0.0/0` for a laptop / Codespaces demo.
- Connect → Drivers → copy the `mongodb+srv://` string.
- If the password contains `@`, `#`, or `%`, URL-encode it (`@` → `%40`).

On first run the app creates database `tiffin_service` and collections `users`, `plans`, and `customers`, and seeds two plans (`Home-style veg` ₹3000, `Home-style plus` ₹4200).

Local demo without Atlas (data is in-memory and is lost when the process stops):

```
MONGODB_URI=mongomock://demo
```

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

```bash
python app.py
```

Open http://127.0.0.1:5000

1. Landing page (public).
2. **Register** an owner, then **log in**.
3. Open **Ledger** (`/app`): subscribe, pause, resume.
4. **Search / sort / paginate** customers and bills.
5. Look up by phone. See active vs paused.

## Debug

| Symptom | What to check |
| --- | --- |
| `Set MONGODB_URI in .env` | `.env` is missing or empty. Copy `.env.example`. |
| Atlas timeout | Cluster paused, wrong URI, or Network Access does not include this machine. |
| `Authentication failed` (Mongo) | Database username/password. Encode special characters. |
| `Login required` / redirect to login | Register first. REST calls need the session cookie from `/api/login`. |
| `Invalid email or password` | Owner account, not the customer phone. |
| `Phone must be a 10-digit mobile number` | `+91` and a leading `0` are accepted. |
| Duplicate phone / email | Unique indexes on `customers.phone` and `users.email`. |
| `Already paused` | Resume before starting another open pause. |
| Wrong bill | Only weekdays count. Try `as_of=YYYY-MM-DD` on GET routes. |

Tests (no Atlas required):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

## REST API endpoints

JSON body is `application/json`. Authenticated routes need a session cookie from `POST /api/register` or `POST /api/login`.

Query helpers on list routes: `q` (search), `sort`, `order` (`asc`\|`desc`), `page`, `per_page` (max 50). Optional `as_of=YYYY-MM-DD` freezes “today”.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/register` | no | Body: `name`, `email`, `password`. Creates owner and logs in. |
| `POST` | `/api/login` | no | Body: `email`, `password`. |
| `POST` | `/api/logout` | no | Clears session. |
| `GET` | `/api/me` | yes | Current owner. |
| `GET` | `/api/plans` | yes | Seeded monthly plans. |
| `GET` | `/api/customers` | yes | Search / sort / paginate. Extra: `status=active\|paused`. |
| `POST` | `/api/customers` | yes | Subscribe. Body: `name`, `phone`, `plan_name`, `subscribed_on`. |
| `GET` | `/api/customers/<phone>` | yes | Customer + this month’s bill. |
| `POST` | `/api/customers/<phone>/pause` | yes | Body: `start`, optional `end`. |
| `POST` | `/api/customers/<phone>/resume` | yes | Body: `on`. |
| `GET` | `/api/bills` | yes | Month sheet. Extra: `year`, `month`. |
| `GET` | `/health` | no | `{ "ok": true }` after Mongo ping. |

## HTML pages

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Landing page (product, audience, features, next three). |
| `GET/POST` | `/register`, `/login` | Owner accounts. |
| `POST` | `/logout` | End session. |
| `GET` | `/app` | Ledger UI over the APIs (search, sort, pagination). |
| `POST` | `/subscribe`, `/pause`, `/resume` | Same core operations as HTML forms. |
| `GET` | `/lookup` | Customer by phone. |
| `GET` | `/bills` | Month-end sheet with search / sort / pages. |

## Project layout

```
billing.py      weekday / pause / pro-rate rules
store.py        MongoDB Atlas (users, plans, customers)
app.py          Flask UI + REST
templates/      HTML
static/         CSS
test_*.py       tests
.env.example    Atlas / mongomock
```

## Evaluation files

- `README.md` — this file
- `REASONING.md` — design, tests, and fixes
- `AI_LOGS.md` — Cursor conversation transcript, copied as-is
