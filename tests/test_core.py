"""Tests for everything that doesn't need the board. Run: python3 -m unittest discover tests"""
import email
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "python"))

import bus  # noqa: E402
import glyphs  # noqa: E402
import irishtime  # noqa: E402
from floors import apply_floor, floor, from_setup  # noqa: E402
from gmail import _snippet  # noqa: E402


def mail(sender, subject, snippet="", received_utc=None):
    return {"sender": sender, "subject": subject, "snippet": snippet, "received_utc": received_utc}


class Floors(unittest.TestCase):
    def test_failed_bill_is_always_today(self):
        m = mail("onlinetopups@prepaypower.ie", "PrepayPower Auto Top Up Failure Notification",
                 "we were unable to charge your card")
        self.assertEqual(apply_floor(m, "fyi"), "needs_today")
        self.assertEqual(apply_floor(m, "noise"), "needs_today")

    def test_successful_bill_is_left_to_gemma(self):
        m = mail("onlinetopups@prepaypower.ie", "Your top up was successful", "Thanks for topping up")
        self.assertEqual(apply_floor(m, "fyi"), "fyi")

    def test_delivery_today_only_from_carriers(self):
        self.assertEqual(floor(mail("noreply@fedex.com", "Your shipment is out for delivery today")), "needs_today")
        self.assertEqual(floor(mail("hello@shop.com", "Out for delivery today: our new range")), "noise")

    def test_rules_raise_but_never_lower(self):
        self.assertEqual(apply_floor(mail("news@site.com", "Weekly digest"), "needs_today"), "needs_today")

    def test_people_you_wrote_to_reach_soon(self):
        people = frozenset({"alex@example.ie", "hi@events.example"})
        self.assertEqual(apply_floor(mail("alex@example.ie", "Slide"), "noise", people), "soon")
        # A shared mailbox you once wrote to mostly sends bulk mail
        self.assertEqual(apply_floor(mail("hi@events.example", "Newsletter"), "noise", people), "noise")

    def test_invalid_model_answer_counts_as_fyi(self):
        self.assertEqual(apply_floor(mail("a@b.com", "x"), "invalid"), "fyi")


class SetupAlerts(unittest.TestCase):
    setup = datetime(2026, 10, 23, 3, 37, tzinfo=timezone.utc)

    def test_alert_naming_the_sloth_is_capped(self):
        m = mail("no-reply@accounts.google.com", "Security alert",
                 "If you didn't generate this password for Morning Sloth, someone might be using your account")
        self.assertTrue(from_setup(m, None))
        self.assertEqual(apply_floor(m, "needs_today", setup_at=None), "fyi")

    def test_alerts_just_before_setup_are_capped(self):
        m = mail("no-reply@accounts.google.com", "Security alert", "Your password was changed", "2026-10-23T03:29")
        self.assertEqual(apply_floor(m, "needs_today", setup_at=self.setup), "fyi")

    def test_alerts_long_after_setup_still_wake(self):
        m = mail("no-reply@accounts.google.com", "Security alert", "New sign-in on Windows", "2026-10-24T02:10")
        self.assertEqual(apply_floor(m, "needs_today", setup_at=self.setup), "needs_today")

    def test_other_senders_are_never_capped(self):
        m = mail("support@github.com", "Possible valid secrets detected", "Action needed", "2026-10-23T03:30")
        self.assertEqual(apply_floor(m, "needs_today", setup_at=self.setup), "needs_today")


class IrishTime(unittest.TestCase):
    def test_summer_time_until_last_sunday_of_october(self):
        # Clocks go back at 01:00 UTC on Sunday 25 October 2026
        before = datetime(2026, 10, 25, 0, 59, tzinfo=timezone.utc)
        after = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(irishtime.to_irish(before), datetime(2026, 10, 25, 1, 59))
        self.assertEqual(irishtime.to_irish(after), datetime(2026, 10, 25, 1, 0))

    def test_summer_time_starts_last_sunday_of_march(self):
        self.assertEqual(irishtime.to_irish(datetime(2027, 3, 28, 0, 59, tzinfo=timezone.utc)), datetime(2027, 3, 28, 0, 59))
        self.assertEqual(irishtime.to_irish(datetime(2027, 3, 28, 1, 0, tzinfo=timezone.utc)), datetime(2027, 3, 28, 2, 0))

    def test_other_timezones_convert(self):
        pdt = datetime.fromisoformat("2026-10-22T13:23:00-07:00")
        self.assertEqual(irishtime.to_irish(pdt), datetime(2026, 10, 22, 21, 23))


class Bus(unittest.TestCase):
    timetable = {
        "calendar": {"weekday": {"days": [1, 1, 1, 1, 1, 0, 0], "start": "20261001", "end": "20261231"},
                     "sunday": {"days": [0, 0, 0, 0, 0, 0, 1], "start": "20261001", "end": "20261231"}},
        "exceptions": [["weekday", "20261026", "2"], ["sunday", "20261026", "1"]],
        "departures": [["09:02:00", "weekday", "Newcastle"], ["09:29:30", "weekday", "Newcastle"],
                       ["09:25:00", "sunday", "Newcastle"], ["25:10:00", "weekday", "Newcastle"]],
    }

    def test_next_bus_on_a_weekday(self):
        self.assertEqual(bus.minutes_to_leave(self.timetable, datetime(2026, 10, 23, 9, 0)), 2)

    def test_missed_bus_moves_to_the_next(self):
        self.assertEqual(bus.minutes_to_leave(self.timetable, datetime(2026, 10, 23, 9, 3)), 26)

    def test_walk_time_skips_buses_you_cannot_reach(self):
        # 2 minutes to the 09:02 is not enough with a 5-minute walk
        self.assertEqual(bus.minutes_to_leave(self.timetable, datetime(2026, 10, 23, 9, 0), 5), 24)

    def test_bank_holiday_runs_the_sunday_timetable(self):
        self.assertEqual(bus.next_departure(self.timetable, datetime(2026, 10, 26, 9, 0)),
                         datetime(2026, 10, 26, 9, 25))

    def test_saturday_has_no_service_here(self):
        self.assertIsNone(bus.minutes_to_leave(self.timetable, datetime(2026, 10, 24, 9, 0)))

    def test_real_timetable_loads(self):
        real = bus.load(ROOT / "app" / "bus_timetable.json")
        self.assertEqual(real["stop_name"], "Castlegar GAA")
        self.assertIsNotNone(bus.next_departure(real, datetime(2026, 10, 27, 9, 0)))


class Glyphs(unittest.TestCase):
    def test_frame_is_13_by_8_levels(self):
        frame = glyphs.countdown(12)
        self.assertEqual(len(frame), 104)
        self.assertTrue(set(frame) <= set("01234567"))

    def test_single_digit_and_overflow(self):
        self.assertIn("7.7", glyphs.render(glyphs.countdown(4)))
        self.assertEqual(glyphs.countdown(150), glyphs.countdown(None))


class Snippet(unittest.TestCase):
    def test_prefers_plain_text_and_collapses_space(self):
        raw = (b"From: a@b.com\r\nSubject: hi\r\nMIME-Version: 1.0\r\n"
               b"Content-Type: multipart/alternative; boundary=x\r\n\r\n"
               b"--x\r\nContent-Type: text/html\r\n\r\n<p>html <b>body</b></p>\r\n"
               b"--x\r\nContent-Type: text/plain\r\n\r\nplain   body\r\n  here\r\n--x--\r\n")
        self.assertEqual(_snippet(email.message_from_bytes(raw)), "plain body here")

    def test_falls_back_to_html_without_tags(self):
        raw = b"Content-Type: text/html\r\n\r\n<style>p{}</style><p>Hello <b>there</b></p>"
        self.assertEqual(_snippet(email.message_from_bytes(raw)), "Hello there")


class Faces(unittest.TestCase):
    def test_every_face_fits_the_matrix(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import faces
        for name, rows in faces.FACES.items():
            self.assertEqual(len(rows), 8, name)
            self.assertTrue(all(len(r) == 13 for r in rows), name)


if __name__ == "__main__":
    unittest.main()
