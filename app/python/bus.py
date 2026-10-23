"""Minutes until the next bus, from the timetable cut out by tools/bus_timetable.py.

This is the published timetable, not live tracking. Live times need a Transport
for Ireland developer key, which needs an account.
"""
import json
from datetime import datetime, timedelta


def _active(timetable, service_id, day):
    ymd = day.strftime("%Y%m%d")
    for sid, date, kind in timetable["exceptions"]:
        if sid == service_id and date == ymd:
            return kind == "1"  # 1 adds the service on this date, 2 removes it
    cal = timetable["calendar"].get(service_id)
    return bool(cal) and cal["start"] <= ymd <= cal["end"] and cal["days"][day.weekday()] == 1


def _at(day, hms):
    # GTFS times can pass 24:00 for trips that run after midnight
    h, m, s = (int(x) for x in hms.split(":"))
    return datetime(day.year, day.month, day.day) + timedelta(hours=h, minutes=m, seconds=s)


def next_departure(timetable, now):
    """The next departure at or after `now` (naive Irish time) today, or None."""
    times = sorted(_at(now, t) for t, sid, _ in timetable["departures"] if _active(timetable, sid, now))
    return next((t for t in times if t >= now), None)


def minutes_to_leave(timetable, now, walk_minutes=0):
    """Whole minutes until you need to leave for the next bus you can still catch, or None."""
    leave_by = None
    candidate = now
    while True:
        bus = next_departure(timetable, candidate)
        if bus is None:
            return None
        leave_by = bus - timedelta(minutes=walk_minutes)
        if leave_by >= now:
            return int((leave_by - now).total_seconds() // 60)
        candidate = bus + timedelta(seconds=1)


def load(path):
    with open(path) as f:
        return json.load(f)
