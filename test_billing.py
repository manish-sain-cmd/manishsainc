from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from billing import (
    Pause,
    Subscription,
    normalize_phone,
    pause_subscription,
    prorate_bill,
    resume_subscription,
    served_weekdays,
    weekdays_in_month,
)


def sub(
    subscribed_on: date = date(2026, 9, 1),
    pauses: list[Pause] | None = None,
    price: str = "3000.00",
) -> Subscription:
    return Subscription(
        phone="9876543210",
        name="Asha",
        plan_name="Home-style veg",
        monthly_price=Decimal(price),
        subscribed_on=subscribed_on,
        pauses=pauses or [],
    )


class PhoneLookupTests(unittest.TestCase):
    def test_keeps_ten_digit_mobile(self):
        self.assertEqual(normalize_phone("98765 43210"), "9876543210")

    def test_strips_india_country_code(self):
        self.assertEqual(normalize_phone("+91-9876543210"), "9876543210")

    def test_rejects_short_numbers(self):
        with self.assertRaises(ValueError):
            normalize_phone("12345")


class PauseResumeTests(unittest.TestCase):
    def test_open_pause_covers_later_days(self):
        pauses = pause_subscription([], date(2026, 9, 10))
        self.assertTrue(pauses[0].covers(date(2026, 9, 15)))
        self.assertFalse(pauses[0].covers(date(2026, 9, 9)))

    def test_cannot_pause_twice_without_resume(self):
        paused = pause_subscription([], date(2026, 9, 10))
        with self.assertRaises(ValueError):
            pause_subscription(paused, date(2026, 9, 12))

    def test_resume_closes_pause_the_day_before(self):
        paused = pause_subscription([], date(2026, 9, 10))
        resumed = resume_subscription(paused, date(2026, 9, 13))
        self.assertEqual(resumed[0].end, date(2026, 9, 12))
        self.assertFalse(resumed[0].covers(date(2026, 9, 13)))

    def test_resume_same_day_drops_empty_pause(self):
        paused = pause_subscription([], date(2026, 9, 10))
        resumed = resume_subscription(paused, date(2026, 9, 10))
        self.assertEqual(resumed, [])

    def test_resume_when_not_paused_fails(self):
        with self.assertRaises(ValueError):
            resume_subscription([], date(2026, 9, 10))

    def test_dated_pause_does_not_block_after_end(self):
        pauses = pause_subscription([], date(2026, 9, 10), date(2026, 9, 12))
        self.assertTrue(pauses[0].covers(date(2026, 9, 12)))
        self.assertFalse(pauses[0].covers(date(2026, 9, 13)))


class ProratedBillTests(unittest.TestCase):
    def test_full_month_no_pause_pays_full_plan(self):
        bill = prorate_bill(sub(), 2026, 9)
        self.assertEqual(bill["weekdays_in_month"], 22)
        self.assertEqual(bill["days_served"], 22)
        self.assertEqual(bill["amount"], Decimal("3000.00"))

    def test_paused_weekdays_are_not_billed(self):
        customer = sub(pauses=[Pause(date(2026, 9, 14), date(2026, 9, 18))])
        bill = prorate_bill(customer, 2026, 9)
        # 14–18 Sep 2026 is Mon–Fri: five served days dropped.
        self.assertEqual(bill["days_served"], 17)
        self.assertEqual(bill["amount"], Decimal("2318.18"))

    def test_weekend_inside_pause_does_not_change_weekday_count(self):
        customer = sub(pauses=[Pause(date(2026, 9, 19), date(2026, 9, 20))])
        bill = prorate_bill(customer, 2026, 9)
        self.assertEqual(bill["days_served"], 22)
        self.assertEqual(bill["amount"], Decimal("3000.00"))

    def test_mid_month_subscribe_skips_earlier_weekdays(self):
        customer = sub(subscribed_on=date(2026, 9, 16))
        served = served_weekdays(customer, 2026, 9)
        self.assertEqual(served[0], date(2026, 9, 16))
        bill = prorate_bill(customer, 2026, 9)
        self.assertEqual(bill["days_served"], 11)
        self.assertEqual(bill["amount"], Decimal("1500.00"))

    def test_open_pause_stops_delivery_until_resumed(self):
        paused = pause_subscription([], date(2026, 9, 21))
        customer = sub(pauses=paused)
        bill = prorate_bill(customer, 2026, 9)
        self.assertEqual(bill["days_served"], 14)

        resumed = resume_subscription(paused, date(2026, 9, 23))
        customer = sub(pauses=resumed)
        bill = prorate_bill(customer, 2026, 9)
        self.assertEqual(bill["days_served"], 20)

    def test_weekdays_helper_skips_saturday_sunday(self):
        days = weekdays_in_month(2026, 9)
        self.assertTrue(all(d.weekday() < 5 for d in days))
        self.assertNotIn(date(2026, 9, 19), days)

    def test_status_active_versus_paused(self):
        customer = sub(pauses=[Pause(date(2026, 9, 10), None)])
        self.assertEqual(customer.status_on(date(2026, 9, 9)), "active")
        self.assertEqual(customer.status_on(date(2026, 9, 10)), "paused")


if __name__ == "__main__":
    unittest.main()
