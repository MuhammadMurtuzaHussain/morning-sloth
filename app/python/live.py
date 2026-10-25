"""Live bus times from Transport for Ireland's GTFS-Realtime feed.

The feed covers every bus in the country: about 500 KB as protobuf against 2.9 MB
as JSON, so it's fetched as protobuf and read with the few lines of wire-format
decoding below, without adding a protobuf library to the app.

It needs a free key from developer.nationaltransport.ie, saved as TFI_API_KEY in
secrets.env. Without one, or when the feed is unreachable, the countdown uses the
timetable alone.
"""
import urllib.request

URL = "https://api.nationaltransport.ie/gtfsr/v2/TripUpdates"

# TripDescriptor.schedule_relationship and StopTimeUpdate.schedule_relationship
ADDED, CANCELED, DELETED = 1, 3, 7
SKIPPED = 1


def _varint(buf, i):
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, i
        shift += 7


def _fields(buf):
    """(field number, value) pairs of one protobuf message; bytes for nested ones."""
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 1:
            value, i = buf[i:i + 8], i + 8
        elif wire == 2:
            size, i = _varint(buf, i)
            value, i = buf[i:i + size], i + size
        elif wire == 5:
            value, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield number, value


def _signed(n):
    # Negative int32 and int64 values arrive as 64-bit two's complement varints
    return n - (1 << 64) if n >= 1 << 63 else n


def _event(buf):
    event = {}
    for number, value in _fields(buf):
        if number == 1:
            event["delay"] = _signed(value)
        elif number == 2:
            event["time"] = _signed(value)
    return event


def parse(data):
    """The trip updates in a FeedMessage, as plain dicts shaped like the JSON feed."""
    trips = []
    for number, entity in _fields(data):
        if number != 2:
            continue
        for number, update in _fields(entity):
            if number != 3:
                continue
            trip, stops, delay = {}, [], None
            for number, value in _fields(update):
                if number == 1:
                    for n, v in _fields(value):
                        if n in (1, 2, 3, 5):
                            trip[{1: "trip_id", 2: "start_time", 3: "start_date", 5: "route_id"}[n]] = v.decode()
                        elif n == 4:
                            trip["schedule_relationship"] = v
                elif number == 2:
                    stop = {}
                    for n, v in _fields(value):
                        if n == 1:
                            stop["stop_sequence"] = v
                        elif n == 2:
                            stop["arrival"] = _event(v)
                        elif n == 3:
                            stop["departure"] = _event(v)
                        elif n == 4:
                            stop["stop_id"] = v.decode()
                        elif n == 5:
                            stop["schedule_relationship"] = v
                    stops.append(stop)
                elif number == 5:
                    delay = _signed(value)
            trips.append({"trip": trip, "stop_time_update": stops, "delay": delay})
    return trips


def fetch(key, timeout=30):
    req = urllib.request.Request(URL, headers={"x-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse(resp.read())


def _when(stop):
    return stop.get("departure") or stop.get("arrival") or {}


def at_stop(trips, stop_id, routes, sequences):
    """What the feed says about our stop.

    `sequences` maps each timetabled trip_id to our stop's stop_sequence on it.
    Returns ({(trip_id, start_date): change}, [unix times of extra buses on our routes]),
    where a change is {"skip": True}, {"delay": seconds} or {"time": unix time}.
    A trip the feed doesn't mention runs to the timetable.
    """
    changes, added = {}, []
    for t in trips:
        trip, rel = t["trip"], t["trip"].get("schedule_relationship", 0)
        if rel == ADDED:
            if trip.get("route_id") in routes:
                for stop in t["stop_time_update"]:
                    if stop.get("stop_id") == stop_id and "time" in _when(stop) \
                            and stop.get("schedule_relationship") != SKIPPED:
                        added.append(_when(stop)["time"])
            continue
        seq = sequences.get(trip.get("trip_id"))
        if seq is None:
            continue
        key = (trip["trip_id"], trip.get("start_date", ""))
        if rel in (CANCELED, DELETED):
            changes[key] = {"skip": True}
            continue
        # GTFS-Realtime carries a delay forward to later stops until the next update,
        # so the nearest update at or before our stop applies
        before = [s for s in t["stop_time_update"] if s.get("stop_sequence", seq + 1) <= seq
                  or s.get("stop_id") == stop_id]
        nearest = max(before, key=lambda s: s.get("stop_sequence", seq), default=None)
        if nearest is None:
            if t["delay"] is not None:
                changes[key] = {"delay": t["delay"]}
        elif nearest.get("stop_id") == stop_id and nearest.get("schedule_relationship") == SKIPPED:
            changes[key] = {"skip": True}
        elif "delay" in _when(nearest):
            changes[key] = {"delay": _when(nearest)["delay"]}
        elif nearest.get("stop_id") == stop_id and "time" in _when(nearest):
            changes[key] = {"time": _when(nearest)["time"]}
    return changes, added
