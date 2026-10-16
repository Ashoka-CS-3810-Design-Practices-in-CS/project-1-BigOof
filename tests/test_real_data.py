"""Checks against the shipped metro.db, so data problems surface in CI rather than production."""

import sqlite3
from collections import deque

import pytest

from big_o.app import DATABASE_PATH, load_metro_graph


@pytest.fixture(scope="module")
def graph():
    return load_metro_graph(DATABASE_PATH)


@pytest.fixture(scope="module")
def db():
    connection = sqlite3.connect(DATABASE_PATH)
    yield connection
    connection.close()


def station_id(graph, name):
    return next(code for code, station in graph.stations.items() if station.name == name)


def test_every_station_is_loaded(graph, db):
    (count,) = db.execute("SELECT COUNT(*) FROM stations").fetchone()

    assert count > 0
    assert len(graph.stations) == count


def test_every_station_has_coordinates(db):
    (missing,) = db.execute(
        "SELECT COUNT(*) FROM stations WHERE latitude IS NULL OR longitude IS NULL"
    ).fetchone()

    assert missing == 0


def test_every_edge_references_known_stations_and_lines(db):
    (bad_stations,) = db.execute(
        """SELECT COUNT(*) FROM edges
           WHERE source_station NOT IN (SELECT station_id FROM stations)
              OR destination_station NOT IN (SELECT station_id FROM stations)"""
    ).fetchone()
    (bad_lines,) = db.execute(
        "SELECT COUNT(*) FROM edges WHERE line_id NOT IN (SELECT line_id FROM lines)"
    ).fetchone()

    assert bad_stations == 0
    assert bad_lines == 0


def test_travel_times_are_positive(db):
    (minimum,) = db.execute("SELECT MIN(travel_time) FROM edges").fetchone()

    assert minimum > 0


def test_network_is_connected(graph):
    # Every station must be reachable from every other, or some routes 404.
    start = next(iter(graph.stations))
    seen = {start}
    queue = deque([start])
    while queue:
        for edge in graph.adjacency[queue.popleft()]:
            if edge.station not in seen:
                seen.add(edge.station)
                queue.append(edge.station)

    unreachable = sorted(graph.stations[code].name for code in graph.stations.keys() - seen)
    assert unreachable == []


def test_every_station_has_a_line(graph):
    assert [s.name for s in graph.stations.values() if not s.lines] == []


def test_known_direct_route(graph):
    result = graph.fastestRoute(
        station_id(graph, "Central Secretariat"),
        station_id(graph, "Mandi House"),
    )

    assert [graph.stations[code].name for code in result.stations] == [
        "Central Secretariat",
        "Janpath",
        "Mandi House",
    ]
    assert result.interchanges == 0


def test_known_route_via_intermediate_station(graph):
    result = graph.routeVia([
        station_id(graph, "Central Secretariat"),
        station_id(graph, "Rajiv Chowk"),
        station_id(graph, "Mandi House"),
    ])

    assert [graph.stations[code].name for code in result.stations] == [
        "Central Secretariat",
        "Patel Chowk",
        "Rajiv Chowk",
        "Barakhamba",
        "Mandi House",
    ]
    assert result.interchanges == 1


def test_walkway_is_flagged(db):
    rows = db.execute("SELECT line_id FROM lines WHERE kind = 'walkway'").fetchall()

    assert rows == [("Walkway",)]


def test_aqua_line_connects_by_walkway(graph):
    result = graph.fastestRoute(
        station_id(graph, "Noida Sector 50"),
        station_id(graph, "Noida Sec-61"),
    )
    names = [graph.stations[code].name for code in result.stations]
    walks = [segment for segment in result.segments if segment.walk]

    # Aqua Line -> skywalk -> Blue Line, counted as a single interchange.
    assert names == ["Noida Sector 50", "Noida Sector 51", "Noida Sec-52", "Noida Sec-61"]
    assert [(graph.stations[w.from_station].name, graph.stations[w.to_station].name) for w in walks] == [
        ("Noida Sector 51", "Noida Sec-52"),
    ]
    assert result.interchanges == 1


def test_walkway_is_not_a_station_line(graph):
    assert graph.stations[station_id(graph, "Noida Sec-52")].lines == {"Delhi3"}
    assert graph.stations[station_id(graph, "Noida Sector 51")].lines == {"NoidaAqua"}
