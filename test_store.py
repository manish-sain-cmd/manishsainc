from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from mongomock import MongoClient

from store import TiffinStore


class StoreFlowTests(unittest.TestCase):
    def setUp(self):
        self.store = TiffinStore(MongoClient().tiffin)
        self.store.seed_plans()

    def test_subscribe_pause_resume_and_prorated_bill(self):
        self.store.subscribe("Asha", "9876543210", "Home-style veg", date(2026, 9, 1))
        self.store.pause("9876543210", date(2026, 9, 14), date(2026, 9, 18))
        bill = self.store.bill("9876543210", 2026, 9)
        self.assertEqual(bill["days_served"], 17)
        self.assertEqual(bill["amount"], Decimal("2318.18"))

        self.store.pause("9876543210", date(2026, 9, 21))
        self.assertEqual(self.store.status("9876543210", date(2026, 9, 21))["status"], "paused")
        self.assertEqual(self.store.status("9876543210", date(2026, 9, 20))["status"], "active")

        self.store.resume("9876543210", date(2026, 9, 23))
        self.assertEqual(self.store.status("9876543210", date(2026, 9, 23))["status"], "active")
        bill = self.store.bill("9876543210", 2026, 9)
        self.assertEqual(bill["days_served"], 15)

    def test_lookup_by_phone_and_status_lists(self):
        self.store.subscribe("Asha", "+91 9876543210", "Home-style veg", date(2026, 9, 1))
        self.store.subscribe("Ravi", "9123456780", "Home-style plus", date(2026, 9, 1))
        self.store.pause("9123456780", date(2026, 9, 10))

        found = self.store.get_customer("98765 43210")
        self.assertEqual(found["name"], "Asha")

        active = self.store.list_by_status(date(2026, 9, 17), "active")
        paused = self.store.list_by_status(date(2026, 9, 17), "paused")
        self.assertEqual([c["name"] for c in active], ["Asha"])
        self.assertEqual([c["name"] for c in paused], ["Ravi"])

    def test_duplicate_phone_is_rejected(self):
        self.store.subscribe("Asha", "9876543210", "Home-style veg", date(2026, 9, 1))
        with self.assertRaises(ValueError):
            self.store.subscribe("Other", "9876543210", "Home-style plus", date(2026, 9, 2))


if __name__ == "__main__":
    unittest.main()
