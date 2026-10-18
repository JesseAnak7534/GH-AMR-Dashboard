-- IEEE NaN and the infinities are valid double precision values, and PostgreSQL
-- orders NaN above every number. So "mic_value > 0" and "total_reads >= 0" are
-- both true of NaN, and a one-sided range check admits it silently. A NaN MIC is
-- then stored looking like a measurement, and every mean, minimum and percentile
-- over the column becomes NaN.
--
-- The legacy ast_results table holds 3,344 such values, one on every
-- disc-diffusion row -- rows that never had an MIC at all.

ALTER TABLE phenotypes DROP CONSTRAINT IF EXISTS phenotypes_mic_value_check;
ALTER TABLE phenotypes ADD CONSTRAINT phenotypes_mic_value_check
  CHECK (mic_value IS NULL
         OR (mic_value > 0
             AND mic_value <> 'NaN'::double precision
             AND mic_value <> 'Infinity'::double precision
             AND mic_value <> '-Infinity'::double precision));

ALTER TABLE genomic_results DROP CONSTRAINT IF EXISTS genomic_results_total_reads_check;
ALTER TABLE genomic_results ADD CONSTRAINT genomic_results_total_reads_check
  CHECK (total_reads IS NULL
         OR (total_reads >= 0
             AND total_reads <> 'NaN'::double precision
             AND total_reads <> 'Infinity'::double precision
             AND total_reads <> '-Infinity'::double precision));

ALTER TABLE genomic_results DROP CONSTRAINT IF EXISTS genomic_results_mean_depth_check;
ALTER TABLE genomic_results ADD CONSTRAINT genomic_results_mean_depth_check
  CHECK (mean_depth IS NULL
         OR (mean_depth >= 0
             AND mean_depth <> 'NaN'::double precision
             AND mean_depth <> 'Infinity'::double precision
             AND mean_depth <> '-Infinity'::double precision));

ALTER TABLE genomic_results DROP CONSTRAINT IF EXISTS genomic_results_n50_check;
ALTER TABLE genomic_results ADD CONSTRAINT genomic_results_n50_check
  CHECK (n50 IS NULL
         OR (n50 >= 0
             AND n50 <> 'NaN'::double precision
             AND n50 <> 'Infinity'::double precision
             AND n50 <> '-Infinity'::double precision));
