"""
Generate sequencing results for isolates already in the database.

Genomic data does not arrive on a mobile form. It comes out of a sequencing run
and a bioinformatics pipeline, as a table of gene calls, typing and quality
metrics, and that is what this writes: one ``genomic_results`` row per isolate
chosen for sequencing, keyed to isolates that already exist, so the genomic
layer attaches to the specimen chain rather than floating beside it.

**Every record produced here is invented.** It exists to exercise the analysis,
and its gene frequencies describe nothing real.

What makes the output useful rather than noise is that it is built *from the
stored phenotypes*. For each isolate the generator looks at what the laboratory
actually recorded, then assigns determinants that would explain those results.
Concordance analysis run over uniform random genes would find nothing, because
there would be nothing to find.

It then introduces, deliberately and in known quantity, the three situations the
analysis exists to surface:

  * resistance with no determinant assigned, which is what an undetected
    mechanism, an incomplete database or a gap in the assembly looks like;
  * a determinant that strongly predicts resistance on an isolate that tested
    susceptible, which is what a mislabelled isolate or a testing error looks
    like;
  * assemblies that fail quality, whose gene calls must not reach a frequency.

Clusters are assigned to isolates sharing an organism and sequence type, and a
few deliberately span sectors, since a cluster holding both a clinical and an
environmental isolate is the shape a One Health transmission question asks
about -- while saying nothing about direction.

Usage (from the project root):

    python scripts/generate_genomes.py                 # dry run
    python scripts/generate_genomes.py --yes
    python scripts/generate_genomes.py --yes --fraction 0.6
    python scripts/generate_genomes.py --delete        # remove generated genomes
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_SEED = 20261018

#: Marks every row this script writes, so --delete can find them again and no
#: generated genome is ever mistaken for a real sequencing result.
CREATED_BY = "synthetic-genome-generator"

#: Typing schemes and a few plausible sequence types per organism. The STs are
#: real designations for these species, used here only as labels.
MLST: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "Escherichia coli": ("ecoli", ("ST131", "ST10", "ST648", "ST410", "ST167")),
    "Klebsiella pneumoniae": ("kpneumoniae",
                              ("ST147", "ST307", "ST15", "ST101", "ST258")),
    "Pseudomonas aeruginosa": ("paeruginosa", ("ST235", "ST111", "ST244")),
    "Staphylococcus aureus": ("saureus", ("ST8", "ST5", "ST88", "ST152")),
    "Salmonella enterica": ("senterica", ("ST11", "ST19", "ST313")),
    "Acinetobacter baumannii": ("abaumannii", ("ST2", "ST1", "ST85")),
    "Enterococcus faecalis": ("efaecalis", ("ST6", "ST16")),
    "Proteus mirabilis": ("pmirabilis", ("ST135",)),
    "Shigella flexneri": ("ecoli", ("ST245",)),
    "Campylobacter jejuni": ("cjejuni", ("ST21", "ST45")),
    "Streptococcus pneumoniae": ("spneumoniae", ("ST156", "ST320")),
}

#: Determinants that occur without explaining anything on the tested panel --
#: real genomes carry plenty. They give the rule set something to ignore and
#: populate "determinants not in the rule set".
INCIDENTAL = ("aph(3'')-Ib", "aph(6)-Id", "mph(A)", "qacE", "floR",
              "tet(M)", "blaOXA-1", "sitABCD")

PLASMIDS = ("IncF", "IncFII", "IncI1", "IncX3", "IncN", "IncHI2", "ColpVC")
VIRULENCE = ("fimH", "iutA", "traT", "ompT", "hlyA", "papC", "ybtS")


def _pick_explaining(agent: str, rng: random.Random, strong_only: bool = False,
                     susceptible_to: Optional[set] = None):
    """A determinant that would account for resistance to this agent.

    ``susceptible_to`` is the set of agents this isolate tested susceptible to,
    and determinants that would strongly predict resistance to any of them are
    excluded. Without that filter the generator manufactured contradictions it
    never intended: picking blaNDM-1 to explain a ceftriaxone result also
    asserts meropenem and cefepime resistance, and if the laboratory recorded
    either as susceptible the isolate acquires a discrepancy that is an artefact
    of gene assignment rather than a designed one. It pushed the contradiction
    rate to ten per cent of pairs, which would read as a failing laboratory.

    Real isolates do carry broad determinants alongside susceptible results, but
    that is the rare case this generator injects on purpose, not the common one.
    """
    from src.genomics import DETERMINANTS
    options = [d for d in DETERMINANTS
               if agent in d.agents and (d.strong or not strong_only)]
    if susceptible_to:
        consistent = [d for d in options
                      if not (d.strong and set(d.agents) & susceptible_to)]
        if consistent:
            options = consistent
    return rng.choice(options) if options else None


def build_genomes(isolates: List[dict], phenotypes: Dict[str, List[dict]],
                  rng: random.Random, fraction: float) -> List[dict]:
    """One genomic record per sequenced isolate, built from its phenotypes."""
    from src.genomics import BY_GENE

    chosen = [i for i in isolates if rng.random() < fraction]
    genomes: List[dict] = []
    stats = {"unexplained": 0, "contradiction": 0, "qc_fail": 0}

    for index, isolate in enumerate(chosen, 1):
        isolate_id = isolate["isolate_id"]
        organism = isolate.get("organism") or ""
        scheme, types = MLST.get(organism, ("unknown", ("ST0",)))
        results = phenotypes.get(isolate_id, [])

        genes: set = set()
        mutations: set = set()
        susceptible_to = {r.get("antibiotic") for r in results
                          if str(r.get("result") or "").upper() == "S"}

        for row in results:
            agent = row.get("antibiotic")
            verdict = str(row.get("result") or "").upper()
            if verdict not in ("R", "I", "NS"):
                continue
            # One resistant result in eight is left unexplained, which is what
            # efflux, porin loss or a gap in the database looks like.
            if rng.random() < 0.125:
                stats["unexplained"] += 1
                continue
            determinant = _pick_explaining(agent, rng,
                                           susceptible_to=susceptible_to)
            if determinant is None:
                stats["unexplained"] += 1
                continue
            (mutations if "_" in determinant.gene else genes).add(determinant.gene)

        # A determinant that strongly predicts resistance, on an isolate that
        # tested susceptible. Rare on purpose: these are the ones to re-check.
        susceptible = [r for r in results
                       if str(r.get("result") or "").upper() == "S"]
        if susceptible and rng.random() < 0.06:
            row = rng.choice(susceptible)
            determinant = _pick_explaining(row.get("antibiotic"), rng,
                                           strong_only=True)
            if determinant is not None:
                (mutations if "_" in determinant.gene
                 else genes).add(determinant.gene)
                stats["contradiction"] += 1

        genes.update(rng.sample(INCIDENTAL, rng.randint(0, 3)))

        # Quality. One assembly in twelve is poor enough that its absent genes
        # cannot be told from genes it simply failed to assemble.
        poor = rng.random() < 0.08
        if poor:
            stats["qc_fail"] += 1
            depth = round(rng.uniform(5, 25), 1)
            breadth = round(rng.uniform(55, 88), 1)
            contamination = round(rng.uniform(4, 18), 2)
            n50 = rng.randint(1200, 15000)
            contigs = rng.randint(520, 1800)
        else:
            depth = round(rng.uniform(45, 190), 1)
            breadth = round(rng.uniform(93, 99.8), 1)
            contamination = round(rng.uniform(0.0, 2.4), 2)
            n50 = rng.randint(35000, 410000)
            contigs = rng.randint(25, 230)

        run_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))
        # genomic_reviewed_has_reviewer: an accepted result must name its
        # reviewer. A sign-off nobody is attached to is not a sign-off.
        review_status = rng.choice(["Accepted", "Accepted", "Unreviewed", "In review"])
        reviewer = (rng.choice(["k.mensah", "a.owusu", "n.boateng"])
                    if review_status == "Accepted" else None)
        genomes.append({
            "genomic_id": f"SEQ-{index:05d}",
            "isolate_id": isolate_id,
            "dataset_id": isolate["dataset_id"],
            "organism": organism,
            "run_id": f"RUN-{run_date:%Y%m}-{rng.randint(1, 9):02d}",
            "total_reads": rng.randint(900_000, 6_500_000),
            "mean_depth": depth,
            "coverage_breadth": breadth,
            "contamination_pct": contamination,
            "n50": n50,
            "contig_count": contigs,
            "qc_status": "Fail" if poor else "Pass",
            "assembler": "SPAdes",
            "assembler_version": "3.15.5",
            "pipeline_name": "bactopia",
            "pipeline_version": "3.0.1",
            "amr_db_name": "ResFinder",
            "amr_db_version": "2026-03-14",
            "species_confirmed": organism,
            "mlst_scheme": scheme,
            "sequence_type": rng.choice(types),
            "amr_genes": sorted(genes),
            "amr_mutations": sorted(mutations),
            "plasmid_replicons": sorted(rng.sample(PLASMIDS, rng.randint(0, 3))),
            "virulence_genes": sorted(rng.sample(VIRULENCE, rng.randint(0, 4))),
            "analysis_date": run_date + timedelta(days=rng.randint(1, 20)),
            "review_status": review_status,
            "reviewed_by": reviewer,
        })

    _assign_clusters(genomes, isolates, rng)
    return genomes, stats


def _assign_clusters(genomes: List[dict], isolates: List[dict],
                     rng: random.Random) -> None:
    """Group genomes sharing an organism and sequence type.

    Clustering here is by shared type rather than by distance, which is what a
    platform receiving results from elsewhere would be given. It says the
    isolates are closely related; it does not say which came first.
    """
    sector_of = {i["isolate_id"]: (i.get("sector") or "") for i in isolates}
    buckets: Dict[Tuple[str, str], List[dict]] = {}
    for genome in genomes:
        buckets.setdefault((genome["organism"], genome["sequence_type"]),
                           []).append(genome)

    number = 0
    for (organism, st), members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        # Not every shared type is called a cluster: a real run leaves plenty
        # unassigned, and the page should have to report that.
        if rng.random() < 0.3:
            continue
        number += 1
        label = f"CL-{number:03d}"
        for genome in members:
            genome["cluster_id"] = label
            genome["cluster_method"] = "MLST + core-genome SNP (<=15 SNPs)"
        sectors = {sector_of.get(g["isolate_id"], "") for g in members}
        if len(sectors) > 1:
            pass          # a cluster spanning sectors; left as the data made it


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

GENOMIC_COLUMNS = (
    "dataset_id", "genomic_id", "isolate_id", "run_id",
    "total_reads", "mean_depth", "coverage_breadth", "contamination_pct",
    "n50", "contig_count", "qc_status",
    "assembler", "assembler_version", "pipeline_name", "pipeline_version",
    "amr_db_name", "amr_db_version", "species_confirmed",
    "mlst_scheme", "sequence_type",
    "amr_genes", "amr_mutations", "plasmid_replicons", "virulence_genes",
    "cluster_method", "cluster_id", "analysis_date", "review_status",
    "reviewed_by", "created_by",
)


def _load_chain(conn) -> Tuple[List[dict], Dict[str, List[dict]]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT i.dataset_id, i.isolate_id, i.organism, s.sector
        FROM isolates i
        JOIN specimens sp ON sp.dataset_id = i.dataset_id
                         AND sp.specimen_id = i.specimen_id
        JOIN subjects  s  ON s.dataset_id  = sp.dataset_id
                         AND s.subject_id  = sp.subject_id
        ORDER BY i.isolate_id
    """)
    isolates = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT isolate_id, antibiotic, result FROM phenotypes "
                "WHERE result IS NOT NULL")
    phenotypes: Dict[str, List[dict]] = {}
    for row in cur.fetchall():
        record = dict(row)
        phenotypes.setdefault(record["isolate_id"], []).append(record)
    cur.close()
    return isolates, phenotypes


def _store_runs(conn, genomes: List[dict]) -> int:
    """Create the sequencing runs the genomes belong to.

    genomic_run_fk requires it: a genome without a run has no instrument, no
    date and no operator behind it, which is most of what makes a sequencing
    result auditable.
    """
    import psycopg2.extras
    runs: Dict[Tuple[str, str], tuple] = {}
    for g in genomes:
        key = (g["dataset_id"], g["run_id"])
        if key in runs:
            continue
        runs[key] = (
            g["dataset_id"], g["run_id"], "Illumina", "NextSeq 2000",
            "Nextera XT", "paired-end 2x150", g["analysis_date"],
            "Noguchi Memorial Institute for Medical Research",
            "sequencing-core", CREATED_BY,
        )
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur.raw,
        "INSERT INTO sequencing_runs (dataset_id, run_id, platform, instrument, "
        "library_kit, read_type, run_date, lab_name, operator, created_by) "
        "VALUES %s ON CONFLICT (dataset_id, run_id) DO NOTHING",
        list(runs.values()), page_size=200)
    conn.commit()
    cur.close()
    return len(runs)


def _store(conn, genomes: List[dict]) -> int:
    import psycopg2.extras
    rows = [(
        g["dataset_id"], g["genomic_id"], g["isolate_id"], g["run_id"],
        g["total_reads"], g["mean_depth"], g["coverage_breadth"],
        g["contamination_pct"], g["n50"], g["contig_count"], g["qc_status"],
        g["assembler"], g["assembler_version"], g["pipeline_name"],
        g["pipeline_version"], g["amr_db_name"], g["amr_db_version"],
        g["species_confirmed"], g["mlst_scheme"], g["sequence_type"],
        json.dumps(g["amr_genes"]), json.dumps(g["amr_mutations"]),
        json.dumps(g["plasmid_replicons"]), json.dumps(g["virulence_genes"]),
        g.get("cluster_method"), g.get("cluster_id"),
        g["analysis_date"], g["review_status"], g.get("reviewed_by"), CREATED_BY,
    ) for g in genomes]
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur.raw,
        f"INSERT INTO genomic_results ({', '.join(GENOMIC_COLUMNS)}) VALUES %s "
        "ON CONFLICT (dataset_id, genomic_id) DO NOTHING",
        rows, page_size=200)
    conn.commit()
    cur.close()
    return len(rows)


def _write_workbook(genomes: List[dict], path: str) -> None:
    """Write the genomes as an upload file.

    This is the shape a sequencing centre's results have to arrive in: one row
    per sequenced isolate, with isolate_id naming an isolate the platform
    already holds. Lists go in separator-delimited rather than as JSON, because
    the people filling these in use a spreadsheet.
    """
    import pandas as pd
    from src.upload_schema import SHEETS

    contract = next(s for s in SHEETS if s.name == "genomics")
    order = [c.name for c in contract.columns]

    rows = []
    for g in genomes:
        row = dict(g)
        for column in ("amr_genes", "amr_mutations", "plasmid_replicons",
                       "virulence_genes"):
            row[column] = ";".join(row.get(column) or [])
        row["platform"] = "Illumina"
        row["instrument"] = "NextSeq 2000"
        row["run_date"] = row.get("analysis_date")
        rows.append({name: row.get(name) for name in order})

    frame = pd.DataFrame(rows, columns=order)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="genomics", index=False)
    print()
    print(f"wrote {path}")
    print(f"  {len(frame):,} row(s), {len(order)} column(s)")
    print("  required columns: " + ", ".join(
        c.name for c in contract.columns if getattr(c, "required", False)))
    print("  amr_genes, amr_mutations, plasmid_replicons and virulence_genes "
          "are semicolon-separated")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true",
                        help="write the genomes; without it, only a dry run")
    parser.add_argument("--fraction", type=float, default=0.65,
                        help="proportion of isolates sequenced (default 0.65)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--delete", action="store_true",
                        help="remove previously generated genomes and exit")
    parser.add_argument("--workbook",
                        help="write an upload file here instead of writing to "
                             "the database -- the format a sequencing centre's "
                             "results must arrive in")
    parser.add_argument("--import-workbook",
                        help="import a genomics upload file, matching rows to "
                             "isolates already in the database by isolate_id")
    args = parser.parse_args()

    from src import db
    conn = db.get_connection()
    try:
        if args.delete:
            cur = conn.cursor()
            cur.execute("DELETE FROM genomic_results WHERE created_by = %s",
                        (CREATED_BY,))
            conn.commit()
            print(f"removed generated genomes (created_by = {CREATED_BY})")
            return 0

        if args.import_workbook:
            import pandas as pd
            from src.ingest import import_genomic_results
            frame = pd.read_excel(args.import_workbook, sheet_name="genomics")
            print(f"read {len(frame):,} row(s) from {args.import_workbook}")
            result = import_genomic_results(frame, uploaded_by="genomics-import")
            print(f"  {result.ok}: {result.message}")
            if result.unmatched:
                print(f"  unmatched isolate ids: {result.unmatched[:10]}")
            if result.ambiguous:
                print(f"  ambiguous isolate ids: {result.ambiguous[:10]}")
            return 0 if result.ok else 1

        isolates, phenotypes = _load_chain(conn)
        print(f"isolates in the chain      : {len(isolates):,}")
        print(f"isolates with phenotypes   : {len(phenotypes):,}")
        if not isolates:
            print("Nothing to sequence. Load specimen data first.")
            return 1

        rng = random.Random(args.seed)
        genomes, stats = build_genomes(isolates, phenotypes, rng, args.fraction)
        clustered = sum(1 for g in genomes if g.get("cluster_id"))
        print(f"\ngenomes generated          : {len(genomes):,} "
              f"({100.0 * len(genomes) / len(isolates):.0f}% of isolates)")
        print(f"  assigned to a cluster    : {clustered:,}")
        print(f"  failing assembly quality : {stats['qc_fail']:,}")
        print(f"  resistance left unexplained : {stats['unexplained']:,} result(s)")
        print(f"  determinant vs susceptible  : {stats['contradiction']:,}")

        if args.workbook:
            _write_workbook(genomes, args.workbook)
            return 0

        if not args.yes:
            print("\nDry run. Nothing written. Re-run with --yes to store.")
            return 0

        runs = _store_runs(conn, genomes)
        print()
        print(f"stored {runs:,} sequencing run(s)")
        stored = _store(conn, genomes)
        print(f"\nstored {stored:,} genomic result(s)")
        print("Every record is invented and describes nothing real.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
