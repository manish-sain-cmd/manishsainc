# Reasoning

## Problem

A tiffin owner sells a monthly weekday lunch plan. Customers pause for travel or festivals and must not pay for those days. At month-end the bill is the plan price pro-rated for days actually delivered. The owner looks people up by phone and needs to see who is active versus paused.

The brief asked to get subscribe, pause/resume, and the pro-rated bill right first, then lookups. The stack requested later was Flask, Python, HTML, and MongoDB Atlas.

## Domain first

Billing is a calendar rule, not a database rule. It lives in `billing.py` so it can be tested without Atlas.

- Delivery days are Monday–Friday only.
- A day is served only if it is on or after `subscribed_on` and not covered by a pause.
- Formula: `monthly_price × (served_weekdays / weekdays_in_that_month)`.
- A full month with no pauses therefore equals the plan price.
- Pause with an end date is a closed range (inclusive). Pause without an end stays open until resume.
- Resume on date D means the last paused day is D−1; D is billed again if it is a weekday.

Phone numbers are normalised to 10 digits (`+91` and a leading `0` stripped) so lookup is reliable.

Persistence (`store.py`) stores customers and pause history in MongoDB. Plans are seeded (`Home-style veg` ₹3000, `Home-style plus` ₹4200). One phone maps to one subscription.

Flask (`app.py` + HTML templates) is the owner console: forms for subscribe/pause/resume, lists for active/paused, phone lookup, month-end sheet.

## What we did not do

- Weekend delivery (the story is weekday lunch).
- Payment capture / GST — the owner asked for the bill amount, not a payment gateway.
- Per-day menu — out of scope for billing.

## Testing

Unit tests in `test_billing.py` lock the calendar math, including September 2026 (22 weekdays):

- Full month, no pause → ₹3000.00
- Pause 14–18 Sep (Mon–Fri) → 17/22 → ₹2318.18
- Weekend-only pause → still full price
- Subscribe on 16 Sep → 11/22 → ₹1500.00
- Open pause then resume
- Active vs paused status
- Phone normalisation

`test_store.py` uses mongomock for subscribe → pause → resume → bill and duplicate-phone rejection.

`test_app.py` hits Flask routes with the test client.

Command: `python -m unittest discover -v` — 20 tests, all passing.

The running app was checked with curl against `http://127.0.0.1:5000`: subscribe Asha, pause 14–18 Sep, lookup showed `paused` and ₹2318.18; Ravi paused from 10 Sep showed 7/22 weekdays.

## Issues and fixes

1. **No Python / no Git on the Windows machine.** Python 3.12 was installed with winget so the app and tests could run.
2. **MongoDB Atlas URI not available while building.** Core tests use mongomock. `MONGODB_URI=mongomock://demo` runs a local demo. Production path remains Atlas via `.env`.
3. **Flask debug reloader.** The reloader forks a second process. With mongomock that meant two empty in-memory databases and double POST handling (`Already paused`). Fix: `use_reloader=False`.
4. **Browser submit was blocked** in the automated browser, so the same flow was verified with curl instead of clicking Start plan.
5. **PowerShell `Invoke-WebRequest`** failed in non-interactive mode; switched to `curl.exe`.
6. **Unique phone** is a MongoDB unique index; duplicates raise a clear error.
7. **`.env` is gitignored** so Atlas passwords are not committed.

## How to show this to a company

Public GitHub repo with these three files in the **root**:

- `README.md` — setup, run, debug, endpoints
- `REASONING.md` — this file
- `AI_LOGS.md` — Cursor transcript copied as-is (do not edit)
