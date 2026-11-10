-- Close the Rapid Metro loop.
--
-- The loop runs Sikanderpur - Phase 2 - Belvedere Towers - Cyber City - Moulsari Avenue -
-- Phase 3 - Phase 2, but the Phase 3 - Phase 2 link was missing, so a trip between the
-- two went the long way round through four other stations. The 120 s travel time is
-- estimated from the ~0.66 km between them, using DMRC's 132 s for the ~1 km
-- Phase-I - Sikanderpur (Rapid Metro) hop as a guide.

-- Stored in both directions like the rest of the table.
INSERT INTO edges (source_station, destination_station, line_id, travel_time)
VALUES ('153', '149', 'Gurgaon1', 120),
       ('149', '153', 'Gurgaon1', 120);
