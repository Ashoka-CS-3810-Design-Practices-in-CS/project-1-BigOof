import json
import os
import re
from pathlib import Path
import sqlite3
import time
import uuid

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .back import MetroGraph
from .logging_config import configure_logging


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "metro.db"
MAX_VIA_STOPS = 3

# User-interaction events the page may report to /log; anything else is rejected
# so the endpoint can't be used to write arbitrary text into the logs.
UI_EVENTS = frozenset({
    "page_loaded",
    "page_load_failed",
    "route_requested",
    "route_found",
    "route_failed",
    "validation_failed",
    "mode_changed",
    "stations_swapped",
    "stop_added",
    "stop_removed",
    "theme_changed",
    "js_error",
})
MAX_UI_DETAIL_FIELDS = 10
MAX_UI_DETAIL_LENGTH = 200
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,64}")

logger = configure_logging()
app = Flask(__name__)


def connect_read_only(database_path):
    """Open the database read-only.

    The app never writes to it, serverless hosts like Vercel have a read-only
    filesystem, and read-only mode can't create an empty file at a wrong path.
    """
    return sqlite3.connect(f"{Path(database_path).resolve().as_uri()}?mode=ro", uri=True)


def load_metro_graph(database_path=DATABASE_PATH):
    """Load the SQLite metro data into the in-memory routing graph."""
    graph = MetroGraph()

    if not Path(database_path).is_file():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    connection = connect_read_only(database_path)
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
        # The line's kind says whether the edge is a train ride or an on-foot
        # transfer ('walkway'); edges whose line is missing count as metro.
        edge_rows = connection.execute(
            """
            SELECT e.source_station, e.destination_station, e.line_id, e.travel_time,
                   COALESCE(l.kind, 'metro') AS kind
            FROM edges e
            LEFT JOIN lines l ON l.line_id = e.line_id
            ORDER BY e.edge_id
            """
        ).fetchall()

        for row in edge_rows:
            graph.add_connection(
                first=row["source_station"],
                second=row["destination_station"],
                travel_time=row["travel_time"],
                line=row["line_id"],
                walk=row["kind"] == "walkway",
            )

        # Populate each Station's line set from its incident connections.
        # Station is frozen, so construct a replacement with the same ID/name
        # and the line IDs observed in the graph's adjacency list. Walkways
        # aren't lines a station is "on", so they're left out.
        from .back import Station

        for station_id, station in list(graph.stations.items()):
            lines = {edge.line for edge in graph.adjacency[station_id] if not edge.walk}
            graph.stations[station_id] = Station(
                code=station.code,
                name=station.name,
                lines=lines,
            )

    finally:
        connection.close()

    return graph


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
            "walk": segment.walk,
        }
        for segment in result.segments
    ]

    # An interchange is where you leave one line for another. Walking segments
    # in between are skipped, so it's reported at the station you got off at.
    interchange_stations = []
    last_ridden = None
    for segment in result.segments:
        if segment.walk:
            continue
        if last_ridden is not None and last_ridden.line != segment.line:
            station_id = last_ridden.to_station
            interchange_stations.append(
                {
                    "id": station_id,
                    "name": metro_graph.stations[station_id].name,
                    "from_line": last_ridden.line,
                    "to_line": segment.line,
                }
            )
        last_ridden = segment

    return {
        "stations": station_details,
        "segments": segments,
        "total_time": result.total_time,
        "interchanges": result.interchanges,
        "interchange_stations": interchange_stations,
    }



def get_line_metadata(database_path=None):
    """Return canonical names, DMRC-style colours and kind ('metro'/'walkway') for each line."""
    connection = connect_read_only(database_path or DATABASE_PATH)
    try:
        rows = connection.execute("SELECT line_id, line_name, color, kind FROM lines").fetchall()
        return {
            row[0]: {
                "name": row[1],
                "color": "#" + row[2].lstrip("#") if row[2] else "#64748b",
                "kind": row[3],
            }
            for row in rows
        }
    finally:
        connection.close()


def load_app_data(database_path=DATABASE_PATH):
    """Load the routing graph and line metadata, or capture why they couldn't be.

    Returns ``(graph, line_metadata, error)``. On failure the graph is ``None`` and
    the error message is served by /health and the other endpoints, instead of the
    app crashing at import.
    """
    try:
        # load_metro_graph checks the file exists first, so a missing database
        # isn't silently created as an empty file by sqlite3.connect.
        graph = load_metro_graph(database_path)
        return graph, get_line_metadata(database_path), None
    except (OSError, sqlite3.Error, KeyError, ValueError) as exc:
        return None, {}, str(exc)


# Load once at startup; route requests use the in-memory graph.
metro_graph, LINE_METADATA, startup_error = load_app_data()
if metro_graph is None:
    logger.error("Startup failed, metro data not loaded: %s", startup_error)
else:
    logger.info(
        "Loaded metro data: %d stations, %d lines from %s",
        len(metro_graph.stations), len(LINE_METADATA), DATABASE_PATH,
    )


@app.before_request
def start_request_log():
    """Tag each request with an ID (returned as X-Request-ID) and start its timer."""
    # Reuse a caller's request ID only if it's short and plain, since it ends up in logs.
    incoming = request.headers.get("X-Request-ID", "")
    g.request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex[:12]
    g.request_started = time.perf_counter()


@app.after_request
def log_request(response):
    """One log line per request; error responses also record their error code."""
    duration_ms = (time.perf_counter() - g.get("request_started", time.perf_counter())) * 1000
    request_id = g.get("request_id", "-")
    response.headers["X-Request-ID"] = request_id
    message = "%s %s -> %d (%.1f ms) [req %s]"
    args = [request.method, request.path, response.status_code, duration_ms, request_id]

    if response.status_code >= 400 and response.is_json:
        error = (response.get_json(silent=True) or {}).get("error")
        if error:
            message += " error=%s"
            args.append(error)
    if response.status_code >= 500:
        logger.error(message, *args)
    elif response.status_code >= 400:
        logger.warning(message, *args)
    elif request.path.startswith("/static/"):
        logger.debug(message, *args)
    else:
        logger.info(message, *args)
    return response


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    """Log unhandled errors with a traceback; let normal HTTP errors (404 etc.) through."""
    if isinstance(exc, HTTPException):
        return exc
    logger.exception("Unhandled error on %s %s [req %s]", request.method, request.path, g.get("request_id", "-"))
    return jsonify({"error": "internal_error", "message": "Something went wrong."}), 500


@app.get("/network")
def get_network():
    """Return station coordinates and all line-coloured connections for the map."""
    if metro_graph is None:
        return jsonify({"error": "backend_not_ready", "message": startup_error or "Metro graph failed to load"}), 500
    connection = connect_read_only(DATABASE_PATH)
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
             "color": LINE_METADATA.get(r["line_id"], {}).get("color", "#64748b"),
             "walk": LINE_METADATA.get(r["line_id"], {}).get("kind") == "walkway"}
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

    body = {"status": "ok"}
    # Report the deployed commit so the deploy pipeline can confirm the new
    # release is the one serving traffic. Set by the deploy workflow (APP_COMMIT)
    # or by Vercel for Git-based deployments (VERCEL_GIT_COMMIT_SHA).
    commit = os.environ.get("APP_COMMIT") or os.environ.get("VERCEL_GIT_COMMIT_SHA")
    if commit:
        body["commit"] = commit
    return jsonify(body), 200


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

    # Optional intermediate stations, visited in order between source and dest.
    via = payload.get("via", [])
    if (
        not isinstance(via, list)
        or len(via) > MAX_VIA_STOPS
        or not all(isinstance(stop, str) and stop.strip() for stop in via)
    ):
        return jsonify({
            "error": "invalid_via",
            "message": f"via must be a list of at most {MAX_VIA_STOPS} station ID strings.",
        }), 400

    stops = [source, *via, destination]
    if via and any(previous == current for previous, current in zip(stops, stops[1:])):
        return jsonify({
            "error": "invalid_via",
            "message": "Each stop must differ from the stop before it.",
        }), 400

    try:
        if via:
            result = metro_graph.routeVia(stops, fewest_interchanges=mode == "fewest_interchanges")
        elif mode == "fastest":
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

    logger.info(
        "Route %s mode=%s via=%s: %d stations, %ss, %d interchanges [req %s]",
        " -> ".join(stops), mode, len(via), len(result.stations),
        result.total_time, result.interchanges, g.get("request_id", "-"),
    )
    response = route_to_dict(result)
    response["mode"] = mode
    response["source"] = source
    response["dest"] = destination
    response["via"] = via
    return jsonify(response), 200


@app.post("/log")
def log_ui_event():
    """Record a user-interaction event sent by the page (see UI_EVENTS)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("event") not in UI_EVENTS:
        return jsonify({"error": "invalid_event", "message": "Unknown or missing event."}), 400

    details = payload.get("details", {})
    if (
        not isinstance(details, dict)
        or len(details) > MAX_UI_DETAIL_FIELDS
        or not all(
            isinstance(key, str) and len(key) <= 40
            and (value is None or isinstance(value, (bool, int, float))
                 or (isinstance(value, str) and len(value) <= MAX_UI_DETAIL_LENGTH))
            for key, value in details.items()
        )
    ):
        return jsonify({"error": "invalid_details", "message": "details must be a small flat object."}), 400

    # json.dumps keeps user-supplied text on one escaped line, so it can't fake log entries.
    logger.info("UI %s %s [req %s]", payload["event"], json.dumps(details, sort_keys=True), g.get("request_id", "-"))
    return "", 204
