"""Minutes until the next bus, from the timetable cut out by tools/bus_timetable.py.

With a Transport for Ireland key, live.py adds delays, cancellations and extra buses
from the realtime feed. Without one this is the published timetable.
"""
import json
from datetime import datetime, timedelta, timezone

import irishtime


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


def sequences(timetable):
    """Our stop's stop_sequence on each timetabled trip, for matching the live feed."""
    return {d[3]: d[4] for d in timetable["departures"] if len(d) > 4}


def _local(unix):
    return irishtime.to_irish(datetime.fromtimestamp(unix, timezone.utc))


def departures(timetable, now, live=None):
    """Today's departures (naive Irish time), with live changes applied when given.

    `live` is what live.at_stop returns: changes per (trip_id, service date) and
    extra buses.
    """
    changes, added = live or ({}, [])
    ymd = now.strftime("%Y%m%d")
    times = []
    for dep in timetable["departures"]:
        if not _active(timetable, dep[1], now):
            continue
        when = _at(now, dep[0])
        change = changes.get((dep[3], ymd), {}) if len(dep) > 3 else {}
        if change.get("skip"):
            continue
        if "delay" in change:
            when += timedelta(seconds=change["delay"])
        elif "time" in change:
            when = _local(change["time"])
        times.append(when)
    return sorted(times + [_local(t) for t in added])


def next_departure(timetable, now, live=None):
    """The next departure at or after `now` (naive Irish time) today, or None."""
    return next((t for t in departures(timetable, now, live) if t >= now), None)


def minutes_to_leave(timetable, now, walk_minutes=0, live=None):
    """Whole minutes until you need to leave for the next bus you can still catch, or None."""
    for bus in departures(timetable, now, live):
        leave_by = bus - timedelta(minutes=walk_minutes)
        if leave_by >= now:
            return int((leave_by - now).total_seconds() // 60)
    return None


def load(path):
    with open(path) as f:
        return json.load(f)
