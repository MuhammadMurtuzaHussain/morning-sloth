"""Irish local time without tzdata, which the App Lab Python container doesn't ship.

Ireland is UTC+1 from 01:00 UTC on the last Sunday of March to 01:00 UTC on the
last Sunday of October, and UTC+0 the rest of the year.
"""
from datetime import datetime, timedelta, timezone


def _last_sunday(year, month):
    day = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def offset(utc):
    start = _last_sunday(utc.year, 3).replace(hour=1)
    end = _last_sunday(utc.year, 10).replace(hour=1)
    return timedelta(hours=1) if start <= utc < end else timedelta(0)


def to_irish(dt):
    """Any aware datetime to naive Irish local time."""
    utc = dt.astimezone(timezone.utc)
    return (utc + offset(utc)).replace(tzinfo=None)


def now():
    return to_irish(datetime.now(timezone.utc))


def between(now, start, end):
    """Whether `now` is in [start, end) given as "HH:MM"; a window may wrap past midnight."""
    hm = now.strftime("%H:%M")
    if start <= end:
        return start <= hm < end
    return hm >= start or hm < end
