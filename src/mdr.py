"""
MDR, XDR and PDR classification.

What was wrong before
---------------------
``alerts.detect_mdr_organisms`` counted an isolate as multidrug-resistant when
it was resistant to three or more entries in one generic, hard-coded map of
antibiotic classes. The critical review flagged the generic map; running it
surfaces three further problems, each of which changes the answer:

* **The categories are organism-specific.** The internationally agreed
  definitions list a different set of antimicrobial categories for
  *Staphylococcus aureus*, *Enterococcus*, Enterobacterales, *Pseudomonas
  aeruginosa* and *Acinetobacter*. Applying one list to all of them counts
  categories that were never relevant to the organism and misses ones that were.

* **Intrinsic resistance was counted.** *Klebsiella* is resistant to ampicillin
  by its own biology, so scoring that as a point towards MDR inflates every
  Klebsiella isolate by one category. The agreed definitions are explicit that
  only *acquired* resistance counts.

* **Intermediate results were ignored.** The definitions use **non-susceptible**,
  which is intermediate *or* resistant. Counting only R understates resistance.

Definitions implemented
-----------------------
Following Magiorakos et al., *Multidrug-resistant, extensively drug-resistant
and pandrug-resistant bacteria: an international expert proposal for interim
standard definitions for acquired resistance*, Clinical Microbiology and
Infection 2012;18:268-281.

* **MDR** -- non-susceptible to at least one agent in three or more
  antimicrobial categories.
* **XDR** -- non-susceptible to at least one agent in all but two or fewer
  categories, that is, susceptible to only one or two categories.
* **PDR** -- non-susceptible to all agents in all categories.

A classification is only made where enough categories were actually tested. An
isolate tested against three agents cannot be shown not to be XDR, and reporting
it as "not XDR" would be a statement about the panel rather than the organism.
``tested_categories`` and ``coverage`` are returned so a caller can see how much
of the category set the laboratory examined.

Status of this table
--------------------
The category lists are transcribed from the published proposal and cover the
organisms this platform sees. Like the breakpoint and intrinsic-resistance
tables, they should be checked against the current source by the national
reference laboratory before the output is used in reporting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

from src import expert_rules

#: Classification outcomes.
CLASS_PDR = "PDR"
CLASS_XDR = "XDR"
CLASS_MDR = "MDR"
CLASS_NOT_MDR = "Not MDR"
CLASS_INSUFFICIENT = "Insufficient testing"

#: Non-susceptible is intermediate or resistant. 'NS' is reported by
#: laboratories that cannot separate the two.
NON_SUSCEPTIBLE = ("I", "R", "NS")
SUSCEPTIBLE = ("S",)

#: Minimum categories that must have been tested before MDR can be asserted.
MIN_CATEGORIES_FOR_MDR = 3


# ---------------------------------------------------------------------------
# Antimicrobial categories, per organism group
#
# Each entry maps a category name to the agent-name patterns that belong to it.
# Patterns are matched case-insensitively against the recorded antibiotic name.
# ---------------------------------------------------------------------------

_ENTEROBACTERALES_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Aminoglycosides": (r"gentamicin", r"tobramycin", r"amikacin", r"netilmicin"),
    "Antipseudomonal penicillins + BLI": (r"ticarcillin.*clav",
                                          r"piperacillin.*tazo"),
    "Carbapenems": (r"ertapenem", r"imipenem", r"meropenem", r"doripenem"),
    "Non-extended spectrum cephalosporins": (r"cefazolin", r"cefuroxime",
                                             r"cephalothin", r"cefalexin",
                                             r"cephalexin"),
    "Extended-spectrum cephalosporins": (r"cefotaxime", r"ceftriaxone",
                                         r"ceftazidime", r"cefepime",
                                         r"cefpodoxime", r"cefixime"),
    "Cephamycins": (r"cefoxitin", r"cefotetan"),
    "Fluoroquinolones": (r"ciprofloxacin", r"levofloxacin", r"moxifloxacin",
                         r"ofloxacin", r"norfloxacin"),
    "Folate pathway inhibitors": (r"trimethoprim", r"sulfamethoxazole",
                                  r"co-?trimoxazole"),
    "Glycylcyclines": (r"tigecycline",),
    "Monobactams": (r"aztreonam",),
    "Penicillins": (r"^ampicillin$", r"^amoxicillin$"),
    "Penicillins + BLI": (r"amoxicillin.*clav", r"ampicillin.*sulbactam",
                          r"co-?amoxiclav"),
    "Phenicols": (r"chloramphenicol",),
    "Phosphonic acids": (r"fosfomycin",),
    "Polymyxins": (r"colistin", r"polymyxin"),
    "Tetracyclines": (r"^tetracycline", r"doxycycline", r"minocycline"),
}

_STAPHYLOCOCCUS_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Aminoglycosides": (r"gentamicin", r"kanamycin", r"tobramycin"),
    "Ansamycins": (r"rifampi",),
    "Anti-MRSA cephalosporins": (r"ceftaroline", r"ceftobiprole"),
    "Anti-staphylococcal beta-lactams": (r"oxacillin", r"cefoxitin",
                                         r"methicillin", r"flucloxacillin",
                                         r"cloxacillin", r"nafcillin"),
    "Fluoroquinolones": (r"ciprofloxacin", r"levofloxacin", r"moxifloxacin",
                         r"ofloxacin"),
    "Folate pathway inhibitors": (r"trimethoprim", r"sulfamethoxazole",
                                  r"co-?trimoxazole"),
    "Fucidanes": (r"fusidic",),
    "Glycopeptides": (r"vancomycin", r"teicoplanin", r"telavancin"),
    "Glycylcyclines": (r"tigecycline",),
    "Lincosamides": (r"clindamycin",),
    "Lipopeptides": (r"daptomycin",),
    "Macrolides": (r"erythromycin", r"azithromycin", r"clarithromycin"),
    "Oxazolidinones": (r"linezolid", r"tedizolid"),
    "Phenicols": (r"chloramphenicol",),
    "Phosphonic acids": (r"fosfomycin",),
    "Streptogramins": (r"quinupristin", r"dalfopristin"),
    "Tetracyclines": (r"^tetracycline", r"doxycycline", r"minocycline"),
}

_ENTEROCOCCUS_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Aminoglycosides (high-level)": (r"gentamicin", r"streptomycin"),
    "Carbapenems": (r"imipenem", r"meropenem", r"doripenem"),
    "Fluoroquinolones": (r"ciprofloxacin", r"levofloxacin", r"moxifloxacin"),
    "Glycopeptides": (r"vancomycin", r"teicoplanin"),
    "Glycylcyclines": (r"tigecycline",),
    "Lipopeptides": (r"daptomycin",),
    "Oxazolidinones": (r"linezolid", r"tedizolid"),
    "Penicillins": (r"^ampicillin$", r"^amoxicillin$", r"^penicillin"),
    "Streptogramins": (r"quinupristin", r"dalfopristin"),
    "Tetracyclines": (r"^tetracycline", r"doxycycline", r"minocycline"),
}

_PSEUDOMONAS_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Aminoglycosides": (r"gentamicin", r"tobramycin", r"amikacin", r"netilmicin"),
    "Antipseudomonal carbapenems": (r"imipenem", r"meropenem", r"doripenem"),
    "Antipseudomonal cephalosporins": (r"ceftazidime", r"cefepime"),
    "Antipseudomonal fluoroquinolones": (r"ciprofloxacin", r"levofloxacin"),
    "Antipseudomonal penicillins + BLI": (r"ticarcillin.*clav",
                                          r"piperacillin.*tazo"),
    "Monobactams": (r"aztreonam",),
    "Phosphonic acids": (r"fosfomycin",),
    "Polymyxins": (r"colistin", r"polymyxin"),
}

_ACINETOBACTER_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Aminoglycosides": (r"gentamicin", r"tobramycin", r"amikacin", r"netilmicin"),
    "Antipseudomonal carbapenems": (r"imipenem", r"meropenem", r"doripenem"),
    "Antipseudomonal fluoroquinolones": (r"ciprofloxacin", r"levofloxacin"),
    "Antipseudomonal penicillins + BLI": (r"piperacillin.*tazo",
                                          r"ticarcillin.*clav"),
    "Extended-spectrum cephalosporins": (r"ceftazidime", r"cefotaxime",
                                         r"ceftriaxone", r"cefepime"),
    "Folate pathway inhibitors": (r"trimethoprim", r"sulfamethoxazole",
                                  r"co-?trimoxazole"),
    "Penicillins + BLI": (r"ampicillin.*sulbactam",),
    "Polymyxins": (r"colistin", r"polymyxin"),
    "Tetracyclines": (r"^tetracycline", r"doxycycline", r"minocycline"),
}

_STREPTOCOCCUS_PNEUMONIAE_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "Aminoglycosides": (r"gentamicin",),
    "Anti-pneumococcal fluoroquinolones": (r"levofloxacin", r"moxifloxacin"),
    "Carbapenems": (r"ertapenem", r"imipenem", r"meropenem"),
    "Cephalosporins (2nd gen)": (r"cefuroxime",),
    "Cephalosporins (3rd gen)": (r"cefotaxime", r"ceftriaxone"),
    "Folate pathway inhibitors": (r"trimethoprim", r"sulfamethoxazole",
                                  r"co-?trimoxazole"),
    "Glycopeptides": (r"vancomycin", r"teicoplanin"),
    "Glycylcyclines": (r"tigecycline",),
    "Lincosamides": (r"clindamycin",),
    "Macrolides": (r"erythromycin", r"azithromycin", r"clarithromycin"),
    "Oxazolidinones": (r"linezolid",),
    "Penicillins": (r"^penicillin", r"^ampicillin$", r"^amoxicillin$"),
    "Phenicols": (r"chloramphenicol",),
    "Streptogramins": (r"quinupristin", r"dalfopristin"),
    "Tetracyclines": (r"^tetracycline", r"doxycycline"),
}

#: Which category set applies to which organism group. The organism groups come
#: from ``expert_rules`` so one organism matcher serves both modules.
CATEGORY_SETS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "Enterobacterales": _ENTEROBACTERALES_CATEGORIES,
    "Staphylococcus": _STAPHYLOCOCCUS_CATEGORIES,
    "Enterococcus": _ENTEROCOCCUS_CATEGORIES,
    "Pseudomonas": _PSEUDOMONAS_CATEGORIES,
    "Acinetobacter": _ACINETOBACTER_CATEGORIES,
    "Streptococcus": _STREPTOCOCCUS_PNEUMONIAE_CATEGORIES,
}

#: Order matters where an organism matches more than one group: the most
#: specific set wins. Klebsiella matches both Enterobacterales and Klebsiella,
#: and Enterobacterales is the one with a published category list.
_SET_PRIORITY = ("Staphylococcus", "Enterococcus", "Pseudomonas",
                 "Acinetobacter", "Streptococcus", "Enterobacterales")


def category_set_for(organism: str) -> Tuple[Optional[str], Dict[str, Tuple[str, ...]]]:
    """Return (group name, category map) for an organism, or (None, {})."""
    groups = set(expert_rules.organism_groups(organism))
    for name in _SET_PRIORITY:
        if name in groups and name in CATEGORY_SETS:
            return name, CATEGORY_SETS[name]
    return None, {}


def categorise_agent(antibiotic: str,
                     categories: Dict[str, Tuple[str, ...]]) -> Optional[str]:
    """Which antimicrobial category an agent belongs to, for this organism."""
    name = (antibiotic or "").strip().lower()
    if not name:
        return None
    for category, patterns in categories.items():
        if any(re.search(p, name) for p in patterns):
            return category
    return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@dataclass
class MDRResult:
    """The classification of one isolate, with everything behind it."""

    isolate_id: str
    organism: str
    organism_group: Optional[str]
    classification: str
    categories_tested: Tuple[str, ...] = ()
    categories_non_susceptible: Tuple[str, ...] = ()
    categories_susceptible: Tuple[str, ...] = ()
    agents_excluded_intrinsic: Tuple[str, ...] = ()
    agents_uncategorised: Tuple[str, ...] = ()
    reason: str = ""

    @property
    def n_tested(self) -> int:
        return len(self.categories_tested)

    @property
    def n_non_susceptible(self) -> int:
        return len(self.categories_non_susceptible)

    @property
    def coverage(self) -> Optional[float]:
        """Share of the organism's category set that was tested."""
        if not self.organism_group:
            return None
        total = len(CATEGORY_SETS.get(self.organism_group, {}))
        return (100 * self.n_tested / total) if total else None

    def as_row(self) -> Dict[str, object]:
        return {
            "isolate_id": self.isolate_id,
            "organism": self.organism,
            "organism_group": self.organism_group or "not classified",
            "classification": self.classification,
            "categories_tested": self.n_tested,
            "categories_non_susceptible": self.n_non_susceptible,
            "non_susceptible_to": "; ".join(self.categories_non_susceptible),
            "still_susceptible_to": "; ".join(self.categories_susceptible),
            "coverage_percent": self.coverage,
            "intrinsic_excluded": "; ".join(self.agents_excluded_intrinsic),
            "reason": self.reason,
        }


def classify_isolate(organism: str,
                     results: Iterable[Tuple[str, str]],
                     *, isolate_id: str = "") -> MDRResult:
    """Classify one isolate from its (antibiotic, result) pairs.

    Intrinsic resistance is removed before counting, because the agreed
    definitions cover acquired resistance only. Without that step every
    *Klebsiella* gains a category for the ampicillin it was always resistant to,
    and every *Pseudomonas* gains several.
    """
    group, categories = category_set_for(organism)
    if not group:
        return MDRResult(
            isolate_id=isolate_id, organism=organism, organism_group=None,
            classification=CLASS_INSUFFICIENT,
            reason="No published antimicrobial category list for this organism, "
                   "so multidrug resistance cannot be defined for it here.")

    tested: Dict[str, Set[str]] = {}
    intrinsic: List[str] = []
    uncategorised: List[str] = []

    for antibiotic, result in results:
        value = str(result or "").strip().upper()
        if value not in NON_SUSCEPTIBLE and value not in SUSCEPTIBLE:
            continue

        # Acquired resistance only.
        finding = expert_rules.check_combination(organism, str(antibiotic))
        if finding is not None and finding.is_error:
            intrinsic.append(str(antibiotic))
            continue

        category = categorise_agent(str(antibiotic), categories)
        if category is None:
            uncategorised.append(str(antibiotic))
            continue
        tested.setdefault(category, set()).add(value)

    if not tested:
        return MDRResult(
            isolate_id=isolate_id, organism=organism, organism_group=group,
            classification=CLASS_INSUFFICIENT,
            agents_excluded_intrinsic=tuple(sorted(set(intrinsic))),
            agents_uncategorised=tuple(sorted(set(uncategorised))),
            reason="No agent tested falls into a defined antimicrobial category "
                   "for this organism.")

    non_susceptible = {c for c, values in tested.items()
                       if values & set(NON_SUSCEPTIBLE)}
    susceptible_only = {c for c in tested if c not in non_susceptible}
    total_categories = len(CATEGORY_SETS[group])

    # PDR: non-susceptible to every agent in every category. Only assertable
    # when the whole category set was tested.
    if (len(tested) == total_categories
            and len(non_susceptible) == total_categories
            and all(not (values & set(SUSCEPTIBLE)) for values in tested.values())):
        classification = CLASS_PDR
        reason = (f"Non-susceptible to every agent tested in all "
                  f"{total_categories} categories.")
    elif len(tested) >= total_categories - 2 and len(susceptible_only) <= 2 \
            and len(non_susceptible) >= 3:
        classification = CLASS_XDR
        reason = (f"Non-susceptible in {len(non_susceptible)} of "
                  f"{len(tested)} categories tested, remaining susceptible to "
                  f"{len(susceptible_only)} "
                  f"({', '.join(sorted(susceptible_only)) or 'none'}).")
    elif len(non_susceptible) >= 3:
        classification = CLASS_MDR
        reason = (f"Non-susceptible to at least one agent in "
                  f"{len(non_susceptible)} categories "
                  f"({', '.join(sorted(non_susceptible))}).")
    elif len(tested) < MIN_CATEGORIES_FOR_MDR:
        classification = CLASS_INSUFFICIENT
        reason = (f"Only {len(tested)} antimicrobial category/categories were "
                  f"tested; at least {MIN_CATEGORIES_FOR_MDR} are needed before "
                  "multidrug resistance can be ruled in or out.")
    else:
        classification = CLASS_NOT_MDR
        reason = (f"Non-susceptible in {len(non_susceptible)} of "
                  f"{len(tested)} categories tested, below the three required.")

    return MDRResult(
        isolate_id=isolate_id, organism=organism, organism_group=group,
        classification=classification,
        categories_tested=tuple(sorted(tested)),
        categories_non_susceptible=tuple(sorted(non_susceptible)),
        categories_susceptible=tuple(sorted(susceptible_only)),
        agents_excluded_intrinsic=tuple(sorted(set(intrinsic))),
        agents_uncategorised=tuple(sorted(set(uncategorised))),
        reason=reason,
    )


def classify_frame(frame: pd.DataFrame, *,
                   isolate_col: str = "isolate_id",
                   organism_col: str = "organism",
                   antibiotic_col: str = "antibiotic",
                   result_col: str = "result") -> pd.DataFrame:
    """Classify every isolate in a surveillance frame."""
    if frame.empty:
        return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    for isolate_id, group in frame.groupby(isolate_col, dropna=True):
        organism = str(group[organism_col].dropna().iloc[0]) \
            if group[organism_col].notna().any() else ""
        pairs = list(zip(group[antibiotic_col], group[result_col]))
        rows.append(classify_isolate(organism, pairs,
                                     isolate_id=str(isolate_id)).as_row())
    return pd.DataFrame(rows)


def summarise(classified: pd.DataFrame) -> Dict[str, object]:
    """Counts by classification, with the denominator stated.

    ``percent_of_classifiable`` deliberately excludes isolates whose panel was
    too narrow to classify. Including them in the denominator would let a
    laboratory reduce its apparent MDR rate by testing fewer agents.
    """
    if classified.empty:
        return {"isolates": 0, "classifiable": 0, "counts": {},
                "percent_of_classifiable": {}}

    counts = classified["classification"].value_counts().to_dict()
    classifiable = int(sum(v for k, v in counts.items()
                           if k != CLASS_INSUFFICIENT))
    percents = {k: (100 * v / classifiable if classifiable else None)
                for k, v in counts.items() if k != CLASS_INSUFFICIENT}
    return {
        "isolates": int(len(classified)),
        "classifiable": classifiable,
        "insufficient": int(counts.get(CLASS_INSUFFICIENT, 0)),
        "counts": {k: int(v) for k, v in counts.items()},
        "percent_of_classifiable": percents,
    }


__all__ = [
    "CLASS_PDR", "CLASS_XDR", "CLASS_MDR", "CLASS_NOT_MDR", "CLASS_INSUFFICIENT",
    "NON_SUSCEPTIBLE", "CATEGORY_SETS", "MDRResult",
    "category_set_for", "categorise_agent",
    "classify_isolate", "classify_frame", "summarise",
]
