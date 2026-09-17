from __future__ import annotations

import os
import unittest

os.environ["MONGODB_URI"] = "mongomock://demo"
os.environ["SECRET_KEY"] = "test"

from app import create_app


class OwnerConsoleTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def _register(self):
        return self.client.post(
            "/register",
            data={"name": "Owner", "email": "owner@kitchen.test", "password": "secret1"},
            follow_redirects=True,
        )

    def test_landing_page_is_public(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Target audience", home.data)
        self.assertIn(b"Three features we would build next", home.data)

    def test_subscribe_pause_and_month_bill(self):
        self._register()
        ledger = self.client.get("/app")
        self.assertEqual(ledger.status_code, 200)
        self.assertIn(b"Subscribe", ledger.data)

        self.client.post(
            "/subscribe",
            data={
                "name": "Asha",
                "phone": "9876543210",
                "plan_name": "Home-style veg",
                "subscribed_on": "2026-09-01",
            },
            follow_redirects=True,
        )
        self.client.post(
            "/pause",
            data={"phone": "9876543210", "start": "2026-09-14", "end": "2026-09-18"},
            follow_redirects=True,
        )
        lookup = self.client.get("/lookup?phone=9876543210&as_of=2026-09-17")
        self.assertEqual(lookup.status_code, 200)
        self.assertIn(b"paused", lookup.data)
        self.assertIn(b"2318.18", lookup.data)

        bills = self.client.get("/bills?year=2026&month=9")
        self.assertIn(b"Asha", bills.data)
        self.assertIn(b"17 / 22", bills.data)

        search = self.client.get("/app?q=Asha&sort=name&order=asc&page=1")
        self.assertIn(b"Asha", search.data)

    def test_rest_register_search_and_bill(self):
        created = self.client.post(
            "/api/register",
            json={"name": "Rina", "email": "rina@kitchen.test", "password": "secret1"},
        )
        self.assertEqual(created.status_code, 201)
        self.client.post(
            "/api/customers",
            json={
                "name": "Asha",
                "phone": "9876543210",
                "plan_name": "Home-style veg",
                "subscribed_on": "2026-09-01",
            },
        )
        listed = self.client.get("/api/customers?q=98765&sort=name&order=asc&page=1&per_page=10")
        payload = listed.get_json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["phone"], "9876543210")
        bill = self.client.get("/api/bills?year=2026&month=9&sort=amount&order=desc")
        self.assertEqual(bill.get_json()["items"][0]["days_served"], 22)


if __name__ == "__main__":
    unittest.main()
