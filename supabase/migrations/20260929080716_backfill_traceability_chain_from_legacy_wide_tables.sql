-- Rebuild subjects -> specimens -> isolates -> phenotypes from the legacy wide
-- tables (samples, ast_results), which are the only surviving copy of this data.
--
-- On patient identity: the legacy samples table has no patient column at all --
-- no hospital number, no sex, no age, no ward. There is no patient to
-- pseudonymise, so patient_pseudonym is left NULL rather than filled with a hash
-- of the sample id. Such a hash would be unique per specimen: it would look like
-- a patient key while grouping nothing, and first-isolate deduplication would
-- silently report one isolate per patient. Every subject therefore takes the
-- 'specimen:' key that src.ingest._subject_identity mints for this exact case.

-- 1. subjects -----------------------------------------------------------------
INSERT INTO subjects (dataset_id, subject_id, sector, animal_species,
                      food_commodity, water_body, sampling_point, created_by)
SELECT s.dataset_id,
       'specimen:' || s.sample_id,
       lower(btrim(s.source_category)),
       CASE WHEN lower(btrim(s.source_category)) IN ('animal', 'aquaculture')
            THEN nullif(btrim(s.source_type), '') END,
       CASE WHEN lower(btrim(s.source_category)) = 'food'
            THEN coalesce(nullif(btrim(s.food_matrix), ''),
                          nullif(btrim(s.source_type), '')) END,
       CASE WHEN lower(btrim(s.source_category)) = 'environment'
            THEN coalesce(nullif(btrim(s.environment_matrix), ''),
                          nullif(btrim(s.source_type), '')) END,
       CASE WHEN lower(btrim(s.source_category)) = 'environment'
            THEN nullif(btrim(s.site_type), '') END,
       'backfill: legacy wide tables'
FROM samples s
ON CONFLICT (dataset_id, subject_id) DO NOTHING;

-- 2. specimens ----------------------------------------------------------------
-- specimen_type is set only where the legacy free-text source_type maps to the
-- controlled vocabulary without guessing; anything else stays NULL rather than
-- defaulting. The original string is kept verbatim in specimen_detail either
-- way, so nothing is lost and the mapping can be revisited.
INSERT INTO specimens (dataset_id, specimen_id, subject_id, specimen_type,
                       specimen_detail, collection_datetime, lab_name, region,
                       district, latitude, longitude, created_by)
SELECT s.dataset_id,
       s.sample_id,
       'specimen:' || s.sample_id,
       CASE
         WHEN lower(btrim(s.source_category)) <> 'human' THEN 'Other'
         WHEN lower(btrim(s.source_type)) = 'urine' THEN 'Urine'
         WHEN lower(btrim(s.source_type)) = 'blood' THEN 'Blood'
         WHEN lower(btrim(s.source_type)) IN ('stool', 'faecal', 'rectal swab')
              THEN 'Stool'
         WHEN lower(btrim(s.source_type)) IN ('csf', 'cerebrospinal fluid')
              THEN 'CSF'
         WHEN lower(btrim(s.source_type)) IN ('sputum', 'nasal swab',
                                              'throat swab') THEN 'Respiratory'
         WHEN lower(btrim(s.source_type)) IN ('wound swab', 'wound', 'pus')
              THEN 'Wound/Pus'
         WHEN lower(btrim(s.source_type)) IN ('tissue', 'vaginal swab')
              THEN 'Other'
         ELSE NULL
       END,
       nullif(btrim(s.source_type), ''),
       CASE WHEN s.collection_date ~ '^\d{4}-\d{2}-\d{2}$'
            THEN (s.collection_date)::date::timestamptz END,
       nullif(btrim(s.lab_name), ''),
       nullif(btrim(s.region), ''),
       nullif(btrim(s.district), ''),
       s.latitude,
       s.longitude,
       'backfill: legacy wide tables'
FROM samples s
ON CONFLICT (dataset_id, specimen_id) DO NOTHING;

-- 3. isolates -----------------------------------------------------------------
INSERT INTO isolates (dataset_id, isolate_id, specimen_id, isolate_number,
                      organism, created_by)
SELECT a.dataset_id, a.isolate_id, a.sample_id,
       row_number() OVER (PARTITION BY a.dataset_id, a.sample_id
                          ORDER BY a.organism),
       a.organism,
       'backfill: legacy wide tables'
FROM (SELECT DISTINCT dataset_id, sample_id, isolate_id, organism
      FROM ast_results) a
ON CONFLICT (dataset_id, isolate_id) DO NOTHING;

-- 4. phenotypes ---------------------------------------------------------------
-- Two things are corrected rather than carried forward:
--
--   * Every disc-diffusion row carries mic_value = NaN and no zone diameter. A
--     disc test yields a zone, not an MIC, and NaN is not a measurement --
--     PostgreSQL merely orders it above every number, which is how it passed the
--     old "mic_value > 0" check. Non-finite MICs become NULL.
--   * breakpoint_version is recorded as unrecorded rather than invented. The
--     legacy table names a guideline family but no edition, and an S/I/R that
--     cannot be traced to an edition cannot be reproduced.
--
-- result_source is 'Imported' throughout: ast_results.auto_interpreted is 0 on
-- every row, so these arrived already interpreted with provenance unknown.
INSERT INTO phenotypes (dataset_id, isolate_id, antibiotic, result, mic_value,
                        zone_diameter, ast_method, breakpoint_standard,
                        breakpoint_version, result_source, test_date, created_by)
SELECT a.dataset_id, a.isolate_id, a.antibiotic,
       nullif(btrim(a.result), ''),
       CASE WHEN a.mic_value IS NOT NULL
             AND a.mic_value > 0
             AND a.mic_value <> 'NaN'::double precision
             AND a.mic_value <> 'Infinity'::double precision
             AND a.mic_value <> '-Infinity'::double precision
            THEN a.mic_value END,
       a.zone_diameter,
       nullif(btrim(a.method), ''),
       coalesce(nullif(btrim(a.guideline), ''), 'unrecorded (legacy import)'),
       'unrecorded (legacy import)',
       'Imported',
       CASE WHEN a.test_date ~ '^\d{4}-\d{2}-\d{2}$'
            THEN (a.test_date)::date END,
       'backfill: legacy wide tables'
FROM ast_results a
ON CONFLICT (dataset_id, isolate_id, antibiotic) DO NOTHING;

-- 5. custody events -----------------------------------------------------------
-- Same granularity as src.ingest._log_custody: identity, collection,
-- identification, and one ast_performed per isolate rather than one per drug.
-- source_system names the backfill, so none of these reads as an observed
-- handoff that someone witnessed.
--
-- custody_events has a surrogate key and no natural unique constraint, so
-- ON CONFLICT cannot guard these the way it guards the tables above. Each one
-- is therefore guarded by NOT EXISTS on (entity, event_type, source_system),
-- which keeps the whole migration replayable rather than doubling the log.
INSERT INTO custody_events (dataset_id, entity_type, entity_id, event_type,
                            actor, source_system, reason)
SELECT sp.dataset_id, 'subject', sp.subject_id, 'transferred', 'backfill',
       'legacy wide tables (samples, ast_results)',
       'subject identity established from specimen (no patient identifier in source)'
FROM specimens sp WHERE sp.created_by = 'backfill: legacy wide tables'  AND NOT EXISTS (
        SELECT 1 FROM custody_events ce
        WHERE ce.dataset_id = sp.dataset_id AND ce.entity_type = 'subject'
          AND ce.entity_id = sp.subject_id AND ce.event_type = 'transferred'
          AND ce.source_system = 'legacy wide tables (samples, ast_results)');

INSERT INTO custody_events (dataset_id, entity_type, entity_id, event_type,
                            event_datetime, actor, site, source_system, reason)
SELECT sp.dataset_id, 'specimen', sp.specimen_id, 'collected',
       sp.collection_datetime, 'backfill',
       coalesce(sp.district, sp.region, ''),
       'legacy wide tables (samples, ast_results)',
       'collection date carried from the legacy samples table'
FROM specimens sp WHERE sp.created_by = 'backfill: legacy wide tables'  AND NOT EXISTS (
        SELECT 1 FROM custody_events ce
        WHERE ce.dataset_id = sp.dataset_id AND ce.entity_type = 'specimen'
          AND ce.entity_id = sp.specimen_id AND ce.event_type = 'collected'
          AND ce.source_system = 'legacy wide tables (samples, ast_results)');

INSERT INTO custody_events (dataset_id, entity_type, entity_id, event_type,
                            actor, source_system, reason)
SELECT i.dataset_id, 'isolate', i.isolate_id, 'identified', 'backfill',
       'legacy wide tables (samples, ast_results)',
       'organism carried from the legacy ast_results table; identification method not recorded'
FROM isolates i WHERE i.created_by = 'backfill: legacy wide tables'  AND NOT EXISTS (
        SELECT 1 FROM custody_events ce
        WHERE ce.dataset_id = i.dataset_id AND ce.entity_type = 'isolate'
          AND ce.entity_id = i.isolate_id AND ce.event_type = 'identified'
          AND ce.source_system = 'legacy wide tables (samples, ast_results)');

INSERT INTO custody_events (dataset_id, entity_type, entity_id, event_type,
                            actor, source_system, reason)
SELECT p.dataset_id, 'isolate', p.isolate_id, 'ast_performed', 'backfill',
       'legacy wide tables (samples, ast_results)',
       count(*)::text || ' agent(s); imported already interpreted, breakpoint edition unrecorded'
FROM phenotypes p WHERE p.created_by = 'backfill: legacy wide tables'  AND NOT EXISTS (
        SELECT 1 FROM custody_events ce
        WHERE ce.dataset_id = p.dataset_id AND ce.entity_type = 'isolate'
          AND ce.entity_id = p.isolate_id AND ce.event_type = 'ast_performed'
          AND ce.source_system = 'legacy wide tables (samples, ast_results)')
GROUP BY p.dataset_id, p.isolate_id;

ANALYZE subjects;
ANALYZE specimens;
ANALYZE isolates;
ANALYZE phenotypes;
ANALYZE custody_events;
