import sqlite3

import pytest

from big_o import app as app_module
from big_o.app import load_metro_graph


@pytest.fixture
def database(tmp_path):
    """Create a small SQLite database representing a metro network."""
    path = tmp_path / "integration_metro.db"

    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE stations (
                station_id TEXT PRIMARY KEY,
                station_name TEXT NOT NULL,
                latitude REAL,
                longitude REAL
            );

            CREATE TABLE lines (
                line_id TEXT PRIMARY KEY,
                line_name TEXT NOT NULL,
                color TEXT,
                kind TEXT NOT NULL DEFAULT 'metro'
            );

            CREATE TABLE edges (
                edge_id INTEGER PRIMARY KEY,
                source_station TEXT NOT NULL,
                destination_station TEXT NOT NULL,
                line_id TEXT NOT NULL,
                travel_time REAL NOT NULL
            );
        """)

        db.executemany(
            "INSERT INTO stations VALUES (?, ?, ?, ?)",
            [
                ("A", "Alpha", 28.60, 77.20),
                ("B", "Bravo", 28.61, 77.21),
                ("C", "Charlie", 28.62, 77.22),
                ("D", "Delta", 28.63, 77.23),
            ],
        )

        db.executemany(
            "INSERT INTO lines (line_id, line_name, color) VALUES (?, ?, ?)",
            [
                ("red", "Red Line", "ff0000"),
                ("blue", "Blue Line", "0000ff"),
                ("green", "Green Line", "00aa00"),
            ],
        )

        db.executemany(
            """INSERT INTO edges
               (source_station, destination_station, line_id, travel_time)
               VALUES (?, ?, ?, ?)""",
            [
                ("A", "B", "red", 2),
                ("B", "D", "blue", 2),
                ("A", "C", "green", 3),
                ("C", "D", "green", 3),
            ],
        )

    return path


@pytest.fixture
def integration_client(database, monkeypatch):
    """Load the graph from SQLite and exercise the real Flask endpoints."""
    graph = load_metro_graph(database)

    monkeypatch.setattr(app_module, "DATABASE_PATH", database)
    monkeypatch.setattr(app_module, "metro_graph", graph)
    monkeypatch.setattr(
        app_module,
        "LINE_METADATA",
        app_module.get_line_metadata(),
    )
    monkeypatch.setattr(app_module, "startup_error", None)

    app_module.app.config.update(TESTING=True)

    with app_module.app.test_client() as client:
        yield client


def test_database_loads_into_graph(database):
    graph = load_metro_graph(database)

    assert len(graph.stations) == 4
    assert graph.stations["A"].name == "Alpha"
    assert graph.stations["D"].name == "Delta"


def test_database_populates_station_lines(database):
    graph = load_metro_graph(database)

    assert graph.stations["A"].lines == {"red", "green"}
    assert graph.stations["B"].lines == {"red", "blue"}
    assert graph.stations["C"].lines == {"green"}
    assert graph.stations["D"].lines == {"blue", "green"}


def test_database_edges_are_bidirectional(database):
    graph = load_metro_graph(database)

    forward = graph.fastestRoute("A", "B")
    backward = graph.fastestRoute("B", "A")

    assert forward.total_time == 2
    assert backward.total_time == 2
    assert forward.stations == ("A", "B")
    assert backward.stations == ("B", "A")


def test_loaded_graph_finds_fastest_route(integration_client):
    response = integration_client.post(
        "/route",
        json={"source": "A", "dest": "D", "mode": "fastest"},
    )

    assert response.status_code == 200
    data = response.get_json()

    assert [s["id"] for s in data["stations"]] == ["A", "B", "D"]
    assert data["total_time"] == 4
    assert data["interchanges"] == 1
    assert data["interchange_stations"][0]["id"] == "B"


def test_loaded_graph_finds_fewest_interchanges(integration_client):
    response = integration_client.post(
        "/route",
        json={
            "source": "A",
            "dest": "D",
            "mode": "fewest_interchanges",
        },
    )

    assert response.status_code == 200
    data = response.get_json()

    assert [s["id"] for s in data["stations"]] == ["A", "C", "D"]
    assert data["total_time"] == 6
    assert data["interchanges"] == 0


def test_network_matches_loaded_database(integration_client):
    response = integration_client.get("/network")

    assert response.status_code == 200
    data = response.get_json()

    assert len(data["stations"]) == 4
    assert len(data["edges"]) == 4
    assert data["lines"]["red"]["name"] == "Red Line"
    assert data["lines"]["red"]["color"] == "#ff0000"


def test_missing_database_is_reported(tmp_path):
    missing_path = tmp_path / "does_not_exist.db"

    with pytest.raises(FileNotFoundError, match="Database file not found"):
        load_metro_graph(missing_path)



def test_walkway_lines_load_as_walking_edges(database):
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO lines VALUES ('Walkway', 'Walkway (on foot)', '9ca3af', 'walkway')")
        db.execute(
            "INSERT INTO edges (source_station, destination_station, line_id, travel_time) "
            "VALUES ('B', 'C', 'Walkway', 5)"
        )

    graph = load_metro_graph(database)

    walk_edges = [edge for edge in graph.adjacency["B"] if edge.line == "Walkway"]
    assert walk_edges and all(edge.walk for edge in walk_edges)
    assert all(not edge.walk for edge in graph.adjacency["A"])
    # A walkway isn't one of the lines a station is on.
    assert graph.stations["B"].lines == {"red", "blue"}
