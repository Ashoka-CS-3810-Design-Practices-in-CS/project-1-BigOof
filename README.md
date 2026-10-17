# Meteronormative

**An interactive Delhi Metro route planner and visualiser** by team **Big O(oof)**:
Gayatri Taneja and Shivanshi Singh.

**Live:** https://project-1-big-oof.vercel.app

Pick a start and a destination, optionally add up to three stops on the way, and choose
whether you care about getting there fastest or changing lines the fewest times.
Meteronormative finds the route, draws it on a map of the network, and lists every
stop with the line you're on and where to change.

## Features

- **Two routing modes**: *Fastest route* (least travel time) and *Least interchanges*
  (fewest line changes, then least time).
- **Intermediate stops**: route A → B through up to three stations, in order. The whole
  journey is optimised at once, including which line to arrive on at each stop.
- **Map view**: the network drawn in official line colours, with the route highlighted, the
  rest of the map greyed out, and interchange and terminus names labelled without overlaps.
- **Stop-by-stop directions**: travel time, number of interchanges, and every station with
  the line to take, where to change, and walking transfers ("Walk to Noida Sec-52 (5 min)").
- **Light and dark themes**, keyboard-accessible controls, and reduced-motion support.

The network covers **262 stations** and **309 connections** across **12 lines** (the Blue Line's
two branches are listed separately), plus the walkway joining the Noida Aqua Line to the Blue Line.

## Tech stack

- **Backend**: Python 3.12, Flask, SQLite (read-only)
- **Frontend**: a single HTML page with vanilla JavaScript and [Leaflet](https://leafletjs.com) maps
- **Tooling**: [uv](https://docs.astral.sh/uv/) for dependencies, pytest and Playwright for tests
- **Hosting**: Vercel (serverless), deployed by GitHub Actions

## Running locally

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). It installs the right
Python version and all dependencies for you.

```
uv sync
uv run big-o
```

Then open http://127.0.0.1:5000.

To run a production-style server instead: `uv run gunicorn big_o.app:app` (http://localhost:8000).

## Tests

```
uv run playwright install chromium   # once, for the browser tests
uv run pytest
```

There are 130 tests, covering:

| File | What it covers |
|---|---|
| `tests/test_back.py` | Routing algorithms: fastest, fewest interchanges, via stops, walkways, errors |
| `tests/test_app.py` | HTTP API: responses, validation, error codes |
| `tests/test_integration.py` | Loading a SQLite database into the routing graph |
| `tests/test_real_data.py` | The shipped `metro.db`: connected network, valid edges, known routes |
| `tests/test_logging.py` | Request logging, the `/log` endpoint, log files |
| `tests/test_entry_point.py` | The `big-o` command and `python -m big_o` |
| `tests/e2e/test_ui.py` | The real page in headless Chromium: planner, via stops, map labels, themes, logging |

Without Chromium installed, the browser tests are skipped locally. In CI they're required.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | The planner page |
| `GET` | `/stations` | All stations, sorted by name |
| `GET` | `/network` | Station coordinates, connections and line colours, for the map |
| `POST` | `/route` | Find a route (see below) |
| `GET` | `/health` | Status, plus the deployed commit |
| `POST` | `/log` | Record a user-interaction event from the page |

`POST /route` takes station IDs from `/stations`. This example goes from Central Secretariat to
Mandi House via Rajiv Chowk:

```json
{ "source": "52", "dest": "92", "via": ["50"], "mode": "fastest" }
```

- `mode` is `"fastest"` or `"fewest_interchanges"`.
- `via` is optional, with at most 3 stations.

The response lists the stations and segments in order, with `total_time` (seconds),
`interchanges`, and where each interchange happens. Errors return a JSON `error` code:
`invalid_source`, `invalid_via`, `unknown_station`, `route_not_found` and so on.

## How routing works

The network is an adjacency-list graph loaded from SQLite at startup (`src/big_o/back.py`).

- **Fastest route**: Dijkstra's algorithm on travel time. *O((V + E) log V)*.
- **Fewest interchanges**: Dijkstra over *(station, current line)* states, comparing
  *(interchanges, time)* pairs, so it minimises line changes first and breaks ties on time.
  Taking an edge on a different line from the one you arrived on costs one interchange.
- **Via stops**: the same search with a third state component, *the next stop still to visit*.
  Reaching that stop moves the search on to the next one at no cost. This optimises the whole
  journey in one search, so it picks the best line to arrive on at each stop. Planning each leg
  separately could add a line change you didn't need.
- **Walkways**: on-foot transfers between separate stations are flagged in the data
  (`lines.kind = 'walkway'`). Walking keeps you "on" the line you arrived by, so
  Aqua → walk → Blue counts as one interchange, not two.

## Project structure

```
src/big_o/
  app.py              Flask app: API endpoints, data loading, request logging
  back.py             Routing graph and algorithms
  logging_config.py   Log setup (stdout, plus a local .logs/ file)
  templates/index.html  The planner page (HTML, CSS, JavaScript)
  metro.db            Network data (SQLite)
  schema.sql          Database schema
  migrations/         Changes applied to metro.db, e.g. the Noida walkway
tests/                Unit, integration, real-data and browser tests
docs/                 Assignment reports (technical design, testing and UX plan)
wsgi.py               Entry point Vercel loads
vercel.json           Vercel configuration
.github/workflows/    CI (tests.yml) and deployment (deploy.yml)
```

## Development workflow

Work happens on `dev` (or feature branches merged into `dev`). Every push and PR runs the tests.
A PR from `dev` into `main` gets a preview deployment. Merging it deploys to production, after
the tests pass and a smoke test confirms the live site works.

Deployment setup, secrets and the pipeline in detail: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Logging

The server logs every request (with a request ID returned in the `X-Request-ID` header), every
route search, and errors with tracebacks. The page also reports user interactions such as route
searches, mode changes and JavaScript errors. Logs go to stdout, which on Vercel appears under
**Project → Logs**. Locally they're also written to `.logs/big_o.log`.
Details: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#logging).
