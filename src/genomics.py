"""
Reading genomes against phenotypes.

The platform could already store sequencing results -- ``genomic_results`` has
columns for provenance, quality, typing, resistance determinants and clustering
-- and could do nothing with them. Genomic data was counted on the coverage
report and never read again. This module is the analysis the storage was built
for.

Four things it does, and the reasoning behind each:

**Concordance.** A gene call and a susceptibility result are two measurements of
the same property, made by different means. Where they disagree, one of them is
wrong, or the biology is more complicated than either captures. Surfacing the
disagreement is the point: it finds sequencing gaps, testing errors and
mechanisms nobody has named yet. Hiding it behind an overall "agreement
percentage" wastes the only cross-check the platform has.

**Determinant frequency.** What genes are circulating, in which organisms and
which sectors. Always reported with the database and version that produced the
call, for the same reason a susceptibility result is useless without its
breakpoint edition: a gene call is a statement about what a particular database
contained on a particular day.

**Clusters.** ``cluster_id`` was stored and never used. It is what separates
"resistant isolates are accumulating here" from "this is one clone spreading",
and those two findings call for entirely different responses.

**Quality gating.** Depth, coverage breadth, contamination and N50 were stored
and never enforced. A poorly covered assembly will miss genes that are present,
so letting it contribute to a frequency understates that gene -- quietly, and in
the direction that looks reassuring.

A note on what absence means. A gene that is not reported was either not there,
not in the database, or not assembled. Those are different, and this module
never collapses them into "no resistance mechanism". Where a phenotype is
non-susceptible and no determinant explains it, the finding is recorded as a
mechanism *not identified*, which is a statement about the method rather than
about the organism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src import db

# ---------------------------------------------------------------------------
# What a determinant predicts
# ---------------------------------------------------------------------------

#: Determinant -> the agents it is expected to make non-susceptible, with a note
#: on the strength of that expectation.
#:
#: Two deliberate limits. The agent list for each gene is what the gene is
#: *expected* to affect, not everything it has ever been associated with:
#: a mapping that claims too much turns every susceptible result into a
#: discrepancy. And `strong` marks the relationships solid enough that a
#: contradiction is worth investigating; where it is False, a susceptible
#: phenotype is unremarkable and the pair is reported but not flagged.
@dataclass(frozen=True)
class Determinant:
    gene: str
    agents: Tuple[str, ...]
    mechanism: str
    strong: bool = True
    note: str = ""


DETERMINANTS: Tuple[Determinant, ...] = (
    # -- extended-spectrum beta-lactamases --------------------------------
    Determinant("blaCTX-M-15", ("Ceftriaxone", "Cefotaxime", "Ceftazidime",
                                "Cefepime"), "ESBL"),
    Determinant("blaCTX-M-14", ("Ceftriaxone", "Cefotaxime", "Cefepime"), "ESBL"),
    Determinant("blaCTX-M-27", ("Ceftriaxone", "Cefotaxime", "Cefepime"), "ESBL"),
    Determinant("blaSHV-12", ("Ceftriaxone", "Cefotaxime", "Ceftazidime"), "ESBL"),
    # -- narrow-spectrum: penicillins only, NOT cephalosporins ------------
    Determinant("blaTEM-1", ("Ampicillin", "Amoxicillin"), "Penicillinase",
                note="Narrow spectrum. Does not explain cephalosporin "
                     "resistance, and should not be read as if it did."),
    Determinant("blaSHV-1", ("Ampicillin", "Amoxicillin"), "Penicillinase",
                note="Narrow spectrum."),
    # -- carbapenemases ----------------------------------------------------
    Determinant("blaNDM-1", ("Meropenem", "Imipenem", "Ertapenem", "Ceftriaxone",
                             "Ceftazidime", "Cefepime"), "Metallo-carbapenemase"),
    Determinant("blaNDM-5", ("Meropenem", "Imipenem", "Ertapenem", "Ceftriaxone",
                             "Cefepime"), "Metallo-carbapenemase"),
    Determinant("blaOXA-48", ("Meropenem", "Ertapenem"), "OXA-48-like carbapenemase",
                note="Often gives low-level carbapenem MICs, and can read as "
                     "susceptible to meropenem while still being transmissible."),
    Determinant("blaKPC-2", ("Meropenem", "Imipenem", "Ertapenem", "Ceftriaxone"),
                "KPC carbapenemase"),
    Determinant("blaVIM-1", ("Meropenem", "Imipenem", "Ceftazidime"),
                "Metallo-carbapenemase"),
    # -- AmpC --------------------------------------------------------------
    Determinant("blaCMY-2", ("Ceftriaxone", "Cefoxitin", "Ceftazidime"),
                "Plasmid-mediated AmpC"),
    # -- staphylococcal ----------------------------------------------------
    Determinant("mecA", ("Oxacillin", "Cefoxitin", "Cefoxitin screen"),
                "Altered PBP2a",
                note="Defines methicillin resistance. A mecA-positive isolate "
                     "reading oxacillin-susceptible should be re-checked."),
    Determinant("mecC", ("Oxacillin", "Cefoxitin"), "Altered PBP2a",
                note="Missed by some PBP2a agglutination tests."),
    # -- glycopeptide ------------------------------------------------------
    Determinant("vanA", ("Vancomycin", "Teicoplanin"), "D-Ala-D-Lac ligase"),
    Determinant("vanB", ("Vancomycin",), "D-Ala-D-Lac ligase",
                note="Typically spares teicoplanin."),
    # -- quinolone ---------------------------------------------------------
    Determinant("qnrB1", ("Ciprofloxacin",), "Target protection", strong=False,
                note="Raises the MIC without usually reaching the resistant "
                     "breakpoint on its own, so a susceptible result here is "
                     "expected rather than contradictory."),
    Determinant("qnrS1", ("Ciprofloxacin",), "Target protection", strong=False,
                note="As qnrB1: contributes to, but rarely alone causes, "
                     "resistance."),
    Determinant("gyrA_S83L", ("Ciprofloxacin", "Levofloxacin"),
                "Target-site mutation"),
    Determinant("parC_S80I", ("Ciprofloxacin",), "Target-site mutation",
                strong=False, note="Usually needs a gyrA mutation alongside it."),
    Determinant("aac(6')-Ib-cr", ("Ciprofloxacin",), "Enzymatic modification",
                strong=False),
    # -- aminoglycoside ----------------------------------------------------
    Determinant("armA", ("Amikacin", "Gentamicin", "Tobramycin"),
                "16S rRNA methylase"),
    Determinant("rmtB", ("Amikacin", "Gentamicin", "Tobramycin"),
                "16S rRNA methylase"),
    Determinant("aac(3)-IIa", ("Gentamicin", "Tobramycin"),
                "Enzymatic modification"),
    # -- other classes -----------------------------------------------------
    Determinant("mcr-1", ("Colistin",), "Phosphoethanolamine transferase"),
    Determinant("sul1", ("Trimethoprim-Sulfamethoxazole",), "Sulfonamide target",
                strong=False, note="Sulfonamide component only."),
    Determinant("sul2", ("Trimethoprim-Sulfamethoxazole",), "Sulfonamide target",
                strong=False),
    Determinant("dfrA17", ("Trimethoprim-Sulfamethoxazole",),
                "Trimethoprim target"),
    Determinant("tet(A)", ("Tetracycline", "Doxycycline"), "Efflux", strong=False,
                note="Tetracycline efflux; doxycycline often remains active."),
    Determinant("tet(B)", ("Tetracycline", "Doxycycline"), "Efflux", strong=False),
    Determinant("ermB", ("Erythromycin", "Clindamycin", "Azithromycin"),
                "rRNA methylase"),
    Determinant("catA1", ("Chloramphenicol",), "Acetyltransferase"),
    Determinant("floR", ("Chloramphenicol",), "Phenicol efflux"),
    # -- narrow-spectrum oxacillinase --------------------------------------
    # Common, and commonly misread. It is poorly inhibited by clavulanate and
    # tazobactam, so it accounts for resistance to the inhibitor combinations
    # while leaving cephalosporins and carbapenems untouched. Reading it as a
    # general beta-lactamase would explain away resistance it has nothing to do
    # with.
    Determinant("blaOXA-1", ("Amoxicillin-Clavulanate", "Piperacillin-Tazobactam",
                             "Ampicillin", "Amoxicillin"), "Oxacillinase",
                note="Not an ESBL and not a carbapenemase. Explains the "
                     "inhibitor combinations, not cephalosporins."),
    # -- staphylococcal penicillinase --------------------------------------
    Determinant("blaZ", ("Penicillin", "Ampicillin", "Amoxicillin"),
                "Staphylococcal penicillinase",
                note="Does not confer oxacillin resistance; that needs mec."),
    # -- acinetobacter carbapenemases --------------------------------------
    Determinant("blaOXA-23", ("Meropenem", "Imipenem"),
                "OXA-23-like carbapenemase",
                note="The usual cause of carbapenem resistance in "
                     "Acinetobacter baumannii."),
    Determinant("blaOXA-51", ("Meropenem",), "Intrinsic oxacillinase",
                strong=False,
                note="Intrinsic to A. baumannii and used to identify the "
                     "species. On its own it gives little or no carbapenem "
                     "resistance, so a susceptible result is expected."),
    # -- aminoglycoside: streptomycin only ---------------------------------
    # strA and strB. They travel together and act on streptomycin; they do not
    # explain gentamicin or amikacin, and treating them as general
    # aminoglycoside resistance would hide a real 16S methylase.
    Determinant("aph(3'')-Ib", ("Streptomycin",), "Aminoglycoside "
                "phosphotransferase",
                note="strA. Streptomycin only."),
    Determinant("aph(6)-Id", ("Streptomycin",), "Aminoglycoside "
                "phosphotransferase",
                note="strB, usually alongside strA. Streptomycin only."),
    # -- macrolide ---------------------------------------------------------
    Determinant("mph(A)", ("Azithromycin", "Erythromycin", "Clarithromycin"),
                "Macrolide phosphotransferase"),
    Determinant("ermC", ("Erythromycin", "Clindamycin", "Azithromycin"),
                "rRNA methylase"),
    # -- tetracycline ------------------------------------------------------
    Determinant("tet(M)", ("Tetracycline", "Doxycycline"),
                "Ribosomal protection", strong=False,
                note="Doxycycline and tigecycline often remain active."),
)

#: Determinants that are real, and are not antibiotic resistance.
#:
#: They turn up in the same gene call tables and would otherwise sit in the
#: "no rule" list forever, implying the rule set is incomplete when it is not.
#: Naming them is also the honest answer to a question the concordance check
#: cannot be asked: no susceptibility result on any panel corresponds to them,
#: so they can neither agree nor disagree with a phenotype.
NON_RESISTANCE_MARKERS: Dict[str, str] = {
    "qacE": "Quaternary ammonium efflux -- disinfectant tolerance, and a marker "
            "of a class 1 integron rather than of resistance to any antibiotic.",
    "qacEdelta1": "Truncated qacE, carried on class 1 integrons. As above.",
    "sitABCD": "Iron and manganese transport. A fitness and virulence factor, "
               "not a resistance determinant; it belongs with virulence genes.",
    "intI1": "Class 1 integrase. Marks a mobile platform that often carries "
             "resistance genes, but confers none itself.",
    "IS26": "Insertion sequence. Mobilises resistance genes without conferring "
            "resistance.",
}

#: gene -> Determinant, for lookup.
BY_GENE: Dict[str, Determinant] = {d.gene: d for d in DETERMINANTS}

#: Every agent any determinant speaks to. Concordance is assessed only on these:
#: scoring a gene panel against an agent no gene in it predicts would mark every
#: resistant result as unexplained, which says nothing about the data.
COVERED_AGENTS: Tuple[str, ...] = tuple(sorted(
    {agent for d in DETERMINANTS for agent in d.agents}))


# ---------------------------------------------------------------------------
# Sequencing quality
# ---------------------------------------------------------------------------

#: Minimum assembly quality for a genome's gene calls to be trusted.
#:
#: A thin or fragmented assembly misses genes that are present, so admitting one
#: understates every determinant it failed to find -- in the direction that
#: looks reassuring. These are ordinary bacterial WGS working thresholds, not a
#: standard; they are here to be argued with and adjusted, which is why they are
#: one named structure rather than numbers scattered through the queries.
@dataclass(frozen=True)
class QualityThresholds:
    min_mean_depth: float = 30.0
    min_coverage_breadth: float = 90.0
    max_contamination_pct: float = 5.0
    min_n50: float = 20000.0
    max_contigs: int = 500


DEFAULT_THRESHOLDS = QualityThresholds()

QC_PASS = "pass"
QC_FAIL = "fail"
QC_UNKNOWN = "not assessable"


def assess_quality(frame: pd.DataFrame,
                   thresholds: QualityThresholds = DEFAULT_THRESHOLDS
                   ) -> pd.DataFrame:
    """Add ``qc_verdict`` and ``qc_reason`` to a genomic frame.

    A genome with no quality metrics recorded is "not assessable" rather than a
    pass. Treating unmeasured as acceptable is how an unvetted assembly ends up
    contributing to a national figure.
    """
    out = frame.copy()
    if out.empty:
        out["qc_verdict"] = pd.Series(dtype=str)
        out["qc_reason"] = pd.Series(dtype=str)
        return out

    def judge(row) -> Tuple[str, str]:
        checks = (
            ("mean_depth", row.get("mean_depth"), thresholds.min_mean_depth,
             "below", f"depth < {thresholds.min_mean_depth:g}x"),
            ("coverage_breadth", row.get("coverage_breadth"),
             thresholds.min_coverage_breadth, "below",
             f"coverage < {thresholds.min_coverage_breadth:g}%"),
            ("contamination_pct", row.get("contamination_pct"),
             thresholds.max_contamination_pct, "above",
             f"contamination > {thresholds.max_contamination_pct:g}%"),
            ("n50", row.get("n50"), thresholds.min_n50, "below",
             f"N50 < {thresholds.min_n50:,.0f}"),
            ("contig_count", row.get("contig_count"), thresholds.max_contigs,
             "above", f"contigs > {thresholds.max_contigs:,}"),
        )
        seen = False
        failures: List[str] = []
        for _name, value, limit, direction, message in checks:
            if value is None or (isinstance(value, float) and value != value):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            seen = True
            if direction == "below" and number < limit:
                failures.append(message)
            elif direction == "above" and number > limit:
                failures.append(message)
        if not seen:
            return QC_UNKNOWN, "no quality metrics recorded"
        if failures:
            return QC_FAIL, "; ".join(failures)
        return QC_PASS, ""

    verdicts = [judge(row) for _, row in out.iterrows()]
    out["qc_verdict"] = [v for v, _ in verdicts]
    out["qc_reason"] = [r for _, r in verdicts]
    return out


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

_GENOMIC_SQL = """
    SELECT g.dataset_id, g.genomic_id, g.isolate_id, g.run_id,
           g.total_reads, g.mean_depth, g.coverage_breadth, g.contamination_pct,
           g.n50, g.contig_count, g.qc_status,
           g.assembler, g.pipeline_name, g.pipeline_version,
           g.amr_db_name, g.amr_db_version,
           g.species_confirmed, g.mlst_scheme, g.sequence_type,
           g.amr_genes, g.amr_mutations, g.plasmid_replicons, g.virulence_genes,
           g.cluster_method, g.cluster_id, g.analysis_date, g.review_status,
           i.organism, i.specimen_id,
           sp.specimen_type, sp.collection_datetime, sp.region, sp.district,
           sp.lab_name, sp.ward_type_at_collection,
           s.sector, s.subject_id
    FROM genomic_results g
    JOIN isolates  i  ON i.dataset_id  = g.dataset_id AND i.isolate_id  = g.isolate_id
    JOIN specimens sp ON sp.dataset_id = i.dataset_id AND sp.specimen_id = i.specimen_id
    JOIN subjects  s  ON s.dataset_id  = sp.dataset_id AND s.subject_id = sp.subject_id
"""


def _as_list(value) -> List[str]:
    """Determinant columns arrive as a JSON array, a separated string, or null."""
    if value is None or (isinstance(value, float) and value != value):
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text or text in ("[]", "null", "None"):
        return []
    if text.startswith("["):
        import json
        try:
            parsed = json.loads(text)
            return [str(v).strip() for v in parsed if str(v).strip()]
        except ValueError:
            pass
    for separator in ("|", ";", ","):
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    return [text]


def load_genomic_frame(dataset_id: Optional[str] = None,
                       sector: Optional[str] = None) -> pd.DataFrame:
    """One row per sequenced isolate, joined to its specimen and subject."""
    clauses: List[str] = []
    params: List[object] = []
    if dataset_id:
        clauses.append("g.dataset_id = %s")
        params.append(dataset_id)
    if sector:
        clauses.append("s.sector = %s")
        params.append(str(sector).lower())

    sql = _GENOMIC_SQL + (" WHERE " + " AND ".join(clauses) if clauses else "")
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(params) if params else None)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
    finally:
        conn.close()

    frame = pd.DataFrame([dict(r) for r in rows], columns=columns)
    if frame.empty:
        return frame
    for column in ("amr_genes", "amr_mutations", "plasmid_replicons",
                   "virulence_genes"):
        frame[column] = frame[column].map(_as_list)
    frame["collection_datetime"] = pd.to_datetime(
        frame["collection_datetime"], errors="coerce", utc=True)
    return assess_quality(frame)


def determinants_of(row) -> List[str]:
    """Every resistance determinant on one genome, genes and mutations together."""
    return list(row.get("amr_genes") or []) + list(row.get("amr_mutations") or [])


# ---------------------------------------------------------------------------
# Genotype against phenotype
# ---------------------------------------------------------------------------

#: The four ways a gene call and a susceptibility result can stand to each
#: other. Named rather than scored, because they mean different things and call
#: for different follow-up.
CONCORDANT_RESISTANT = "explained resistance"
CONCORDANT_SUSCEPTIBLE = "no determinant, susceptible"
GENOTYPE_ONLY = "determinant found, tested susceptible"
PHENOTYPE_ONLY = "resistance with no determinant identified"

#: Non-susceptible for this purpose is I or R together. An intermediate result
#: is not susceptibility, and for a mechanism question the clinically relevant
#: split is "the drug works" against "it does not reliably".
NON_SUSCEPTIBLE = ("R", "I", "NS")


def concordance(genomic: pd.DataFrame,
                phenotypes: Optional[pd.DataFrame] = None,
                *, dataset_id: Optional[str] = None,
                exclude_failed_qc: bool = True) -> pd.DataFrame:
    """Compare every determinant call against the matching susceptibility result.

    One row per isolate and agent, for agents some determinant in the panel
    speaks to. Agents nothing predicts are left out entirely: including them
    would mark every resistant result as unexplained and say nothing.

    ``exclude_failed_qc`` drops genomes whose assembly failed quality. Their
    absent genes cannot be distinguished from genes the assembly missed, so
    scoring them manufactures discrepancies out of sequencing depth.
    """
    if genomic.empty:
        return pd.DataFrame()

    working = genomic
    if exclude_failed_qc and "qc_verdict" in working.columns:
        working = working[working["qc_verdict"] != QC_FAIL]
    if working.empty:
        return pd.DataFrame()

    if phenotypes is None:
        phenotypes = _load_phenotypes(dataset_id)
    if phenotypes.empty:
        return pd.DataFrame()

    # phenotype lookup: (dataset, isolate, agent) -> result
    results: Dict[Tuple[str, str, str], str] = {}
    for _, row in phenotypes.iterrows():
        key = (str(row.get("dataset_id")), str(row.get("isolate_id")),
               str(row.get("antibiotic")))
        value = row.get("result")
        if value is not None and str(value).strip():
            results[key] = str(value).strip().upper()

    rows: List[Dict[str, object]] = []
    for _, genome in working.iterrows():
        found = set(determinants_of(genome))
        dataset = str(genome.get("dataset_id"))
        isolate = str(genome.get("isolate_id"))

        for agent in COVERED_AGENTS:
            result = results.get((dataset, isolate, agent))
            if result is None:
                continue                      # the agent was not tested

            explaining = [d for d in DETERMINANTS
                          if agent in d.agents and d.gene in found]
            non_susceptible = result in NON_SUSCEPTIBLE

            if explaining and non_susceptible:
                verdict = CONCORDANT_RESISTANT
            elif explaining and not non_susceptible:
                verdict = GENOTYPE_ONLY
            elif not explaining and non_susceptible:
                verdict = PHENOTYPE_ONLY
            else:
                verdict = CONCORDANT_SUSCEPTIBLE

            # Only a strong expectation makes a contradiction worth chasing. A
            # qnr gene with a susceptible ciprofloxacin result is the normal
            # case, not a discrepancy, and flagging it would bury the real ones.
            notable = bool(verdict == GENOTYPE_ONLY
                           and any(d.strong for d in explaining))

            rows.append({
                "dataset_id": dataset,
                "isolate_id": isolate,
                "organism": genome.get("organism"),
                "sector": genome.get("sector"),
                "specimen_type": genome.get("specimen_type"),
                "lab_name": genome.get("lab_name"),
                "antibiotic": agent,
                "result": result,
                "non_susceptible": non_susceptible,
                "determinants": "; ".join(d.gene for d in explaining),
                "mechanism": "; ".join(sorted({d.mechanism for d in explaining})),
                "verdict": verdict,
                "notable": notable,
                "amr_db_name": genome.get("amr_db_name"),
                "amr_db_version": genome.get("amr_db_version"),
                "qc_verdict": genome.get("qc_verdict"),
            })

    return pd.DataFrame(rows)


def _load_phenotypes(dataset_id: Optional[str]) -> pd.DataFrame:
    sql = ("SELECT dataset_id, isolate_id, antibiotic, result "
           "FROM phenotypes WHERE result IS NOT NULL")
    params: Tuple[object, ...] = ()
    if dataset_id:
        sql += " AND dataset_id = %s"
        params = (dataset_id,)
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or None)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
    finally:
        conn.close()
    return pd.DataFrame([dict(r) for r in rows], columns=columns)


def concordance_summary(table: pd.DataFrame) -> Dict[str, object]:
    """Headline counts, with agreement stated only where it means something.

    The percentage covers pairs the determinant panel can speak to at all, and
    is reported alongside the two kinds of disagreement rather than instead of
    them: an agreement figure on its own hides whether the misses are
    undetected mechanisms or genes that are not being expressed.
    """
    if table.empty:
        return {"pairs": 0, "isolates": 0}

    counts = table["verdict"].value_counts().to_dict()
    agree = counts.get(CONCORDANT_RESISTANT, 0) + counts.get(CONCORDANT_SUSCEPTIBLE, 0)
    total = len(table)
    return {
        "pairs": total,
        "isolates": int(table["isolate_id"].nunique()),
        "agents": int(table["antibiotic"].nunique()),
        "agreement_percent": round(100.0 * agree / total, 1) if total else None,
        "explained_resistance": counts.get(CONCORDANT_RESISTANT, 0),
        "no_determinant_susceptible": counts.get(CONCORDANT_SUSCEPTIBLE, 0),
        "determinant_but_susceptible": counts.get(GENOTYPE_ONLY, 0),
        "resistance_unexplained": counts.get(PHENOTYPE_ONLY, 0),
        "notable_contradictions": int(table["notable"].sum()),
    }


def unexplained_resistance(table: pd.DataFrame) -> pd.DataFrame:
    """Where an isolate resists a drug and no determinant accounts for it.

    Worth looking at rather than worth correcting. The usual explanations are
    efflux or porin loss, a determinant the database does not carry, or a region
    the assembly did not cover -- all of which are findings about the method,
    not evidence that the laboratory is wrong.
    """
    if table.empty:
        return table
    out = table[table["verdict"] == PHENOTYPE_ONLY]
    if out.empty:
        return out
    return (out.groupby(["organism", "antibiotic"], dropna=False)
               .agg(isolates=("isolate_id", "nunique"))
               .reset_index()
               .sort_values("isolates", ascending=False))


def contradictions(table: pd.DataFrame) -> pd.DataFrame:
    """Isolates carrying a determinant that strongly predicts resistance, which
    nonetheless tested susceptible.

    These are the ones to re-check. A mecA-positive staphylococcus reading
    oxacillin-susceptible is either a mislabelled isolate, a contaminated
    assembly or a testing error, and each is worth knowing about.
    """
    if table.empty or "notable" not in table.columns:
        return pd.DataFrame()
    out = table[table["notable"]]
    columns = [c for c in ("isolate_id", "organism", "antibiotic", "result",
                           "determinants", "mechanism", "lab_name", "sector",
                           "amr_db_name", "amr_db_version")
               if c in out.columns]
    return out[columns].sort_values(["organism", "antibiotic"])


# ---------------------------------------------------------------------------
# What is circulating
# ---------------------------------------------------------------------------

def determinant_frequency(genomic: pd.DataFrame, *, by: Optional[str] = None,
                          exclude_failed_qc: bool = True) -> pd.DataFrame:
    """How often each determinant is found, optionally split by a column.

    The denominator is genomes examined, not determinants counted, so the figure
    reads as "this proportion of sequenced isolates carried it" rather than a
    share of all gene calls -- which would rise simply because some isolates
    carry more genes than others.

    Every row carries the database and version behind the call. A determinant
    result without them cannot be reproduced, for the same reason an S/I/R
    without its breakpoint edition cannot.
    """
    if genomic.empty:
        return pd.DataFrame()

    working = genomic
    if exclude_failed_qc and "qc_verdict" in working.columns:
        working = working[working["qc_verdict"] != QC_FAIL]
    if working.empty:
        return pd.DataFrame()

    groups: List[Tuple[object, pd.DataFrame]]
    if by and by in working.columns:
        groups = list(working.groupby(by, dropna=False))
    else:
        groups = [("All sequenced isolates", working)]

    rows: List[Dict[str, object]] = []
    for label, chunk in groups:
        examined = len(chunk)
        tally: Dict[str, int] = {}
        for _, genome in chunk.iterrows():
            for gene in set(determinants_of(genome)):
                tally[gene] = tally.get(gene, 0) + 1
        databases = sorted({f"{n} {v}".strip() for n, v in zip(
            chunk.get("amr_db_name", pd.Series(dtype=str)).fillna(""),
            chunk.get("amr_db_version", pd.Series(dtype=str)).fillna(""))
            if str(n).strip()})
        for gene, count in sorted(tally.items(), key=lambda kv: -kv[1]):
            known = BY_GENE.get(gene)
            if known is not None:
                mechanism = known.mechanism
            elif gene in NON_RESISTANCE_MARKERS:
                mechanism = "not a resistance determinant"
            else:
                mechanism = "not in the rule set"
            rows.append({
                (by or "group"): label,
                "determinant": gene,
                "mechanism": mechanism,
                "isolates": count,
                "genomes_examined": examined,
                "percent": round(100.0 * count / examined, 1) if examined else None,
                "database": "; ".join(databases) or "unrecorded",
            })
    return pd.DataFrame(rows)


def determinants_not_in_rules(genomic: pd.DataFrame) -> List[str]:
    """Determinants present in the data that the rule set says nothing about.

    Not an error. It is the list to extend DETERMINANTS from, and a reminder
    that concordance only speaks to the genes it knows: a gene absent from the
    rules contributes nothing to explaining a resistant phenotype, so unexplained
    resistance may simply mean an unmapped determinant.
    """
    if genomic.empty:
        return []
    seen: set = set()
    for _, genome in genomic.iterrows():
        seen.update(determinants_of(genome))
    return sorted(seen - set(BY_GENE) - set(NON_RESISTANCE_MARKERS))


def non_resistance_markers_found(genomic: pd.DataFrame) -> Dict[str, str]:
    """Known markers present in the data that confer no antibiotic resistance.

    Reported separately so they neither inflate the "no rule" list nor sit in a
    resistance frequency as though they belonged there.
    """
    if genomic.empty:
        return {}
    seen: set = set()
    for _, genome in genomic.iterrows():
        seen.update(determinants_of(genome))
    return {gene: NON_RESISTANCE_MARKERS[gene]
            for gene in sorted(seen & set(NON_RESISTANCE_MARKERS))}


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

@dataclass
class ClusterReport:
    """What the clustering shows, and what it does not."""
    clusters: pd.DataFrame
    members: pd.DataFrame
    methods: List[str] = field(default_factory=list)
    unclustered: int = 0

    @property
    def summary(self) -> str:
        if self.clusters.empty:
            return ("No clusters were recorded. Either clustering has not been "
                    "run, or no two sequenced isolates were assigned to the "
                    "same cluster.")
        multi = self.clusters[self.clusters["isolates"] > 1]
        crossing = int((self.clusters["sectors"] > 1).sum())
        method = ", ".join(self.methods) if self.methods else "unrecorded method"
        text = (f"{len(multi):,} cluster(s) hold more than one isolate, out of "
                f"{len(self.clusters):,} assigned, by {method}. "
                f"{self.unclustered:,} sequenced isolate(s) carry no cluster.")
        if crossing:
            text += (f" {crossing} cluster(s) span more than one sector, which is "
                     "the pattern a One Health transmission question is asking "
                     "about -- though shared cluster membership shows relatedness, "
                     "not direction.")
        return text


def clusters(genomic: pd.DataFrame, *, exclude_failed_qc: bool = True
             ) -> ClusterReport:
    """Group sequenced isolates by their recorded cluster.

    ``cluster_id`` and ``cluster_method`` were stored by ingest and read by
    nothing. This is what turns "resistant isolates are accumulating here" into
    "these are the same clone", which are different findings with different
    responses.

    What this cannot say is which way anything moved. Cluster membership is
    symmetric: it shows that two isolates are closely related, not which came
    first. Direction needs dated sampling and a phylogeny, and nothing here
    should be read as evidence of it.
    """
    if genomic.empty:
        return ClusterReport(pd.DataFrame(), pd.DataFrame())

    working = genomic
    if exclude_failed_qc and "qc_verdict" in working.columns:
        working = working[working["qc_verdict"] != QC_FAIL]
    if working.empty:
        return ClusterReport(pd.DataFrame(), pd.DataFrame())

    has_cluster = working["cluster_id"].notna() & (
        working["cluster_id"].astype(str).str.strip() != "")
    assigned = working[has_cluster]
    unclustered = int((~has_cluster).sum())

    if assigned.empty:
        return ClusterReport(pd.DataFrame(), pd.DataFrame(),
                             unclustered=unclustered)

    rows: List[Dict[str, object]] = []
    for cluster_id, chunk in assigned.groupby("cluster_id"):
        collected = chunk["collection_datetime"].dropna()
        rows.append({
            "cluster_id": cluster_id,
            "method": "; ".join(sorted({str(m) for m in chunk["cluster_method"]
                                        if m and str(m).strip()})) or "unrecorded",
            "isolates": len(chunk),
            "organisms": chunk["organism"].nunique(),
            "organism": "; ".join(sorted({str(o) for o in chunk["organism"] if o})),
            "sectors": chunk["sector"].nunique(),
            "sector_mix": "; ".join(sorted({str(s) for s in chunk["sector"] if s})),
            "sequence_types": "; ".join(sorted({str(t) for t in chunk["sequence_type"]
                                                if t and str(t).strip()})),
            "labs": chunk["lab_name"].nunique(),
            "first_collected": collected.min() if not collected.empty else None,
            "last_collected": collected.max() if not collected.empty else None,
            "span_days": (int((collected.max() - collected.min()).days)
                          if len(collected) > 1 else 0),
        })

    table = (pd.DataFrame(rows)
             .sort_values(["isolates", "sectors"], ascending=False)
             .reset_index(drop=True))

    member_columns = [c for c in ("cluster_id", "isolate_id", "organism",
                                  "sequence_type", "sector", "specimen_type",
                                  "lab_name", "region", "collection_datetime",
                                  "qc_verdict")
                      if c in assigned.columns]
    members = assigned[member_columns].sort_values(
        ["cluster_id", "collection_datetime"])

    methods = sorted({str(m) for m in assigned["cluster_method"]
                      if m and str(m).strip()})
    return ClusterReport(table, members, methods, unclustered)


def sequencing_coverage(genomic: pd.DataFrame,
                        total_isolates: Optional[int] = None) -> Dict[str, object]:
    """How much of the collection has been sequenced, and how good it is.

    Sequencing coverage is the limit on every genomic statement the platform
    makes. A gene frequency drawn from 12 of 400 isolates is a statement about
    those twelve, and the proportion belongs beside it.
    """
    if genomic.empty:
        return {"sequenced": 0, "total_isolates": total_isolates or 0}

    verdicts = genomic["qc_verdict"].value_counts().to_dict() \
        if "qc_verdict" in genomic.columns else {}
    out: Dict[str, object] = {
        "sequenced": len(genomic),
        "total_isolates": total_isolates,
        "passed_qc": verdicts.get(QC_PASS, 0),
        "failed_qc": verdicts.get(QC_FAIL, 0),
        "not_assessable": verdicts.get(QC_UNKNOWN, 0),
        "typed": int(genomic["sequence_type"].notna().sum()),
        "clustered": int(genomic["cluster_id"].notna().sum()),
    }
    if total_isolates:
        out["percent_sequenced"] = round(100.0 * len(genomic) / total_isolates, 1)
    return out


__all__ = [
    "Determinant", "DETERMINANTS", "BY_GENE", "COVERED_AGENTS",
    "QualityThresholds", "DEFAULT_THRESHOLDS", "assess_quality",
    "QC_PASS", "QC_FAIL", "QC_UNKNOWN",
    "load_genomic_frame", "determinants_of",
    "concordance", "concordance_summary", "unexplained_resistance",
    "contradictions",
    "CONCORDANT_RESISTANT", "CONCORDANT_SUSCEPTIBLE", "GENOTYPE_ONLY",
    "PHENOTYPE_ONLY",
    "determinant_frequency", "determinants_not_in_rules",
    "NON_RESISTANCE_MARKERS", "non_resistance_markers_found",
    "ClusterReport", "clusters", "sequencing_coverage",
]
