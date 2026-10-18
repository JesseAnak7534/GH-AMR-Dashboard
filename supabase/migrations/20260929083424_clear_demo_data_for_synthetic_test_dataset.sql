-- ###########################################################################
-- DESTRUCTIVE. This migration empties every surveillance table.
--
-- It is kept here because it is part of the applied history of this project's
-- database, not because it should be run again. On a fresh or empty database it
-- is a no-op; on a database holding data it will remove all of it. Do not
-- replay it against a restored production snapshot.
-- ###########################################################################
--
-- Remove the two demo datasets (AMR_Training_Data, Kobo Sync) and everything
-- derived from them, so the platform holds only the synthetic test dataset and
-- every figure on screen comes from data whose construction is known.
--
-- A full snapshot was taken first, in migrations 20260929081340 and
-- 20260929081752. The legacy_backup schema still holds every row of all of
-- this and is not reachable through the public API.
--
-- The users table is deliberately untouched: accounts are configuration, not
-- surveillance data.

-- Children first. The chain has ON DELETE CASCADE, so this is belt and braces
-- rather than strictly required, but it makes the order of removal explicit.
DELETE FROM custody_events;
DELETE FROM phenotypes;
DELETE FROM genomic_results;
DELETE FROM sequencing_runs;
DELETE FROM isolates;
DELETE FROM specimens;
DELETE FROM encounters;
DELETE FROM subjects;

-- Legacy wide tables, still read by the Dashboard page.
DELETE FROM ast_results;
DELETE FROM samples;

-- Signals and their action log were computed from the data above, so they
-- describe nothing once it is gone.
DELETE FROM signal_actions;
DELETE FROM signals;

-- Consumption and prescribing.
DELETE FROM amc_records;
DELETE FROM amu_records;
DELETE FROM pps_prescriptions;
DELETE FROM pps_surveys;

-- Alerting and reporting artefacts (already empty, cleared for completeness).
DELETE FROM alerts;
DELETE FROM alert_subscriptions;
DELETE FROM predictions;
DELETE FROM report_history;

DELETE FROM datasets;

ANALYZE;
