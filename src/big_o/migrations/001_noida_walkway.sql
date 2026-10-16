-- Connect the Noida Aqua Line to the rest of the network.
--
-- The Aqua Line's Noida Sector 51 and the Blue Line's Noida Sec-52 are separate
-- stations joined by a pedestrian skywalk (~300 m), so without this link no route
-- could cross between the Aqua Line and any other line.
--
-- Walking transfers are modelled as a "line" whose kind is 'walkway': the router
-- treats such edges as on foot, so they never count as an extra interchange and the
-- UI labels them "Walk to ...". The 300 s (5 min) travel time is an estimate.

ALTER TABLE lines
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'metro' CHECK (kind IN ('metro', 'walkway'));

INSERT INTO lines (line_id, line_name, color, kind)
VALUES ('Walkway', 'Walkway (on foot)', '9CA3AF', 'walkway');

-- Edges are stored in both directions, matching the rest of the table.
INSERT INTO edges (source_station, destination_station, line_id, travel_time)
SELECT a.station_id, b.station_id, 'Walkway', 300
FROM stations a, stations b
WHERE (a.station_name = 'Noida Sec-52' AND b.station_name = 'Noida Sector 51')
   OR (a.station_name = 'Noida Sector 51' AND b.station_name = 'Noida Sec-52');
