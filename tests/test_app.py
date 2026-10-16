import sqlite3

import pytest

import big_o.app as metro_app
from big_o.back import MetroGraph


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Build a small, predictable graph.
    graph = MetroGraph()
    for code in ("A", "B", "C", "D"):
        graph.add_station(code, f"Station {code}")

    graph.add_connection("A", "B", 2, "red")
    graph.add_connection("B", "D", 2, "blue")
    graph.add_connection("A", "C", 3, "green")
    graph.add_connection("C", "D", 3, "green")

    monkeypatch.setattr(metro_app, "metro_graph", graph)
    monkeypatch.setattr(metro_app, "startup_error", None)
    monkeypatch.setattr(
        metro_app,
        "LINE_METADATA",
        {
            "red": {"name": "Red Line", "color": "#ff0000"},
            "blue": {"name": "Blue Line", "color": "#0000ff"},
            "green": {"name": "Green Line", "color": "#00aa00"},
        },
    )

    # Create a temporary database for /network.
    db_path = tmp_path / "test_metro.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE stations (
                station_id TEXT PRIMARY KEY,
                station_name TEXT NOT NULL,
                latitude REAL,
                longitude REAL
            );

            CREATE TABLE edges (
                edge_id INTEGER PRIMARY KEY,
                source_station TEXT NOT NULL,
                destination_station TEXT NOT NULL,
                line_id TEXT NOT NULL,
                travel_time REAL NOT NULL
            );

            CREATE TABLE lines (
                line_id TEXT PRIMARY KEY,
                line_name TEXT NOT NULL,
                color TEXT,
                kind TEXT NOT NULL DEFAULT 'metro'
            );
        """)

        db.executemany(
            "INSERT INTO stations VALUES (?, ?, ?, ?)",
            [
                ("A", "Station A", 28.60, 77.20),
                ("B", "Station B", 28.61, 77.21),
                ("C", "Station C", 28.62, 77.22),
                ("D", "Station D", 28.63, 77.23),
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
        db.executemany(
            "INSERT INTO lines (line_id, line_name, color) VALUES (?, ?, ?)",
            [
                ("red", "Red Line", "ff0000"),
                ("blue", "Blue Line", "0000ff"),
                ("green", "Green Line", "00aa00"),
            ],
        )

    monkeypatch.setattr(metro_app, "DATABASE_PATH", db_path)

    metro_app.app.config.update(TESTING=True)

    with metro_app.app.test_client() as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


@pytest.mark.parametrize("variable", ["APP_COMMIT", "VERCEL_GIT_COMMIT_SHA"])
def test_health_reports_deployed_commit(client, monkeypatch, variable):
    monkeypatch.delenv("APP_COMMIT", raising=False)
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv(variable, "abc123")

    response = client.get("/health")

    assert response.get_json() == {"status": "ok", "commit": "abc123"}


def test_health_when_graph_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(metro_app, "metro_graph", None)
    monkeypatch.setattr(metro_app, "startup_error", "Database unavailable")

    response = client.get("/health")

    assert response.status_code == 500
    assert response.get_json() == {"status": "error", "message": "Database unavailable"}


def test_stations(client):
    response = client.get("/stations")

    assert response.status_code == 200
    data = response.get_json()

    assert len(data["stations"]) == 4
    names = [station["name"] for station in data["stations"]]
    assert names == sorted(names, key=str.casefold)


def test_stations_when_graph_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(metro_app, "metro_graph", None)

    response = client.get("/stations")

    assert response.status_code == 500
    assert response.get_json()["error"] == "backend_not_ready"


def test_network(client):
    response = client.get("/network")

    assert response.status_code == 200
    data = response.get_json()

    assert len(data["stations"]) == 4
    assert len(data["edges"]) == 4
    assert data["stations"][0]["lat"] == 28.60
    assert all(edge["walk"] is False for edge in data["edges"])
    assert data["edges"][0]["line_name"] in {
        "Red Line", "Blue Line", "Green Line"
    }
    assert data["lines"]["red"]["color"] == "#ff0000"


def test_fastest_route(client):
    response = client.post(
        "/route",
        json={"source": "A", "dest": "D", "mode": "fastest"},
    )

    assert response.status_code == 200
    data = response.get_json()

    assert data["stations"] == [
        {"id": "A", "name": "Station A"},
        {"id": "B", "name": "Station B"},
        {"id": "D", "name": "Station D"},
    ]
    assert data["total_time"] == 4
    assert data["interchanges"] == 1
    assert len(data["interchange_stations"]) == 1
    assert data["interchange_stations"][0]["id"] == "B"


def test_fewest_interchanges_route(client):
    response = client.post(
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
    assert data["interchange_stations"] == []


def test_route_rejects_non_json(client):
    response = client.post(
        "/route",
        data="not json",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_json"


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"dest": "D", "mode": "fastest"}, "invalid_source"),
        ({"source": "A", "mode": "fastest"}, "invalid_destination"),
        (
            {"source": "A", "dest": "D", "mode": "cheapest"},
            "invalid_mode",
        ),
        (
            {"source": "UNKNOWN", "dest": "D", "mode": "fastest"},
            "unknown_station",
        ),
    ],
)
def test_route_validation(client, payload, expected_error):
    response = client.post("/route", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error


def test_route_via_intermediate_station(client):
    response = client.post(
        "/route",
        json={"source": "A", "dest": "D", "via": ["C"], "mode": "fastest"},
    )

    assert response.status_code == 200
    data = response.get_json()

    assert [s["id"] for s in data["stations"]] == ["A", "C", "D"]
    assert data["total_time"] == 6
    assert data["via"] == ["C"]


def test_route_without_via_reports_empty_list(client):
    response = client.post(
        "/route",
        json={"source": "A", "dest": "D", "mode": "fastest"},
    )

    assert response.get_json()["via"] == []


@pytest.mark.parametrize(
    "via",
    [
        "C",
        [""],
        [1],
        ["A"],
        ["B", "B"],
        ["B", "C", "B", "C"],
    ],
)
def test_route_rejects_invalid_via(client, via):
    response = client.post(
        "/route",
        json={"source": "A", "dest": "D", "via": via, "mode": "fastest"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_via"


def test_route_via_unknown_station(client):
    response = client.post(
        "/route",
        json={"source": "A", "dest": "D", "via": ["UNKNOWN"], "mode": "fastest"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "unknown_station"


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "A", "dest": "E", "mode": "fastest"},
        {"source": "A", "dest": "E", "mode": "fewest_interchanges"},
        {"source": "A", "dest": "D", "via": ["E"], "mode": "fastest"},
    ],
)
def test_route_not_found(client, payload):
    # E exists but has no connections, so no path reaches it.
    metro_app.metro_graph.add_station("E", "Station E")

    response = client.post("/route", json=payload)

    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "route_not_found"
    assert "No route" in data["message"]


def test_network_when_graph_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(metro_app, "metro_graph", None)
    monkeypatch.setattr(metro_app, "startup_error", "Database unavailable")

    response = client.get("/network")

    assert response.status_code == 500
    assert response.get_json()["error"] == "backend_not_ready"


def test_route_reports_walking_segments(client, monkeypatch):
    # Swap in a graph where B and D are joined by a walkway instead of blue.
    graph = MetroGraph()
    for code in ("A", "B", "C", "D"):
        graph.add_station(code, f"Station {code}")
    graph.add_connection("A", "B", 2, "red")
    graph.add_connection("B", "C", 1, "walkway", walk=True)
    graph.add_connection("C", "D", 2, "green")
    monkeypatch.setattr(metro_app, "metro_graph", graph)

    response = client.post("/route", json={"source": "A", "dest": "D", "mode": "fastest"})
    data = response.get_json()

    assert [segment["walk"] for segment in data["segments"]] == [False, True, False]
    assert data["interchanges"] == 1
    # The interchange is where you leave the red line, not the walkway itself.
    assert data["interchange_stations"] == [
        {"id": "B", "name": "Station B", "from_line": "red", "to_line": "green"},
    ]


def test_load_app_data_reports_missing_database(tmp_path):
    missing = tmp_path / "missing.db"

    graph, line_metadata, error = metro_app.load_app_data(missing)

    assert graph is None
    assert line_metadata == {}
    assert "Database file not found" in error
    # sqlite3.connect would create an empty file; loading must not.
    assert not missing.exists()


def test_load_app_data_reports_broken_database(tmp_path):
    broken = tmp_path / "broken.db"
    sqlite3.connect(broken).close()  # exists, but has no tables

    graph, line_metadata, error = metro_app.load_app_data(broken)

    assert graph is None
    assert "no such table" in error


def test_load_app_data_loads_graph_and_metadata(client):
    graph, line_metadata, error = metro_app.load_app_data(metro_app.DATABASE_PATH)

    assert error is None
    assert set(graph.stations) == {"A", "B", "C", "D"}
    assert line_metadata["red"] == {"name": "Red Line", "color": "#ff0000", "kind": "metro"}


def test_route_when_graph_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(metro_app, "metro_graph", None)
    monkeypatch.setattr(metro_app, "startup_error", "Database unavailable")

    response = client.post(
        "/route",
        json={"source": "A", "dest": "D", "mode": "fastest"},
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "backend_not_ready"


def test_index_renders(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    html = response.get_data(as_text=True)
    # The page's key controls are present.
    for element_id in ("source", "destination", "find-route", "add-stop", "route-map", "route-list"):
        assert f'id="{element_id}"' in html

