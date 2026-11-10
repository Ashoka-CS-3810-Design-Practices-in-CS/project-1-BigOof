-- Bring the network up to date with what DMRC runs as of October 2026.
--
-- Sources: DMRC's own line and station lists (backend.delhimetrorail.com, the API
-- behind delhimetrorail.com's journey planner), OpenStreetMap for the coordinates
-- of the new stations, and Wikipedia for opening dates.
--
-- What changes:
--   * Pink Line ring: Majlis Park - Maujpur-Babarpur opened on 8 March 2026, so the
--     Pink Line is now a closed loop. Soorghat is built but not yet open (trains run
--     through it), so it is left out and Jagatpur-Wazirabad links straight to
--     Nanaksar-Sonia Vihar.
--   * Maujpur-Babarpur - Shiv Vihar becomes its own line. DMRC runs it as a
--     separate service ("Pink (Ext.)"), and its planner counts the change at Maujpur.
--   * Magenta Line: Krishna Park Extension (opened 5 January 2025) beyond Janakpuri West,
--     and the separate Majlis Park - Deepali Chowk stretch (opened 8 March 2026). The
--     two stretches aren't joined yet, so the new one gets its own line ID.
--   * Airport Express: Yashobhoomi Dwarka Sector-25 (opened 17 September 2023).
--   * Green Line: trains also stop at Punjabi Bagh West, an interchange with the Pink Line.
--   * The Dhaula Kuan (Airport Express) - Durgabai Deshmukh South Campus (Pink) footbridge,
--     which DMRC's planner treats as a 15-minute walk.
--   * Sikanderpur: Rapid Metro trains no longer pass through the Yellow Line station;
--     the two stations are joined by a walkway instead.
--   * Official renames, plus a few spelling fixes.
--
-- Travel times use DMRC's planner figures where they look real (Green Line, Airport
-- Express, Rapid Metro). DMRC's figures for the 2026 stretches are placeholders: 2 s for
-- Majlis Park - Burari and Prashant Vihar - Madhuban Chowk, and a flat 126 s (Pink) or
-- 108 s (Magenta) for every other hop. Those edges, and Krishna Park Extension (DMRC
-- quotes 12 minutes, which includes waiting for its alternate-train service), are
-- estimated from the station-to-station distance with each line's fit of the existing
-- data: Pink 85 s + 53 s/km, Magenta 80 s + 50 s/km.

PRAGMA foreign_keys = ON;

-- Lines

INSERT INTO lines (line_id, line_name, color, kind) VALUES
    ('Delhi7Ext', 'Pink Line (Shiv Vihar Branch)', 'F172AC', 'metro'),
    ('Delhi8Ext', 'Magenta Line (Majlis Park - Deepali Chowk)', 'C6168D', 'metro');

UPDATE lines SET line_name = 'Pink Line (Ring)' WHERE line_id = 'Delhi7';

-- Renamed stations (DMRC's current names; the old name is kept in brackets where
-- riders are likely to still search for it)

UPDATE stations SET station_name = 'Madhuban Chowk (Pitampura)' WHERE station_id = '18';
UPDATE stations SET station_name = 'Rohini (Rohini East)' WHERE station_id = '19';
UPDATE stations SET station_name = 'Dr. Baba Saheb Ambedkar Hospital (Rohini West)' WHERE station_id = '20';
UPDATE stations SET station_name = 'Seva Teerth (Udyog Bhawan)' WHERE station_id = '53';
UPDATE stations SET station_name = 'Millennium City Centre Gurugram' WHERE station_id = '71';
UPDATE stations SET station_name = 'Dwarka-Kakrola' WHERE station_id = '113';
UPDATE stations SET station_name = 'Shree Ram Mandir Mayur Vihar' WHERE station_id = '224';
UPDATE stations SET station_name = 'Mansarovar Park' WHERE station_id = '3';
UPDATE stations SET station_name = 'Netaji Subhash Place' WHERE station_id = '16';
UPDATE stations SET station_name = 'Subhash Nagar' WHERE station_id = '105';

-- New stations (coordinates from OpenStreetMap)

INSERT INTO stations (station_id, station_name, latitude, longitude) VALUES
    ('521', 'Burari', 28.729829, 77.19957),
    ('522', 'Jharoda Majra', 28.724965, 77.213712),
    ('523', 'Jagatpur - Wazirabad', 28.721116, 77.223995),
    ('524', 'Nanaksar - Sonia Vihar', 28.708718, 77.242509),
    ('525', 'Khajuri Khas', 28.705261, 77.254499),
    ('526', 'Bhajanpura', 28.703599, 77.262647),
    ('527', 'Yamuna Vihar', 28.702376, 77.277311),
    ('528', 'Krishna Park Extension', 28.647792, 77.084343),
    ('529', 'Deepali Chowk', 28.6981, 77.118279),
    ('530', 'Uttari Pitampura - Prashant Vihar', 28.713074, 77.138731),
    ('531', 'Haiderpur Village', 28.724899, 77.142467),
    ('532', 'Bhalaswa', 28.736957, 77.168087),
    ('533', 'Yashobhoomi Dwarka Sector - 25', 28.550832, 77.045307);

-- Shiv Vihar branch: move Maujpur-Babarpur - Gokulpuri - Johri Enclave - Shiv Vihar
-- off the ring's line ID.

UPDATE edges SET line_id = 'Delhi7Ext'
WHERE line_id = 'Delhi7'
  AND source_station IN ('215', '216', '217', '218')
  AND destination_station IN ('215', '216', '217', '218');

-- Green Line: Punjabi Bagh - Punjabi Bagh West - Shivaji Park replaces the direct
-- Punjabi Bagh - Shivaji Park run (times from DMRC's planner).

DELETE FROM edges
WHERE line_id = 'Delhi5'
  AND ((source_station = '33' AND destination_station = '32')
    OR (source_station = '32' AND destination_station = '33'));

-- Sikanderpur: the Yellow Line station (68) and the Rapid Metro station (148) are two
-- buildings joined by a footbridge, but Rapid Metro trains were routed through the
-- Yellow Line station (Phase-I - 68 - 148 - Phase 2), so riding the Rapid Metro past
-- Sikanderpur looked like a stop on the Yellow Line, and reaching the Rapid Metro
-- station from the Yellow Line counted an extra interchange. Trains now run
-- Phase-I - 148 directly (132 s, from DMRC) and 68 - 148 is a 3-minute walk.

DELETE FROM edges
WHERE line_id = 'Gurgaon1'
  AND ((source_station = '168' AND destination_station = '68')
    OR (source_station = '68' AND destination_station = '168')
    OR (source_station = '68' AND destination_station = '148')
    OR (source_station = '148' AND destination_station = '68'));

-- New edges, stored in both directions like the rest of the table.

WITH new_edges (a, b, line_id, travel_time) AS (
    VALUES
        -- Pink Line ring: Majlis Park - Maujpur-Babarpur
        ('173', '521', 'Delhi7', 181),
        ('521', '522', 'Delhi7', 164),
        ('522', '523', 'Delhi7', 143),
        ('523', '524', 'Delhi7', 205),   -- runs through Soorghat, not yet open
        ('524', '525', 'Delhi7', 150),
        ('525', '526', 'Delhi7', 128),
        ('526', '527', 'Delhi7', 161),
        ('527', '215', 'Delhi7', 149),
        -- Magenta Line: Janakpuri West - Krishna Park Extension
        ('108', '528', 'Delhi8', 186),
        -- Magenta Line: Majlis Park - Deepali Chowk
        ('173', '532', 'Delhi8Ext', 179),
        ('532', '38', 'Delhi8Ext', 215),
        ('38', '531', 'Delhi8Ext', 130),
        ('531', '530', 'Delhi8Ext', 148),
        ('530', '18', 'Delhi8Ext', 148),
        ('18', '529', 'Delhi8Ext', 145),
        -- Airport Express: Dwarka Sector-21 - Yashobhoomi Dwarka Sector-25
        ('121', '533', 'DelhiAirport', 124),   -- DMRC's figure
        -- Green Line via Punjabi Bagh West
        ('33', '176', 'Delhi5', 140),
        ('176', '32', 'Delhi5', 146),
        -- Rapid Metro: Phase-I - Sikanderpur (Rapid Metro)
        ('168', '148', 'Gurgaon1', 132),
        -- Sikanderpur (Yellow Line) - Sikanderpur (Rapid Metro) footbridge
        ('68', '148', 'Walkway', 180),
        -- Dhaula Kuan - Durgabai Deshmukh South Campus footbridge (DMRC: 15 minutes)
        ('156', '181', 'Walkway', 900)
)
INSERT INTO edges (source_station, destination_station, line_id, travel_time)
SELECT a, b, line_id, travel_time FROM new_edges
UNION ALL
SELECT b, a, line_id, travel_time FROM new_edges;
