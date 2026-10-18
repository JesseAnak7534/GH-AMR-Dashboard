-- Extend the pre-wipe snapshot to the consumption, prescribing and alerting
-- tables, and to the normalised chain.
--
-- Replayed on an empty database this simply creates empty archive tables.

DROP TABLE IF EXISTS legacy_backup.amc_records;
DROP TABLE IF EXISTS legacy_backup.amu_records;
DROP TABLE IF EXISTS legacy_backup.pps_surveys;
DROP TABLE IF EXISTS legacy_backup.pps_prescriptions;
DROP TABLE IF EXISTS legacy_backup.alerts;
DROP TABLE IF EXISTS legacy_backup.alert_subscriptions;
DROP TABLE IF EXISTS legacy_backup.predictions;
DROP TABLE IF EXISTS legacy_backup.report_history;
DROP TABLE IF EXISTS legacy_backup.scheduled_reports;
DROP TABLE IF EXISTS legacy_backup.subjects;
DROP TABLE IF EXISTS legacy_backup.encounters;
DROP TABLE IF EXISTS legacy_backup.specimens;
DROP TABLE IF EXISTS legacy_backup.isolates;
DROP TABLE IF EXISTS legacy_backup.phenotypes;
DROP TABLE IF EXISTS legacy_backup.genomic_results;
DROP TABLE IF EXISTS legacy_backup.sequencing_runs;
DROP TABLE IF EXISTS legacy_backup.custody_events;

CREATE TABLE legacy_backup.amc_records         AS SELECT * FROM public.amc_records;
CREATE TABLE legacy_backup.amu_records         AS SELECT * FROM public.amu_records;
CREATE TABLE legacy_backup.pps_surveys         AS SELECT * FROM public.pps_surveys;
CREATE TABLE legacy_backup.pps_prescriptions   AS SELECT * FROM public.pps_prescriptions;
CREATE TABLE legacy_backup.alerts              AS SELECT * FROM public.alerts;
CREATE TABLE legacy_backup.alert_subscriptions AS SELECT * FROM public.alert_subscriptions;
CREATE TABLE legacy_backup.predictions         AS SELECT * FROM public.predictions;
CREATE TABLE legacy_backup.report_history      AS SELECT * FROM public.report_history;
CREATE TABLE legacy_backup.scheduled_reports   AS SELECT * FROM public.scheduled_reports;
CREATE TABLE legacy_backup.subjects            AS SELECT * FROM public.subjects;
CREATE TABLE legacy_backup.encounters          AS SELECT * FROM public.encounters;
CREATE TABLE legacy_backup.specimens           AS SELECT * FROM public.specimens;
CREATE TABLE legacy_backup.isolates            AS SELECT * FROM public.isolates;
CREATE TABLE legacy_backup.phenotypes          AS SELECT * FROM public.phenotypes;
CREATE TABLE legacy_backup.genomic_results     AS SELECT * FROM public.genomic_results;
CREATE TABLE legacy_backup.sequencing_runs     AS SELECT * FROM public.sequencing_runs;
CREATE TABLE legacy_backup.custody_events      AS SELECT * FROM public.custody_events;

REVOKE ALL ON ALL TABLES IN SCHEMA legacy_backup FROM anon, authenticated;
