"""Cut Transport for Ireland's Bus Éireann GTFS timetable down to one route at one stop.

The full feed is about 50 MB zipped; the board only needs a few hundred departure
times. Download the feed (no account needed):
  https://www.transportforireland.ie/transitData/Data/GTFS_Bus_Eireann.zip
then: python3 tools/bus_timetable.py <unzipped gtfs dir> 404 8460B5243201 > app/bus_timetable.json
"""
import csv
import json
import sys
from pathlib import Path


def rows(gtfs, name):
    with open(Path(gtfs) / name, encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def build(gtfs, route_short_name, stop_id):
    routes = {r["route_id"] for r in rows(gtfs, "routes.txt") if r["route_short_name"] == route_short_name}
    trips = {t["trip_id"]: t for t in rows(gtfs, "trips.txt") if t["route_id"] in routes}
    stop = next(s for s in rows(gtfs, "stops.txt") if s["stop_id"] == stop_id)
    departures = []
    for st in rows(gtfs, "stop_times.txt"):
        trip = trips.get(st["trip_id"])
        # pickup_type 1 means the bus doesn't pick up here (for example at the last stop)
        if trip and st["stop_id"] == stop_id and st.get("pickup_type", "0") != "1":
            departures.append([st["departure_time"], trip["service_id"], trip["trip_headsign"]])
    services = {d[1] for d in departures}
    calendar = {c["service_id"]: c for c in rows(gtfs, "calendar.txt") if c["service_id"] in services}
    exceptions = [[e["service_id"], e["date"], e["exception_type"]]
                  for e in rows(gtfs, "calendar_dates.txt") if e["service_id"] in services]
    feed = next(rows(gtfs, "feed_info.txt"), {})
    return {
        "route": route_short_name,
        "stop_id": stop_id,
        "stop_name": stop["stop_name"],
        "feed_version": feed.get("feed_version", ""),
        "valid_until": max((c["end_date"] for c in calendar.values()), default=""),
        "calendar": {sid: {"days": [int(c[d]) for d in ("monday", "tuesday", "wednesday", "thursday",
                                                         "friday", "saturday", "sunday")],
                           "start": c["start_date"], "end": c["end_date"]} for sid, c in calendar.items()},
        "exceptions": exceptions,
        "departures": sorted(departures),
    }


if __name__ == "__main__":
    print(json.dumps(build(*sys.argv[1:4]), indent=1))
