-- Snapshot the two demo datasets (AMR_Training_Data, Kobo Sync) before the
-- database is cleared for the synthetic test dataset. Copied server-side into a
-- schema of its own, so this costs nothing and leaves a way back.
--
-- legacy_backup is not in PostgREST's exposed schema list, so these tables are
-- not reachable through the public API and need no RLS policies of their own.
--
-- Replayed on an empty database this simply creates empty archive tables.

CREATE SCHEMA IF NOT EXISTS legacy_backup;
REVOKE ALL ON SCHEMA legacy_backup FROM anon, authenticated;

DROP TABLE IF EXISTS legacy_backup.datasets;
DROP TABLE IF EXISTS legacy_backup.samples;
DROP TABLE IF EXISTS legacy_backup.ast_results;
DROP TABLE IF EXISTS legacy_backup.signals;
DROP TABLE IF EXISTS legacy_backup.signal_actions;

CREATE TABLE legacy_backup.datasets       AS SELECT * FROM public.datasets;
CREATE TABLE legacy_backup.samples        AS SELECT * FROM public.samples;
CREATE TABLE legacy_backup.ast_results    AS SELECT * FROM public.ast_results;
CREATE TABLE legacy_backup.signals        AS SELECT * FROM public.signals;
CREATE TABLE legacy_backup.signal_actions AS SELECT * FROM public.signal_actions;

COMMENT ON SCHEMA legacy_backup IS
  'Snapshot of the demo data (AMR_Training_Data, Kobo Sync) taken 2026-09-29 '
  'before clearing the database for the synthetic test dataset. The normalised '
  'chain is not copied because it was itself derived from these wide tables by '
  'migration 20260929080716 and can be rebuilt from them.';
