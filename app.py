from pathlib import Path
import sqlite3

from flask import Flask, jsonify, render_template, request

from back import MetroGraph


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "metro.db"

app = Flask(__name__)


def load_metro_graph(database_path=DATABASE_PATH):
    """Load the SQLite metro data into the in-memory routing graph."""
    graph = MetroGraph()

    if not Path(database_path).is_file():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row

    try:
        # Load station records first, because edges reference station IDs.
        station_rows = connection.execute(
            """
            SELECT station_id, station_name
            FROM stations
            ORDER BY station_name
            """
        ).fetchall()

        for row in station_rows:
            graph.add_station(
                code=row["station_id"],
                name=row["station_name"],
            )

        # Each edge records the line used for that connection. Add connections
        # through MetroGraph so its adjacency list remains the routing source.
        edge_rows = connection.execute(
            """
            SELECT source_station, destination_station, line_id, travel_time
            FROM edges
            ORDER BY edge_id
            """
        ).fetchall()

        for row in edge_rows:
            graph.add_connection(
                first=row["source_station"],
                second=row["destination_station"],
                travel_time=row["travel_time"],
                line=row["line_id"],
            )

        # Populate each Station's line set from its incident connections.
        # Station is frozen, so construct a replacement with the same ID/name
        # and the line IDs observed in the graph's adjacency list.
        from back import Station

        for station_id, station in list(graph.stations.items()):
            lines = {edge.line for edge in graph.adjacency[station_id]}
            graph.stations[station_id] = Station(
                code=station.code,
                name=station.name,
                lines=lines,
            )

    finally:
        connection.close()

    return graph


# Load once at startup; route requests use the in-memory graph.
try:
    metro_graph = load_metro_graph()
    startup_error = None
except (OSError, sqlite3.Error, KeyError, ValueError) as exc:
    metro_graph = None
    startup_error = str(exc)


def route_to_dict(result):
    """Convert a RouteResult dataclass into a JSON-compatible dictionary."""
    station_details = [
        {
            "id": station_id,
            "name": metro_graph.stations[station_id].name,
        }
        for station_id in result.stations
    ]

    segments = [
        {
            "from_station": segment.from_station,
            "from_name": metro_graph.stations[segment.from_station].name,
            "to_station": segment.to_station,
            "to_name": metro_graph.stations[segment.to_station].name,
            "line": segment.line,
            "line_name": LINE_METADATA.get(segment.line, {}).get("name", segment.line),
            "color": LINE_METADATA.get(segment.line, {}).get("color", "#64748b"),
            "travel_time": segment.travel_time,
        }
        for segment in result.segments
    ]

    interchange_stations = []
    for previous, current in zip(result.segments, result.segments[1:]):
        if previous.line != current.line:
            station_id = previous.to_station
            interchange_stations.append(
                {
                    "id": station_id,
                    "name": metro_graph.stations[station_id].name,
                    "from_line": previous.line,
                    "to_line": current.line,
                }
            )

    return {
        "stations": station_details,
        "segments": segments,
        "total_time": result.total_time,
        "interchanges": result.interchanges,
        "interchange_stations": interchange_stations,
    }



def get_line_metadata():
    """Return canonical names and DMRC-style colours for each line."""
    connection = sqlite3.connect(str(DATABASE_PATH))
    try:
        rows = connection.execute("SELECT line_id, line_name, color FROM lines").fetchall()
        return {
            row[0]: {"name": row[1], "color": "#" + row[2].lstrip("#") if row[2] else "#64748b"}
            for row in rows
        }
    finally:
        connection.close()


LINE_METADATA = get_line_metadata()


@app.get("/network")
def get_network():
    """Return station coordinates and all line-coloured connections for the map."""
    if metro_graph is None:
        return jsonify({"error": "backend_not_ready", "message": startup_error or "Metro graph failed to load"}), 500
    connection = sqlite3.connect(str(DATABASE_PATH))
    connection.row_factory = sqlite3.Row
    try:
        station_rows = connection.execute(
            "SELECT station_id, station_name, latitude, longitude FROM stations"
        ).fetchall()
        edge_rows = connection.execute(
            "SELECT source_station, destination_station, line_id FROM edges"
        ).fetchall()
    finally:
        connection.close()
    return jsonify({
        "stations": [
            {"id": r["station_id"], "name": r["station_name"],
             "lat": r["latitude"], "lon": r["longitude"]}
            for r in station_rows
        ],
        "edges": [
            {"from": r["source_station"], "to": r["destination_station"],
             "line": r["line_id"],
             "line_name": LINE_METADATA.get(r["line_id"], {}).get("name", r["line_id"]),
             "color": LINE_METADATA.get(r["line_id"], {}).get("color", "#64748b")}
            for r in edge_rows
        ],
        "lines": LINE_METADATA,
    }), 200


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    if metro_graph is None:
        return jsonify({
            "status": "error",
            "message": startup_error or "Metro graph failed to load",
        }), 500

    return jsonify({"status": "ok"}), 200


@app.get("/stations")
def get_stations():
    if metro_graph is None:
        return jsonify({
            "error": "backend_not_ready",
            "message": startup_error or "Metro graph failed to load",
        }), 500

    stations = [
        {"id": station.code, "name": station.name}
        for station in sorted(
            metro_graph.stations.values(),
            key=lambda item: item.name.casefold(),
        )
    ]
    return jsonify({"stations": stations}), 200


@app.post("/route")
def get_route():
    if metro_graph is None:
        return jsonify({
            "error": "backend_not_ready",
            "message": startup_error or "Metro graph failed to load",
        }), 500

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({
            "error": "invalid_json",
            "message": "Send a JSON object containing source, dest, and mode.",
        }), 400

    source = payload.get("source")
    destination = payload.get("dest")
    mode = payload.get("mode")

    if not isinstance(source, str) or not source.strip():
        return jsonify({
            "error": "invalid_source",
            "message": "source must be a non-empty station ID string.",
        }), 400

    if not isinstance(destination, str) or not destination.strip():
        return jsonify({
            "error": "invalid_destination",
            "message": "dest must be a non-empty station ID string.",
        }), 400

    if mode not in ("fastest", "fewest_interchanges"):
        return jsonify({
            "error": "invalid_mode",
            "message": "mode must be 'fastest' or 'fewest_interchanges'.",
        }), 400

    try:
        if mode == "fastest":
            result = metro_graph.fastestRoute(source, destination)
        else:
            result = metro_graph.fewestInterchangesRoute(source, destination)

    except KeyError as exc:
        return jsonify({
            "error": "unknown_station",
            "message": str(exc),
        }), 400
    except ValueError as exc:
        return jsonify({
            "error": "route_not_found",
            "message": str(exc),
        }), 404

    response = route_to_dict(result)
    response["mode"] = mode
    response["source"] = source
    response["dest"] = destination
    return jsonify(response), 200


if __name__ == "__main__":
    # Debug mode is suitable for local development only.
    app.run(host="127.0.0.1", port=5000, debug=True)
