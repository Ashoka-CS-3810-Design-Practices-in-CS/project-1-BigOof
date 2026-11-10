-- Fix Adarsh Nagar's coordinates.
--
-- The station was stored at 28.696377, 77.208809, which is between Guru Tegh Bahadur
-- Nagar and Vishwavidyalaya, so the map drew Jahangirpuri - Adarsh Nagar - Azadpur as
-- long diagonals across Model Town. The real station is between Jahangirpuri and
-- Azadpur (OpenStreetMap / Wikipedia: 28°42'51"N 77°10'02"E).

UPDATE stations SET latitude = 28.714167, longitude = 77.167222 WHERE station_id = '40';
