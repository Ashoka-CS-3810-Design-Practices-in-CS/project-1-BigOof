PRAGMA foreign_keys = ON;

-- Stations

CREATE TABLE stations (
    station_id   TEXT PRIMARY KEY,
    station_name TEXT NOT NULL,
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL
);

-- Metro Lines

CREATE TABLE lines (
    line_id   TEXT PRIMARY KEY,
    line_name TEXT NOT NULL,
    color     TEXT
);


-- Edges / Connections

CREATE TABLE edges (
    edge_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_station   TEXT NOT NULL,
    destination_station TEXT NOT NULL,
    line_id          TEXT NOT NULL,
    travel_time      INTEGER NOT NULL,

    FOREIGN KEY (source_station)
        REFERENCES stations(station_id),

    FOREIGN KEY (destination_station)
        REFERENCES stations(station_id),

    FOREIGN KEY (line_id)
        REFERENCES lines(line_id),

    CHECK (travel_time > 0),

    UNIQUE (source_station, destination_station, line_id)
);

-- Indexes

CREATE INDEX idx_edges_source
ON edges(source_station);

CREATE INDEX idx_edges_destination
ON edges(destination_station);

CREATE INDEX idx_edges_line
ON edges(line_id);