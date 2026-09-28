"""
Expert rules: organism-agent combinations that must not be reported.

Why this exists
---------------
Running the new analytics over the platform's own data produced this row:

    Escherichia coli   Vancomycin   n=35   91.4% susceptible   CI 77.6-97.0

That is not a surprising finding, it is an impossible one. Vancomycin is a large
glycopeptide that cannot cross the Gram-negative outer membrane, so *E. coli* is
intrinsically resistant to it. A susceptibility percentage for that pair is
meaningless however carefully its confidence interval is computed, and a
dashboard that displays it teaches its users to distrust everything beside it.

The critical review asked for exactly this guard in two places: "Unknown or
unsupported combinations should remain unclassified rather than inherit a
default", and "test boundary cases and unsupported combinations".

Two distinct rules
------------------
**Intrinsic resistance.** The organism is resistant by its own biology. A
susceptible result is a laboratory or data-entry error, not a finding. These are
suppressed from reporting and raised as data-quality errors.

**Not reportable although active in vitro.** The agent may inhibit the organism
on a plate but is known to fail in the patient, so CLSI directs that it not be
reported as susceptible. The classic case is *Salmonella* and *Shigella* with
first- and second-generation cephalosporins and aminoglycosides. These are
suppressed from clinical reporting but are not data errors, and they remain
valid for surveillance of the genotype.

Status of this table
--------------------
This is an abridged, conservative transcription of well-established intrinsic
resistance from CLSI M100 (expected-resistance tables) and EUCAST's expert-rules
and intrinsic-resistance document. It covers the organisms and agents this
platform actually sees. It is deliberately incomplete: a rule is included only
where it is not in dispute.

It carries the same caveat the review attached to the breakpoint tables, and for
the same reason -- **it must be verified against the current authoritative
editions by the national reference laboratory before it is relied on for
anything clinical.** Its purpose here is to stop the platform publishing
impossible numbers, which it does whether or not the table is complete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

#: Finding severity.
SEVERITY_ERROR = "error"          # biologically impossible; a data problem
SEVERITY_SUPPRESS = "suppress"    # real in vitro, not to be reported clinically

# ---------------------------------------------------------------------------
# Organism groups
#
# Matched on the organism name as recorded. Patterns are deliberately loose,
# because laboratories write "E. coli", "Escherichia coli" and "E.coli", and a
# rule that only fires on one spelling protects nobody.
# ---------------------------------------------------------------------------

ORGANISM_GROUPS: Dict[str, Tuple[str, ...]] = {
    # Each group lists the full genus and the abbreviated forms laboratories
    # actually write. Without the abbreviations, "K. pneumoniae" matched no
    # group at all and every rule silently passed it -- so an impossible
    # combination on an abbreviated name went unreported. Abbreviations are
    # anchored on the species name, which disambiguates the shared initials
    # (S. aureus against S. pneumoniae, K. pneumoniae against S. pneumoniae,
    # E. coli against C. coli).
    "Enterobacterales": (
        r"escherichia", r"\be\.? ?coli\b",
        r"klebsiella", r"\bk\.? ?(pneumoniae|oxytoca|aerogenes)\b",
        r"enterobacter\b", r"\be\.? ?cloacae\b",
        r"serratia", r"\bs\.? ?marcescens\b",
        r"citrobacter", r"\bc\.? ?(freundii|koseri)\b",
        r"proteus", r"\bp\.? ?(mirabilis|vulgaris)\b",
        r"morganella", r"providencia",
        r"salmonella", r"\bs\.? ?(enterica|typhi|typhimurium)\b",
        r"shigella", r"hafnia", r"pantoea",
        r"raoultella", r"edwardsiella", r"yersinia",
        r"cronobacter",
    ),
    # Sub-groups of Enterobacterales that carry their own intrinsic resistance.
    # These exist so a rule can name exactly the genera it applies to. The
    # previous design wrote the rule against all Enterobacterales and listed
    # exceptions, and the exception list had to mirror every spelling in the
    # group -- so "K. pneumoniae" escaped the Klebsiella exception and colistin,
    # a last-resort agent against carbapenem-resistant Klebsiella, was flagged
    # impossible. Naming the genera positively removes that whole class of bug.
    "Klebsiella": (r"klebsiella",
                   r"\bk\.? ?(pneumoniae|oxytoca|aerogenes)\b"),
    "Proteae": (r"proteus", r"morganella", r"providencia",
                r"\bp\.? ?(mirabilis|vulgaris)\b",
                r"\bm\.? ?morganii\b", r"\bp\.? ?stuartii\b"),
    "Serratia": (r"serratia", r"\bs\.? ?marcescens\b"),
    "SalmonellaShigella": (r"salmonella", r"shigella",
                           r"\bs\.? ?(enterica|typhi|typhimurium)\b",
                           r"\bs\.? ?(flexneri|sonnei|dysenteriae)\b"),
    "Pseudomonas": (r"pseudomonas", r"\bp\.? ?aeruginosa\b"),
    "Acinetobacter": (r"acinetobacter", r"\ba\.? ?baumannii\b"),
    "Stenotrophomonas": (r"stenotrophomonas",
                         r"\bs\.? ?maltophilia\b"),
    "Burkholderia": (r"burkholderia", r"\bb\.? ?cepacia\b"),
    "Staphylococcus": (r"staphylococc", r"\bmrsa\b",
                       r"\bmssa\b",
                       r"\bs\.? ?(aureus|epidermidis|haemolyticus|saprophyticus)\b",
                       r"coagulase.?negative", r"\bcons\b"),
    "Enterococcus": (r"enterococc",
                     r"\be\.? ?(faecalis|faecium)\b", r"\bvre\b"),
    "Streptococcus": (r"streptococc", r"\bstrep\b",
                      r"pneumococc", r"viridans",
                      r"\bs\.? ?(pneumoniae|pyogenes|agalactiae)\b"),
    "Campylobacter": (r"campylobacter",
                      r"\bc\.? ?(jejuni|coli)\b"),
    "Haemophilus": (r"haemophilus", r"\bh\.? ?influenzae\b"),
    "Neisseria": (r"neisseria",
                  r"\bn\.? ?(gonorrhoeae|meningitidis)\b"),
    "Vibrio": (r"vibrio", r"\bv\.? ?cholerae\b"),
    "Listeria": (r"listeria", r"\bl\.? ?monocytogenes\b"),
    "Candida": (r"candida", r"\byeast\b",
                r"\bc\.? ?(albicans|glabrata|auris|tropicalis)\b"),
}


#: Convenience super-groups.
GRAM_NEGATIVE_GROUPS = ("Enterobacterales", "Pseudomonas", "Acinetobacter",
                        "Stenotrophomonas", "Burkholderia", "Campylobacter",
                        "Haemophilus", "Neisseria", "Vibrio")
GRAM_POSITIVE_GROUPS = ("Staphylococcus", "Enterococcus", "Streptococcus",
                        "Listeria")

# ---------------------------------------------------------------------------
# Agent groups
# ---------------------------------------------------------------------------

AGENT_GROUPS: Dict[str, Tuple[str, ...]] = {
    "glycopeptide": (r"vancomycin", r"teicoplanin", r"dalbavancin",
                     r"telavancin", r"oritavancin"),
    "oxazolidinone": (r"linezolid", r"tedizolid"),
    "lipopeptide": (r"daptomycin",),
    "lincosamide": (r"clindamycin", r"lincomycin"),
    "macrolide": (r"erythromycin", r"clarithromycin", r"azithromycin"),
    "fusidane": (r"fusidic",),
    "monobactam": (r"aztreonam",),
    "polymyxin": (r"colistin", r"polymyxin"),
    "quinolone_first_gen": (r"nalidixic",),
    "aminopenicillin": (r"^ampicillin", r"^amoxicillin(?!.*clav)"),
    "penicillin_g": (r"^penicillin", r"benzylpenicillin"),
    "antistaph_penicillin": (r"oxacillin", r"methicillin", r"cloxacillin",
                             r"flucloxacillin", r"nafcillin"),
    "cephalosporin_1": (r"cefazolin", r"cephalothin", r"cefalexin",
                        r"cephalexin", r"cefadroxil", r"cephradine"),
    "cephalosporin_2": (r"cefuroxime", r"cefoxitin", r"cefaclor", r"cefotetan",
                        r"cefamandole", r"cefprozil"),
    "cephalosporin_3": (r"ceftriaxone", r"cefotaxime", r"ceftazidime",
                        r"cefixime", r"cefpodoxime", r"ceftibuten"),
    "cephalosporin_all": (r"^cef", r"^ceph", r"ceftazidime", r"ceftriaxone"),
    "aminoglycoside": (r"gentamicin", r"amikacin", r"tobramycin", r"netilmicin",
                       r"streptomycin", r"kanamycin"),
    "carbapenem": (r"meropenem", r"imipenem", r"ertapenem", r"doripenem"),
    "ertapenem": (r"ertapenem",),
    "nitrofuran": (r"nitrofurantoin",),
    "tetracycline": (r"^tetracycline", r"doxycycline", r"minocycline"),
    "folate_inhibitor": (r"trimethoprim", r"sulfamethoxazole", r"co-?trimoxazole",
                         r"sulfonamide"),
    "chloramphenicol": (r"chloramphenicol",),
    "rifamycin": (r"rifampi", r"rifamycin"),
    "amoxicillin_clav": (r"amoxicillin.*clav", r"co-?amoxiclav"),
}


@dataclass(frozen=True)
class Rule:
    organism_group: str
    agent_group: str
    severity: str
    reason: str
    # There is deliberately no exception list. An earlier version let a rule name
    # a broad group and exclude genera by regex, and the exclusions had to mirror
    # every spelling the group matched -- so "K. pneumoniae" escaped the
    # Klebsiella exclusion and colistin was flagged impossible for the one
    # organism it is most needed against. Rules name the genera they apply to.


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

_GRAM_NEGATIVE_IMPOSSIBLE = (
    ("glycopeptide",
     "Glycopeptides cannot cross the Gram-negative outer membrane. A "
     "susceptible result is not possible and indicates a testing or data-entry "
     "error."),
    ("oxazolidinone",
     "Oxazolidinones have no useful Gram-negative activity; efflux renders them "
     "inactive."),
    ("lipopeptide",
     "Daptomycin requires a Gram-positive cell envelope to act."),
    ("fusidane",
     "Fusidic acid has no Gram-negative activity."),
)

_GRAM_POSITIVE_IMPOSSIBLE = (
    ("monobactam",
     "Aztreonam binds only Gram-negative PBP3 and has no Gram-positive "
     "activity."),
    ("polymyxin",
     "Polymyxins act on the Gram-negative outer-membrane lipopolysaccharide, "
     "which Gram-positive organisms do not have."),
    ("quinolone_first_gen",
     "Nalidixic acid has no clinically useful Gram-positive activity and is not "
     "a reportable agent for these organisms."),
)

RULES: Tuple[Rule, ...] = tuple(
    # Gram-negative organisms against Gram-positive-only agents.
    [Rule(group, agent, SEVERITY_ERROR, reason)
     for group in GRAM_NEGATIVE_GROUPS
     for agent, reason in _GRAM_NEGATIVE_IMPOSSIBLE]
    # Gram-positive organisms against Gram-negative-only agents.
    + [Rule(group, agent, SEVERITY_ERROR, reason)
       for group in GRAM_POSITIVE_GROUPS
       for agent, reason in _GRAM_POSITIVE_IMPOSSIBLE]
    + [
        # Lincosamides and macrolides against Enterobacterales.
        Rule("Enterobacterales", "lincosamide", SEVERITY_ERROR,
             "Enterobacterales are intrinsically resistant to lincosamides."),
        Rule("Pseudomonas", "lincosamide", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to lincosamides."),

        # Klebsiella and the aminopenicillins.
        Rule("Klebsiella", "aminopenicillin", SEVERITY_ERROR,
             "Klebsiella species produce a chromosomal penicillinase and are "
             "intrinsically resistant to ampicillin and amoxicillin."),

        # Pseudomonas: a long intrinsic list; the agents most often mis-entered.
        Rule("Pseudomonas", "aminopenicillin", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to "
             "aminopenicillins."),
        Rule("Pseudomonas", "amoxicillin_clav", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to "
             "amoxicillin-clavulanate."),
        Rule("Pseudomonas", "cephalosporin_1", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to first- and "
             "second-generation cephalosporins."),
        Rule("Pseudomonas", "cephalosporin_2", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to first- and "
             "second-generation cephalosporins."),
        Rule("Pseudomonas", "ertapenem", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to ertapenem."),
        Rule("Pseudomonas", "tetracycline", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to "
             "tetracyclines."),
        Rule("Pseudomonas", "folate_inhibitor", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to trimethoprim "
             "and trimethoprim-sulfamethoxazole."),
        Rule("Pseudomonas", "chloramphenicol", SEVERITY_ERROR,
             "Pseudomonas aeruginosa is intrinsically resistant to "
             "chloramphenicol."),

        # Acinetobacter.
        Rule("Acinetobacter", "aminopenicillin", SEVERITY_ERROR,
             "Acinetobacter species are intrinsically resistant to "
             "aminopenicillins."),
        Rule("Acinetobacter", "ertapenem", SEVERITY_ERROR,
             "Acinetobacter species are intrinsically resistant to ertapenem."),
        Rule("Acinetobacter", "monobactam", SEVERITY_ERROR,
             "Acinetobacter species are intrinsically resistant to aztreonam."),

        # Stenotrophomonas.
        Rule("Stenotrophomonas", "carbapenem", SEVERITY_ERROR,
             "Stenotrophomonas maltophilia carries an inducible "
             "metallo-beta-lactamase and is intrinsically resistant to "
             "carbapenems."),
        Rule("Stenotrophomonas", "aminoglycoside", SEVERITY_ERROR,
             "Stenotrophomonas maltophilia is intrinsically resistant to "
             "aminoglycosides."),

        # Enterococcus.
        Rule("Enterococcus", "cephalosporin_all", SEVERITY_ERROR,
             "Enterococci are intrinsically resistant to all cephalosporins; a "
             "susceptible result cannot be acted on."),
        Rule("Enterococcus", "folate_inhibitor", SEVERITY_SUPPRESS,
             "Enterococci appear susceptible to trimethoprim-sulfamethoxazole "
             "in vitro but the combination fails in vivo, because they use "
             "exogenous folate. CLSI directs that it not be reported."),
        Rule("Enterococcus", "lincosamide", SEVERITY_ERROR,
             "Enterococci are intrinsically resistant to lincosamides."),

        # Salmonella and Shigella: active in vitro, ineffective in the patient.
        Rule("SalmonellaShigella", "cephalosporin_1", SEVERITY_SUPPRESS,
             "First- and second-generation cephalosporins may appear active "
             "against Salmonella and Shigella in vitro but are not clinically "
             "effective; CLSI directs that they not be reported as susceptible."),
        Rule("SalmonellaShigella", "cephalosporin_2", SEVERITY_SUPPRESS,
             "First- and second-generation cephalosporins may appear active "
             "against Salmonella and Shigella in vitro but are not clinically "
             "effective; CLSI directs that they not be reported as susceptible."),
        Rule("SalmonellaShigella", "aminoglycoside", SEVERITY_SUPPRESS,
             "Aminoglycosides may appear active against Salmonella and Shigella "
             "in vitro but are not clinically effective for enteric fever or "
             "shigellosis; CLSI directs that they not be reported."),

        # Proteus, Morganella, Providencia and Serratia.
        Rule("Proteae", "nitrofuran", SEVERITY_ERROR,
             "Proteus, Morganella and Providencia are intrinsically resistant "
             "to nitrofurantoin."),
        Rule("Proteae", "polymyxin", SEVERITY_ERROR,
             "Proteus, Morganella and Providencia are intrinsically resistant "
             "to polymyxins."),
        Rule("Proteae", "tetracycline", SEVERITY_ERROR,
             "Proteus species are intrinsically resistant to tetracycline."),
        Rule("Serratia", "nitrofuran", SEVERITY_ERROR,
             "Serratia marcescens is intrinsically resistant to nitrofurantoin."),
        Rule("Serratia", "polymyxin", SEVERITY_ERROR,
             "Serratia marcescens is intrinsically resistant to polymyxins."),

        # Staphylococcus.
        Rule("Staphylococcus", "aminopenicillin", SEVERITY_SUPPRESS,
             "Ampicillin susceptibility in staphylococci is inferred from "
             "penicillin, and beta-lactamase production makes a direct "
             "susceptible result unreliable."),

        # Candida, in case a yeast reaches an AST sheet.
        Rule("Candida", "carbapenem", SEVERITY_ERROR,
             "Antibacterial agents have no antifungal activity."),
        Rule("Candida", "aminoglycoside", SEVERITY_ERROR,
             "Antibacterial agents have no antifungal activity."),
        Rule("Candida", "cephalosporin_all", SEVERITY_ERROR,
             "Antibacterial agents have no antifungal activity."),
        Rule("Candida", "glycopeptide", SEVERITY_ERROR,
             "Antibacterial agents have no antifungal activity."),
    ]
)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(re.search(p, lowered) for p in patterns)


def organism_groups(organism: str) -> Tuple[str, ...]:
    """Every group an organism name belongs to."""
    return tuple(group for group, patterns in ORGANISM_GROUPS.items()
                 if _matches_any(organism, patterns))


def agent_groups(antibiotic: str) -> Tuple[str, ...]:
    """Every group an agent name belongs to."""
    return tuple(group for group, patterns in AGENT_GROUPS.items()
                 if _matches_any(antibiotic, patterns))


@dataclass(frozen=True)
class Finding:
    organism: str
    antibiotic: str
    severity: str
    reason: str

    @property
    def is_error(self) -> bool:
        return self.severity == SEVERITY_ERROR


def check_combination(organism: str, antibiotic: str) -> Optional[Finding]:
    """Whether this organism-agent pair should be reported.

    Returns None when the pair is acceptable. An error finding means a
    susceptible result is biologically impossible; a suppress finding means the
    result is real but must not guide treatment.

    Errors are checked before suppressions, so the more serious verdict wins.
    """
    orgs = set(organism_groups(organism))
    if not orgs:
        return None
    agents = set(agent_groups(antibiotic))
    if not agents:
        return None

    for wanted_severity in (SEVERITY_ERROR, SEVERITY_SUPPRESS):
        for rule in RULES:
            if rule.severity != wanted_severity:
                continue
            if rule.organism_group not in orgs or rule.agent_group not in agents:
                continue
            return Finding(organism=organism, antibiotic=antibiotic,
                           severity=rule.severity, reason=rule.reason)
    return None


def screen_frame(frame: pd.DataFrame, *,
                 organism_col: str = "organism",
                 antibiotic_col: str = "antibiotic",
                 result_col: str = "result") -> pd.DataFrame:
    """Screen a surveillance frame for combinations that must not be reported.

    Returns one row per offending organism-agent pair with the number of
    observations behind it and how many were reported susceptible -- the latter
    being the count that proves the problem is real rather than theoretical.
    """
    if frame.empty:
        return pd.DataFrame(columns=["organism", "antibiotic", "severity",
                                     "observations", "reported_susceptible",
                                     "reason"])

    rows: List[Dict[str, object]] = []
    pairs = frame[[organism_col, antibiotic_col]].drop_duplicates()
    for _, pair in pairs.iterrows():
        organism, antibiotic = pair[organism_col], pair[antibiotic_col]
        finding = check_combination(str(organism), str(antibiotic))
        if finding is None:
            continue
        subset = frame[(frame[organism_col] == organism)
                       & (frame[antibiotic_col] == antibiotic)]
        susceptible = 0
        if result_col in subset.columns:
            susceptible = int((subset[result_col].astype(str).str.strip().str.upper()
                               == "S").sum())
        rows.append({
            "organism": organism, "antibiotic": antibiotic,
            "severity": finding.severity,
            "observations": int(len(subset)),
            "reported_susceptible": susceptible,
            "reason": finding.reason,
        })

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    order = {SEVERITY_ERROR: 0, SEVERITY_SUPPRESS: 1}
    table["_order"] = table["severity"].map(order).fillna(9)
    return (table.sort_values(["_order", "reported_susceptible", "observations"],
                              ascending=[True, False, False])
                 .drop(columns="_order")
                 .reset_index(drop=True))


def drop_unreportable(frame: pd.DataFrame, *,
                      organism_col: str = "organism",
                      antibiotic_col: str = "antibiotic",
                      severities: Sequence[str] = (SEVERITY_ERROR, SEVERITY_SUPPRESS),
                      ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Remove unreportable combinations. Returns (kept, findings).

    Used before building an antibiogram, so that an impossible pair cannot
    occupy a cell. The findings are returned rather than discarded, because the
    right response to them is to correct the source data, not to hide the rows.
    """
    findings = screen_frame(frame, organism_col=organism_col,
                            antibiotic_col=antibiotic_col)
    if findings.empty:
        return frame, findings

    excluded = findings[findings["severity"].isin(severities)]
    if excluded.empty:
        return frame, findings

    bad = set(zip(excluded["organism"], excluded["antibiotic"]))
    mask = pd.Series(
        [(o, a) not in bad for o, a in zip(frame[organism_col], frame[antibiotic_col])],
        index=frame.index)
    return frame[mask].copy(), findings


__all__ = [
    "SEVERITY_ERROR", "SEVERITY_SUPPRESS",
    "ORGANISM_GROUPS", "AGENT_GROUPS", "RULES",
    "Rule", "Finding",
    "organism_groups", "agent_groups", "check_combination",
    "screen_frame", "drop_unreportable",
]
