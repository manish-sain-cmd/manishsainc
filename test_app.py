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

    def test_subscribe_pause_and_month_bill(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Subscribe", home.data)

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


if __name__ == "__main__":
    unittest.main()
