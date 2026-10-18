-- subjects_human_needs_pseudonym forbade a human subject with no pseudonym,
-- but src.ingest._subject_identity builds exactly that whenever the source
-- record carried no patient number: it returns a 'specimen:<id>' key and leaves
-- patient_pseudonym NULL. The database and the ingest path therefore disagreed,
-- and anonymised human data could not be stored at all.
--
-- Forbidding the case does not make the data linkable. It only invites someone
-- to invent an identifier, and a fabricated pseudonym is worse than an admitted
-- gap, because it looks like patient linkage that does not exist. The
-- 'specimen:' key is unique per specimen, so CLSI M39 deduplication treats it as
-- unkeyed and reports it as such rather than claiming one isolate per patient.
--
-- Upload validation is unchanged: local_patient_id and facility_code remain
-- required for HUMAN rows, so the normal path still demands linkage.

ALTER TABLE subjects DROP CONSTRAINT IF EXISTS subjects_human_needs_pseudonym;
ALTER TABLE subjects ADD CONSTRAINT subjects_human_needs_pseudonym
  CHECK (sector <> 'human'
         OR (patient_pseudonym IS NOT NULL AND facility_code IS NOT NULL)
         OR subject_id LIKE 'specimen:%');
