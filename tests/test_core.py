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
import live  # noqa: E402
from floors import apply_floor, explain, floor, from_setup  # noqa: E402
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


class Explain(unittest.TestCase):
    def test_names_the_rule_that_fired(self):
        webinar = {"sender": "x@y.com", "subject": "Webinar starting in 10 minutes", "snippet": ""}
        self.assertEqual(explain(webinar), ("needs_today", "an event is starting now"))
        friend = {"sender": "me@x.com", "subject": "hi", "snippet": ""}
        self.assertEqual(explain(friend, {"me@x.com"}), ("soon", "from someone you have written to"))
        self.assertEqual(explain(friend), ("noise", ""))


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


class BusWindow(unittest.TestCase):
    """The countdown shows from 09:00 up to, not including, 13:00; any other time it's just the sloth."""
    def at(self, hm):
        return datetime(2026, 10, 26, int(hm[:2]), int(hm[3:]))

    def test_countdown_runs_nine_to_one(self):
        for hm in ("09:00", "11:30", "12:59"):
            self.assertTrue(irishtime.between(self.at(hm), "09:00", "13:00"), hm)

    def test_sloth_only_outside_the_window(self):
        for hm in ("08:59", "13:00", "15:00", "23:59", "03:00"):
            self.assertFalse(irishtime.between(self.at(hm), "09:00", "13:00"), hm)

    def test_window_may_wrap_past_midnight(self):
        self.assertTrue(irishtime.between(self.at("23:00"), "22:00", "02:00"))
        self.assertTrue(irishtime.between(self.at("01:00"), "22:00", "02:00"))
        self.assertFalse(irishtime.between(self.at("12:00"), "22:00", "02:00"))


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

    def test_live_dot_lights_only_the_corner(self):
        plain, dotted = glyphs.countdown(7), glyphs.countdown(7, live_dot=True)
        self.assertEqual([i for i in range(104) if plain[i] != dotted[i]], [12])


def pb_varint(n):
    n &= (1 << 64) - 1
    out = b""
    while True:
        out += bytes([(n & 0x7F) | (0x80 if n > 0x7F else 0)])
        n >>= 7
        if not n:
            return out


def pb(number, value):
    """One protobuf field: ints as varints, str and bytes as length-delimited."""
    if isinstance(value, int):
        return pb_varint(number << 3) + pb_varint(value)
    value = value.encode() if isinstance(value, str) else value
    return pb_varint(number << 3 | 2) + pb_varint(len(value)) + value


def trip_update(trip_id, stops=(), rel=0, route="2 404 c a", date="20261027"):
    trip = pb(1, trip_id) + pb(3, date) + pb(4, rel) + pb(5, route)
    body = pb(1, trip) + b"".join(pb(2, s) for s in stops)
    return pb(2, pb(1, "e" + trip_id) + pb(3, body))


def stop_update(seq, stop_id, delay=None, at=None, rel=0):
    event = (pb(1, delay) if delay is not None else b"") + (pb(2, at) if at is not None else b"")
    return pb(1, seq) + pb(3, event) + pb(4, stop_id) + pb(5, rel)


class Live(unittest.TestCase):
    STOP, ROUTES, SEQ = "8460B5243201", {"2 404 c a"}, {"a": 4, "b": 4, "c": 4, "d": 4, "e": 4}

    def changes(self, *entities):
        feed = pb(1, pb(1, "2.0")) + b"".join(entities)
        return live.at_stop(live.parse(feed), self.STOP, self.ROUTES, self.SEQ)

    def test_negative_delays_decode(self):
        trips = live.parse(trip_update("a", [stop_update(4, self.STOP, delay=-90)]))
        self.assertEqual(trips[0]["stop_time_update"][0]["departure"], {"delay": -90})

    def test_delay_at_our_stop(self):
        changes, _ = self.changes(trip_update("a", [stop_update(4, self.STOP, delay=2327)]))
        self.assertEqual(changes[("a", "20261027")], {"delay": 2327})

    def test_delay_carries_forward_from_an_earlier_stop(self):
        changes, _ = self.changes(trip_update("a", [stop_update(2, "X", delay=300),
                                                    stop_update(6, "Y", delay=900)]))
        self.assertEqual(changes[("a", "20261027")], {"delay": 300})

    def test_cancelled_and_skipped_buses_are_dropped(self):
        changes, _ = self.changes(trip_update("b", rel=live.CANCELED),
                                  trip_update("c", [stop_update(4, self.STOP, rel=live.SKIPPED)]))
        self.assertEqual(changes[("b", "20261027")], {"skip": True})
        self.assertEqual(changes[("c", "20261027")], {"skip": True})

    def test_added_bus_on_our_route_counts(self):
        _, added = self.changes(trip_update("x", [stop_update(1, self.STOP, at=1792998000)], rel=live.ADDED),
                                trip_update("y", [stop_update(1, self.STOP, at=1792999000)], rel=live.ADDED,
                                            route="2 409 c a"))
        self.assertEqual(added, [1792998000])

    def test_trips_we_dont_timetable_are_ignored(self):
        changes, _ = self.changes(trip_update("zzz", [stop_update(4, self.STOP, delay=60)]))
        self.assertEqual(changes, {})


class LiveBus(unittest.TestCase):
    timetable = {
        "calendar": {"weekday": {"days": [1, 1, 1, 1, 1, 0, 0], "start": "20261001", "end": "20261231"}},
        "exceptions": [],
        "departures": [["09:02:00", "weekday", "Newcastle", "a", 4],
                       ["09:30:00", "weekday", "Newcastle", "b", 4]],
    }
    now = datetime(2026, 10, 27, 9, 0)

    def test_late_bus_counts_down_to_when_it_really_comes(self):
        live_changes = ({("a", "20261027"): {"delay": 600}}, [])
        self.assertEqual(bus.minutes_to_leave(self.timetable, self.now, 0, live_changes), 12)

    def test_cancelled_bus_moves_to_the_next(self):
        live_changes = ({("a", "20261027"): {"skip": True}}, [])
        self.assertEqual(bus.minutes_to_leave(self.timetable, self.now, 0, live_changes), 30)

    def test_extra_bus_shows_up(self):
        # 09:10 Irish winter time is 09:10 UTC
        extra = int(datetime(2026, 10, 27, 9, 10, tzinfo=timezone.utc).timestamp())
        live_changes = ({("a", "20261027"): {"skip": True}}, [extra])
        self.assertEqual(bus.minutes_to_leave(self.timetable, self.now, 0, live_changes), 10)

    def test_yesterdays_delay_does_not_apply_today(self):
        live_changes = ({("a", "20261026"): {"delay": 600}}, [])
        self.assertEqual(bus.minutes_to_leave(self.timetable, self.now, 0, live_changes), 2)

    def test_real_timetable_has_trip_ids_for_matching(self):
        real = bus.load(ROOT / "app" / "bus_timetable.json")
        self.assertTrue(real["route_ids"])
        self.assertEqual(len(bus.sequences(real)), len(real["departures"]))


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
