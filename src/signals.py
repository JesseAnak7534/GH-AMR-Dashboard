"""
Surveillance signals and the response lifecycle.

What the review asked for
-------------------------
    "an alert needs an explicit denominator, deduplicated surveillance unit,
    minimum-data rule, baseline, source population, and a clear explanation of
    why it fired. Generic thresholds should not be mistaken for outbreak
    definitions or action thresholds approved by Ghanaian public-health
    authorities."

    "Create an operational alert lifecycle: machine signal -> laboratory
    verification -> epidemiologist/clinician review -> assigned response owner ->
    action and due date -> resolution/evidence -> closure. Record timestamps so
    programme managers can see time from specimen collection to confirmed
    result, alert review, notification and response. Keep the generating
    dataset, rule version, affected observations and reviewer attached to each
    event."

What was there before
---------------------
``alerts.check_resistance_thresholds`` grouped the flat AST table by organism
and agent, counted rows, and raised an alert at fixed cut-offs of 20, 40, 60 and
80 per cent with a minimum of ten rows. Four problems, each of which changes
whether a signal fires:

* the denominator was susceptibility tests, not isolates, so an organism tested
  against a longer panel crossed the minimum sooner;
* there was no deduplication, so one repeatedly cultured patient could raise a
  national signal on their own;
* there was no baseline, so a stable endemic rate fired every time the page
  loaded, which is how a system comes to show 111 high-priority alerts that
  nobody reads;
* nothing recorded why a signal fired, so a reviewer could not judge it without
  re-deriving it.

Every signal here carries its rule and version, its numerator and denominator
with the denominator defined in words, its surveillance unit, its baseline, the
isolates behind it, and a plain-language explanation. Thresholds are defaults
for review, not approved action thresholds, and each signal says so.

Nothing in this module notifies anyone. The review asks that sensitivity and
false-alarm burden be piloted against historical data before any automatic
notification or escalation, so signals are recorded for review and that is all.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import psycopg2.extras
import pandas as pd

from src import db, expert_rules, mdr
from src import surveillance as sv

logger = logging.getLogger(__name__)

#: Bumped whenever a rule's logic or threshold changes, so a signal recorded
#: last month can be told apart from one the current rules would raise.
RULESET_VERSION = "2026.09.1"

SEVERITY_INFO = "info"
SEVERITY_MODERATE = "moderate"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"
SEVERITIES = (SEVERITY_INFO, SEVERITY_MODERATE, SEVERITY_HIGH, SEVERITY_CRITICAL)

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

STATUS_DETECTED = "detected"
STATUS_LAB_VERIFICATION = "lab_verification"
STATUS_UNDER_REVIEW = "under_review"
STATUS_ASSIGNED = "assigned"
STATUS_ACTIONED = "actioned"
STATUS_RESOLVED = "resolved"
STATUS_CLOSED = "closed"
STATUS_DISMISSED = "dismissed"

STATUSES = (STATUS_DETECTED, STATUS_LAB_VERIFICATION, STATUS_UNDER_REVIEW,
            STATUS_ASSIGNED, STATUS_ACTIONED, STATUS_RESOLVED, STATUS_CLOSED,
            STATUS_DISMISSED)

#: The path a signal may take. A signal can be dismissed from any open state --
#: a machine signal that a laboratory disproves should not have to be carried
#: through review to be closed -- but it cannot skip from detection to resolved
#: without someone having looked at it.
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    STATUS_DETECTED: (STATUS_LAB_VERIFICATION, STATUS_UNDER_REVIEW, STATUS_DISMISSED),
    STATUS_LAB_VERIFICATION: (STATUS_UNDER_REVIEW, STATUS_DISMISSED),
    STATUS_UNDER_REVIEW: (STATUS_ASSIGNED, STATUS_DISMISSED),
    STATUS_ASSIGNED: (STATUS_ACTIONED, STATUS_DISMISSED),
    STATUS_ACTIONED: (STATUS_RESOLVED, STATUS_DISMISSED),
    STATUS_RESOLVED: (STATUS_CLOSED,),
    STATUS_CLOSED: (),
    STATUS_DISMISSED: (),
}

STATUS_LABELS: Dict[str, str] = {
    STATUS_DETECTED: "Detected by rule",
    STATUS_LAB_VERIFICATION: "With the laboratory for verification",
    STATUS_UNDER_REVIEW: "Under epidemiological or clinical review",
    STATUS_ASSIGNED: "Assigned to a response owner",
    STATUS_ACTIONED: "Action taken",
    STATUS_RESOLVED: "Resolved with evidence",
    STATUS_CLOSED: "Closed",
    STATUS_DISMISSED: "Dismissed",
}

OPEN_STATUSES = (STATUS_DETECTED, STATUS_LAB_VERIFICATION, STATUS_UNDER_REVIEW,
                 STATUS_ASSIGNED, STATUS_ACTIONED)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SignalRule:
    """A detection rule, described in the terms the review demanded."""

    rule_id: str
    name: str
    description: str
    surveillance_unit: str
    denominator_definition: str
    minimum_data: str
    baseline_definition: str
    default_threshold: Optional[float]
    severity_basis: str
    governance: str = (
        "A default threshold for review. It is not an outbreak definition and "
        "has not been approved as an action threshold by any national "
        "public-health authority.")

    def as_row(self) -> Dict[str, str]:
        return {
            "Rule": self.name,
            "Identifier": self.rule_id,
            "What it looks for": self.description,
            "Surveillance unit": self.surveillance_unit,
            "Denominator": self.denominator_definition,
            "Minimum data": self.minimum_data,
            "Baseline": self.baseline_definition,
            "Default threshold": ("—" if self.default_threshold is None
                                  else str(self.default_threshold)),
            "Severity from": self.severity_basis,
            "Governance": self.governance,
        }


RULES: Dict[str, SignalRule] = {
    "resistance-above-baseline": SignalRule(
        rule_id="resistance-above-baseline",
        name="Resistance above its own baseline",
        description=(
            "Non-susceptibility for one organism and agent in the recent window "
            "is materially higher than in the preceding baseline period for the "
            "same organism, agent and sector."),
        surveillance_unit=(
            "Isolates, deduplicated to the first isolate of each organism per "
            "subject per period (CLSI M39)"),
        denominator_definition=(
            "Isolates of that organism with an interpreted result for that "
            "agent, in the recent window, in one sector"),
        minimum_data=(
            f"At least {sv.MIN_ISOLATES_FOR_REPORTING} isolates in the recent "
            "window and the same in the baseline"),
        baseline_definition=(
            "The same organism, agent and sector over the period immediately "
            "before the window, of equal length"),
        default_threshold=15.0,
        severity_basis=(
            "Size of the increase in percentage points, and whether the "
            "confidence intervals of the two periods overlap"),
    ),
    "critical-resistance": SignalRule(
        rule_id="critical-resistance",
        name="Resistance to a last-line agent",
        description=(
            "Any isolate non-susceptible to a carbapenem, a polymyxin, "
            "linezolid or a glycopeptide where that agent is a last-line option "
            "for the organism."),
        surveillance_unit="Individual isolates",
        denominator_definition=(
            "Not a rate. Each qualifying isolate raises its own signal, because "
            "one carbapenem-resistant isolate warrants confirmation "
            "irrespective of how many were tested"),
        minimum_data="One isolate with a confirmed non-susceptible result",
        baseline_definition="None. This rule is not comparative",
        default_threshold=None,
        severity_basis="The agent involved and whether the isolate is XDR or PDR",
    ),
    "mdr-burden": SignalRule(
        rule_id="mdr-burden",
        name="Multidrug resistance above threshold",
        description=(
            "The share of classifiable isolates of one organism meeting the MDR "
            "definition exceeds the threshold."),
        surveillance_unit="Isolates, deduplicated, classifiable for MDR",
        denominator_definition=(
            "Isolates of that organism tested against at least three "
            "antimicrobial categories. Isolates whose panel was too narrow are "
            "excluded from both numerator and denominator, so a laboratory "
            "cannot lower its rate by testing fewer agents"),
        minimum_data=f"At least {sv.MIN_ISOLATES_FOR_REPORTING} classifiable isolates",
        baseline_definition=(
            "None in this version. The rule reports a level, not a change"),
        default_threshold=30.0,
        severity_basis="Distance above the threshold",
    ),
    "emerging-resistance": SignalRule(
        rule_id="emerging-resistance",
        name="Resistance not previously seen",
        description=(
            "A non-susceptible result for an organism and agent that had none "
            "in the baseline period, where the baseline had enough isolates for "
            "its absence to be meaningful."),
        surveillance_unit="Isolates, deduplicated",
        denominator_definition=(
            "Isolates of that organism and agent in the recent window"),
        minimum_data=(
            "At least 10 isolates tested in the baseline with no "
            "non-susceptible result, and at least one in the window"),
        baseline_definition=(
            "The same organism, agent and sector in the period before the "
            "window"),
        default_threshold=None,
        severity_basis="Whether the agent is last-line",
    ),
    "implausible-result": SignalRule(
        rule_id="implausible-result",
        name="Biologically implausible result",
        description=(
            "Susceptibility recorded for an organism and agent where the "
            "organism is intrinsically resistant. A data-quality signal, not an "
            "epidemiological one."),
        surveillance_unit="Susceptibility results",
        denominator_definition="All results for that organism and agent",
        minimum_data="One result",
        baseline_definition="None. The combination is impossible at any rate",
        default_threshold=None,
        severity_basis="Fixed at high; the result cannot be correct",
    ),
}

#: Agents whose loss matters most. Used by the critical and emerging rules.
LAST_LINE_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "Carbapenem": (r"meropenem", r"imipenem", r"ertapenem", r"doripenem"),
    "Polymyxin": (r"colistin", r"polymyxin"),
    "Glycopeptide": (r"vancomycin", r"teicoplanin"),
    "Oxazolidinone": (r"linezolid", r"tedizolid"),
    "Lipopeptide": (r"daptomycin",),
    "Glycylcycline": (r"tigecycline",),
}


def last_line_class(antibiotic: str) -> Optional[str]:
    import re
    name = (antibiotic or "").strip().lower()
    for label, patterns in LAST_LINE_PATTERNS.items():
        if any(re.search(p, name) for p in patterns):
            return label
    return None


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """One detected signal, carrying everything a reviewer needs."""

    rule_id: str
    title: str
    explanation: str
    severity: str
    dataset_id: Optional[str] = None
    sector: Optional[str] = None
    organism: Optional[str] = None
    antibiotic: Optional[str] = None
    region: Optional[str] = None
    lab_name: Optional[str] = None
    numerator: Optional[float] = None
    denominator: Optional[float] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    baseline_value: Optional[float] = None
    affected_isolates: Tuple[str, ...] = ()
    first_specimen_date: Optional[date] = None
    last_specimen_date: Optional[date] = None
    rule_version: str = RULESET_VERSION

    @property
    def rule(self) -> SignalRule:
        return RULES[self.rule_id]

    @property
    def signal_key(self) -> str:
        """Deterministic fingerprint.

        Re-running detection over the same data must update the existing signal
        rather than raise a duplicate, or a reviewer's work is lost every time
        the page reloads.
        """
        parts = [self.rule_id, self.rule_version, str(self.dataset_id),
                 str(self.sector), str(self.organism), str(self.antibiotic),
                 str(self.region), str(self.lab_name),
                 str(self.last_specimen_date)]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_signal_schema(cur) -> None:
    """Create the signal and action tables. Safe to call on every startup."""
    severities = ", ".join(f"'{s}'" for s in SEVERITIES)
    statuses = ", ".join(f"'{s}'" for s in STATUSES)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id BIGSERIAL PRIMARY KEY,
            signal_key TEXT NOT NULL UNIQUE,
            dataset_id TEXT,
            rule_id TEXT NOT NULL,
            rule_version TEXT NOT NULL,
            sector TEXT,
            organism TEXT,
            antibiotic TEXT,
            region TEXT,
            lab_name TEXT,
            title TEXT NOT NULL,
            explanation TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ({severities})),

            -- The numbers behind the signal, and what they mean.
            numerator DOUBLE PRECISION,
            denominator DOUBLE PRECISION,
            value DOUBLE PRECISION,
            threshold DOUBLE PRECISION,
            baseline_value DOUBLE PRECISION,
            surveillance_unit TEXT NOT NULL,
            denominator_definition TEXT NOT NULL,
            baseline_definition TEXT,
            minimum_data TEXT,

            affected_isolates JSONB,
            first_specimen_date DATE,
            last_specimen_date DATE,

            status TEXT NOT NULL DEFAULT '{STATUS_DETECTED}'
                CHECK (status IN ({statuses})),
            assigned_to TEXT,
            due_date DATE,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status_changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Append-only. A signal's history is the evidence that it was handled, so
    # transitions are added, never rewritten.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS signal_actions (
            action_id BIGSERIAL PRIMARY KEY,
            signal_id BIGINT NOT NULL
                REFERENCES signals (signal_id) ON DELETE CASCADE,
            from_status TEXT CHECK (from_status IS NULL
                                    OR from_status IN ({statuses})),
            to_status TEXT NOT NULL CHECK (to_status IN ({statuses})),
            actor TEXT NOT NULL,
            actor_role TEXT,
            note TEXT,
            evidence TEXT,
            assigned_to TEXT,
            due_date DATE,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_signals_status ON signals (status)",
        "CREATE INDEX IF NOT EXISTS idx_signals_rule ON signals (rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_signals_dataset ON signals (dataset_id)",
        "CREATE INDEX IF NOT EXISTS idx_signal_actions_signal "
        "ON signal_actions (signal_id, occurred_at)",
    ):
        cur.execute(statement)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _interpreted(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "result" not in frame.columns:
        return frame.iloc[0:0]
    mask = frame["result"].astype(str).str.strip().str.upper().isin(
        sv.INTERPRETED_RESULTS)
    return frame[mask]


def _non_susceptible_rate(group: pd.DataFrame) -> Tuple[int, int, Optional[float]]:
    isolates = group.drop_duplicates(subset=["dataset_id", "isolate_id"])
    total = len(isolates)
    if not total:
        return 0, 0, None
    values = isolates["result"].astype(str).str.strip().str.upper()
    ns = int(values.isin(["I", "R", "NS"]).sum())
    return ns, total, 100 * ns / total


def _split_periods(frame: pd.DataFrame, window_days: int
                   ) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[date], Optional[date]]:
    """Recent window and the equal-length baseline before it."""
    collected = frame["collection_datetime"].dropna()
    if collected.empty:
        return frame.iloc[0:0], frame.iloc[0:0], None, None
    latest = collected.max()
    window_start = latest - pd.Timedelta(days=window_days)
    baseline_start = window_start - pd.Timedelta(days=window_days)

    recent = frame[frame["collection_datetime"] > window_start]
    baseline = frame[(frame["collection_datetime"] > baseline_start)
                     & (frame["collection_datetime"] <= window_start)]
    return recent, baseline, window_start.date(), latest.date()


def detect_resistance_above_baseline(frame: pd.DataFrame, *,
                                     window_days: int = 90,
                                     threshold: float = 15.0,
                                     dataset_id: Optional[str] = None
                                     ) -> List[Signal]:
    """Non-susceptibility materially above the preceding period.

    Comparative rather than absolute. A stable endemic 70% does not fire every
    time the page loads; a move from 40% to 60% does.
    """
    rule = RULES["resistance-above-baseline"]
    signals: List[Signal] = []
    if frame.empty:
        return signals

    deduplicated, _ = sv.select_first_isolates(_interpreted(frame))
    if deduplicated.empty:
        return signals

    recent, baseline, _, latest = _split_periods(deduplicated, window_days)
    if recent.empty or baseline.empty:
        return signals

    for (sector, organism, antibiotic), current in recent.groupby(
            ["sector", "organism", "antibiotic"], dropna=False):
        prior = baseline[(baseline["sector"] == sector)
                         & (baseline["organism"] == organism)
                         & (baseline["antibiotic"] == antibiotic)]
        ns_now, n_now, rate_now = _non_susceptible_rate(current)
        ns_before, n_before, rate_before = _non_susceptible_rate(prior)

        if (n_now < sv.MIN_ISOLATES_FOR_REPORTING
                or n_before < sv.MIN_ISOLATES_FOR_REPORTING):
            continue
        if rate_now is None or rate_before is None:
            continue

        change = rate_now - rate_before
        if change < threshold:
            continue

        low_now, _ = sv.wilson_interval(ns_now, n_now)
        _, high_before = sv.wilson_interval(ns_before, n_before)
        intervals_separate = (low_now is not None and high_before is not None
                              and low_now > high_before)

        severity = SEVERITY_HIGH if intervals_separate and change >= 25 else (
            SEVERITY_MODERATE if intervals_separate else SEVERITY_INFO)

        explanation = (
            f"Non-susceptibility of {organism} to {antibiotic} in the {sector} "
            f"sector rose from {rate_before:.1f}% ({ns_before}/{n_before} "
            f"isolates) in the preceding {window_days} days to {rate_now:.1f}% "
            f"({ns_now}/{n_now}) in the most recent {window_days} days, an "
            f"increase of {change:.1f} percentage points. "
            + ("The 95% confidence intervals of the two periods do not overlap, "
               "so the change is unlikely to be sampling variation alone."
               if intervals_separate else
               "The confidence intervals of the two periods overlap, so this "
               "may be sampling variation; it is raised for review rather than "
               "as an established increase.")
        )

        signals.append(Signal(
            rule_id=rule.rule_id, title=(
                f"{organism} — {antibiotic}: non-susceptibility up "
                f"{change:.0f} points"),
            explanation=explanation, severity=severity, dataset_id=dataset_id,
            sector=str(sector) if sector else None,
            organism=str(organism), antibiotic=str(antibiotic),
            numerator=ns_now, denominator=n_now, value=rate_now,
            threshold=threshold, baseline_value=rate_before,
            affected_isolates=tuple(sorted(set(
                current["isolate_id"].dropna().astype(str)))[:200]),
            first_specimen_date=(current["collection_datetime"].min().date()
                                 if current["collection_datetime"].notna().any() else None),
            last_specimen_date=latest,
        ))
    return signals


def detect_critical_resistance(frame: pd.DataFrame, *,
                               dataset_id: Optional[str] = None) -> List[Signal]:
    """Non-susceptibility to a last-line agent.

    Grouped by organism, agent and laboratory rather than raised per isolate.
    Per-isolate signals are clinically defensible -- each carbapenem-resistant
    isolate does warrant confirmation -- but they produce a queue nobody can
    work: this data yields 243 of them. The review's warning about false-alarm
    burden applies to volume as much as to accuracy, so the signal names the
    cluster and carries every affected isolate for follow-up.
    """
    rule = RULES["critical-resistance"]
    signals: List[Signal] = []
    if frame.empty:
        return signals

    working = _interpreted(frame)
    if working.empty:
        return signals

    values = working["result"].astype(str).str.strip().str.upper()
    non_susceptible = working[values.isin(["I", "R", "NS"])].copy()
    if non_susceptible.empty:
        return signals

    # Only agents that are genuinely last-line for that organism.
    keep = []
    for _, row in non_susceptible.iterrows():
        agent_class = last_line_class(str(row.get("antibiotic")))
        if agent_class is None:
            keep.append(None)
            continue
        finding = expert_rules.check_combination(str(row.get("organism") or ""),
                                                 str(row.get("antibiotic")))
        keep.append(None if (finding is not None and finding.is_error)
                    else agent_class)
    non_susceptible["_agent_class"] = keep
    non_susceptible = non_susceptible[non_susceptible["_agent_class"].notna()]
    if non_susceptible.empty:
        return signals

    # XDR and PDR isolates raise the severity of the cluster they sit in.
    classified = mdr.classify_frame(working)
    severe_isolates: set = set()
    if not classified.empty:
        severe_isolates = set(
            classified.loc[classified["classification"].isin(
                [mdr.CLASS_PDR, mdr.CLASS_XDR]), "isolate_id"].astype(str))

    for (sector, organism, antibiotic, lab), group in non_susceptible.groupby(
            ["sector", "organism", "antibiotic", "lab_name"], dropna=False):
        isolates = sorted(set(group["isolate_id"].dropna().astype(str)))
        if not isolates:
            continue
        agent_class = str(group["_agent_class"].iloc[0])
        severe = sorted(set(isolates) & severe_isolates)
        severity = SEVERITY_CRITICAL if severe else SEVERITY_HIGH

        collected = group["collection_datetime"].dropna()
        first = collected.min().date() if not collected.empty else None
        last = collected.max().date() if not collected.empty else None

        signals.append(Signal(
            rule_id=rule.rule_id,
            title=(f"{organism}: {len(isolates)} isolate(s) non-susceptible to "
                   f"{antibiotic}"),
            explanation=(
                f"{len(isolates)} isolate(s) of {organism} were reported "
                f"non-susceptible to {antibiotic}, a {agent_class.lower()} and a "
                f"last-line option for this organism, at "
                f"{lab or 'an unrecorded laboratory'}"
                + (f" in the {sector} sector" if sector else "") + ". "
                + (f"{len(severe)} of them meet the XDR or PDR definition. "
                   if severe else "")
                + "Confirmation by the reference laboratory is the next step. "
                  "These are laboratory reports, not confirmed findings, and the "
                  "count is of isolates rather than patients."),
            severity=severity, dataset_id=dataset_id,
            sector=str(sector) if sector else None,
            organism=str(organism), antibiotic=str(antibiotic),
            region=(str(group["region"].dropna().iloc[0])
                    if group["region"].notna().any() else None),
            lab_name=str(lab) if lab else None,
            numerator=len(isolates), denominator=len(isolates),
            affected_isolates=tuple(isolates[:200]),
            first_specimen_date=first, last_specimen_date=last,
        ))
    return signals


def detect_mdr_burden(frame: pd.DataFrame, *, threshold: float = 30.0,
                      dataset_id: Optional[str] = None) -> List[Signal]:
    """Share of classifiable isolates meeting the MDR definition."""
    rule = RULES["mdr-burden"]
    signals: List[Signal] = []
    if frame.empty:
        return signals

    deduplicated, _ = sv.select_first_isolates(_interpreted(frame))
    if deduplicated.empty:
        return signals

    for (sector, organism), group in deduplicated.groupby(
            ["sector", "organism"], dropna=False):
        classified = mdr.classify_frame(group)
        if classified.empty:
            continue
        summary = mdr.summarise(classified)
        classifiable = summary["classifiable"]
        if classifiable < sv.MIN_ISOLATES_FOR_REPORTING:
            continue

        counts = summary["counts"]
        multidrug = (counts.get(mdr.CLASS_MDR, 0) + counts.get(mdr.CLASS_XDR, 0)
                     + counts.get(mdr.CLASS_PDR, 0))
        rate = 100 * multidrug / classifiable
        if rate < threshold:
            continue

        severity = (SEVERITY_CRITICAL if rate >= 70 else
                    SEVERITY_HIGH if rate >= 50 else SEVERITY_MODERATE)
        signals.append(Signal(
            rule_id=rule.rule_id,
            title=f"{organism}: {rate:.0f}% of classifiable isolates are MDR "
                  f"or worse",
            explanation=(
                f"{multidrug} of {classifiable} classifiable {organism} isolates "
                f"in the {sector} sector meet the MDR definition or worse "
                f"({counts.get(mdr.CLASS_XDR, 0)} XDR, "
                f"{counts.get(mdr.CLASS_PDR, 0)} PDR). "
                f"{summary['insufficient']} further isolate(s) were tested "
                "against too few antimicrobial categories to classify and are "
                "excluded from both numerator and denominator. Classification "
                "follows the international interim definitions and excludes "
                "intrinsic resistance."),
            severity=severity, dataset_id=dataset_id,
            sector=str(sector) if sector else None, organism=str(organism),
            numerator=multidrug, denominator=classifiable, value=rate,
            threshold=threshold,
            affected_isolates=tuple(sorted(
                classified.loc[classified["classification"].isin(
                    [mdr.CLASS_MDR, mdr.CLASS_XDR, mdr.CLASS_PDR]),
                    "isolate_id"].astype(str))[:200]),
            first_specimen_date=(group["collection_datetime"].min().date()
                                 if group["collection_datetime"].notna().any() else None),
            last_specimen_date=(group["collection_datetime"].max().date()
                                if group["collection_datetime"].notna().any() else None),
        ))
    return signals


def detect_implausible_results(frame: pd.DataFrame, *,
                               dataset_id: Optional[str] = None) -> List[Signal]:
    """Data-quality signals for impossible organism-agent combinations."""
    rule = RULES["implausible-result"]
    signals: List[Signal] = []
    if frame.empty:
        return signals

    findings = expert_rules.screen_frame(frame)
    if findings.empty:
        return signals

    errors = findings[(findings["severity"] == expert_rules.SEVERITY_ERROR)
                      & (findings["reported_susceptible"] > 0)]
    for _, row in errors.iterrows():
        organism, antibiotic = str(row["organism"]), str(row["antibiotic"])
        subset = frame[(frame["organism"] == organism)
                       & (frame["antibiotic"] == antibiotic)]
        signals.append(Signal(
            rule_id=rule.rule_id,
            title=f"{organism} recorded susceptible to {antibiotic}",
            explanation=(
                f"{int(row['reported_susceptible'])} of {int(row['observations'])} "
                f"results for {organism} against {antibiotic} record "
                f"susceptibility. {row['reason']} These results cannot be "
                "correct and indicate an identification, testing or data-entry "
                "problem. They are excluded from antibiograms, but the source "
                "records should be corrected."),
            severity=SEVERITY_HIGH, dataset_id=dataset_id,
            organism=organism, antibiotic=antibiotic,
            numerator=float(row["reported_susceptible"]),
            denominator=float(row["observations"]),
            affected_isolates=tuple(sorted(set(
                subset["isolate_id"].dropna().astype(str)))[:200]),
        ))
    return signals


DETECTORS = {
    "resistance-above-baseline": detect_resistance_above_baseline,
    "critical-resistance": detect_critical_resistance,
    "mdr-burden": detect_mdr_burden,
    "implausible-result": detect_implausible_results,
}


def detect_all(dataset_id: Optional[str] = None,
               rules: Optional[Sequence[str]] = None) -> List[Signal]:
    """Run every enabled rule over the surveillance view."""
    frame = sv.load_surveillance_frame(dataset_id=dataset_id)
    if frame.empty:
        return []

    wanted = tuple(rules) if rules else tuple(DETECTORS)
    signals: List[Signal] = []
    for rule_id in wanted:
        detector = DETECTORS.get(rule_id)
        if detector is None:
            continue
        try:
            signals.extend(detector(frame, dataset_id=dataset_id))
        except Exception:                             # noqa: BLE001
            logger.exception("signal rule %s failed", rule_id)
    return signals


__all__ = [
    "RULESET_VERSION", "SEVERITIES", "STATUSES", "STATUS_LABELS",
    "OPEN_STATUSES", "ALLOWED_TRANSITIONS",
    "STATUS_DETECTED", "STATUS_LAB_VERIFICATION", "STATUS_UNDER_REVIEW",
    "STATUS_ASSIGNED", "STATUS_ACTIONED", "STATUS_RESOLVED", "STATUS_CLOSED",
    "STATUS_DISMISSED",
    "SignalRule", "RULES", "Signal", "init_signal_schema",
    "last_line_class", "detect_all", "DETECTORS",
]


# ---------------------------------------------------------------------------
# Persistence and lifecycle
# ---------------------------------------------------------------------------

def record_signals(signals: Sequence[Signal], *,
                   actor: str = "system") -> Dict[str, int]:
    """Store detected signals, updating rather than duplicating.

    A signal's fingerprint covers its rule, version, scope and latest specimen
    date, so re-running detection over unchanged data touches ``last_seen_at``
    and leaves a reviewer's progress alone. Re-raising a signal someone has
    already dismissed would make the queue unusable.

    Existing keys are fetched in one query and new rows inserted in one batch.
    The first version issued a SELECT and an INSERT per signal, which is two
    round trips each to a hosted database and took minutes on a few hundred.
    """
    counts = {"new": 0, "refreshed": 0}
    if not signals:
        return counts

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        raw_cur = cur.raw

        keys = [s.signal_key for s in signals]
        cur.execute("SELECT signal_key FROM signals WHERE signal_key = ANY(%s)",
                    (keys,))
        known = {r[0] for r in cur.fetchall()}

        refreshed = [s for s in signals if s.signal_key in known]
        fresh = [s for s in signals if s.signal_key not in known]

        if refreshed:
            psycopg2.extras.execute_values(
                raw_cur,
                "UPDATE signals AS t SET last_seen_at = now(), value = v.value, "
                "numerator = v.numerator, denominator = v.denominator, "
                "baseline_value = v.baseline_value "
                "FROM (VALUES %s) AS v(signal_key, value, numerator, "
                "denominator, baseline_value) "
                "WHERE t.signal_key = v.signal_key",
                [(s.signal_key, s.value, s.numerator, s.denominator,
                  s.baseline_value) for s in refreshed],
                template="(%s, %s::double precision, %s::double precision, "
                         "%s::double precision, %s::double precision)")
            counts["refreshed"] = len(refreshed)

        if fresh:
            rows = []
            for s in fresh:
                rule = s.rule
                rows.append((
                    s.signal_key, s.dataset_id, s.rule_id, s.rule_version,
                    s.sector, s.organism, s.antibiotic, s.region, s.lab_name,
                    s.title, s.explanation, s.severity, s.numerator,
                    s.denominator, s.value, s.threshold, s.baseline_value,
                    rule.surveillance_unit, rule.denominator_definition,
                    rule.baseline_definition, rule.minimum_data,
                    json.dumps(list(s.affected_isolates)),
                    s.first_specimen_date, s.last_specimen_date, STATUS_DETECTED,
                ))
            psycopg2.extras.execute_values(raw_cur, """
                INSERT INTO signals
                (signal_key, dataset_id, rule_id, rule_version, sector, organism,
                 antibiotic, region, lab_name, title, explanation, severity,
                 numerator, denominator, value, threshold, baseline_value,
                 surveillance_unit, denominator_definition, baseline_definition,
                 minimum_data, affected_isolates, first_specimen_date,
                 last_specimen_date, status)
                VALUES %s ON CONFLICT (signal_key) DO NOTHING
            """, rows, page_size=200)

            # The detection entry in the append-only log, for the rows just
            # created. Selected back by key so the generated ids are correct.
            cur.execute(
                "SELECT signal_id, rule_id, rule_version FROM signals "
                "WHERE signal_key = ANY(%s)",
                ([s.signal_key for s in fresh],))
            created = cur.fetchall()
            psycopg2.extras.execute_values(raw_cur, """
                INSERT INTO signal_actions
                (signal_id, from_status, to_status, actor, actor_role, note)
                VALUES %s
            """, [(int(r[0]), None, STATUS_DETECTED, actor, "detection rule",
                   f"Raised by rule {r[1]} version {r[2]}.")
                  for r in created], page_size=200)
            counts["new"] = len(fresh)

        conn.commit()
    except Exception:                                 # noqa: BLE001
        conn.rollback()
        logger.exception("record_signals failed")
        raise
    finally:
        conn.close()
    return counts


def advance_signal(signal_id: int, to_status: str, *, actor: str,
                   actor_role: str = "", note: str = "", evidence: str = "",
                   assigned_to: str = "", due_date: Optional[date] = None
                   ) -> Tuple[bool, str]:
    """Move a signal to the next lifecycle state.

    Transitions are checked against ALLOWED_TRANSITIONS, so a signal cannot go
    from detected straight to resolved without anyone having reviewed it. The
    move is written to the append-only action log in the same transaction as the
    status change: a handoff recorded separately from the change it describes is
    not an audit trail.
    """
    if to_status not in STATUSES:
        return False, f"{to_status!r} is not a known status."

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM signals WHERE signal_id = %s", (signal_id,))
        row = cur.fetchone()
        if row is None:
            return False, "No such signal."
        current = row[0]

        allowed = ALLOWED_TRANSITIONS.get(current, ())
        if to_status not in allowed:
            readable = ", ".join(STATUS_LABELS[s] for s in allowed) or "nothing"
            return False, (
                f"A signal that is '{STATUS_LABELS[current]}' can only move to: "
                f"{readable}.")

        if to_status == STATUS_ASSIGNED and not assigned_to:
            return False, "Assigning a signal requires a response owner."
        if to_status == STATUS_RESOLVED and not evidence:
            return False, ("Resolving a signal requires evidence of what was "
                           "done and what changed.")
        if to_status == STATUS_DISMISSED and not note:
            return False, "Dismissing a signal requires a reason."

        cur.execute("""
            UPDATE signals
               SET status = %s, status_changed_at = now(),
                   assigned_to = COALESCE(NULLIF(%s, ''), assigned_to),
                   due_date = COALESCE(%s, due_date)
             WHERE signal_id = %s
        """, (to_status, assigned_to, due_date, signal_id))
        cur.execute("""
            INSERT INTO signal_actions
            (signal_id, from_status, to_status, actor, actor_role, note,
             evidence, assigned_to, due_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (signal_id, current, to_status, actor, actor_role, note,
              evidence, assigned_to or None, due_date))
        conn.commit()
        return True, f"Signal moved to '{STATUS_LABELS[to_status]}'."
    except Exception as exc:                          # noqa: BLE001
        conn.rollback()
        logger.exception("advance_signal failed")
        return False, f"Could not update the signal: {exc}"
    finally:
        conn.close()


def list_signals(*, status: Optional[Sequence[str]] = None,
                 dataset_id: Optional[str] = None,
                 rule_id: Optional[str] = None,
                 severity: Optional[Sequence[str]] = None) -> pd.DataFrame:
    """Signals matching the filters, newest first."""
    clauses, params = [], []
    if status:
        clauses.append("status = ANY(%s)")
        params.append(list(status))
    if dataset_id:
        # A signal raised across the whole platform carries no dataset, and it
        # still concerns whichever dataset the user is looking at. Filtering it
        # out left the queue empty whenever a dataset was selected, which is the
        # normal case, so the page reported no signals while 278 were stored.
        clauses.append("(dataset_id = %s OR dataset_id IS NULL)")
        params.append(dataset_id)
    if rule_id:
        clauses.append("rule_id = %s")
        params.append(rule_id)
    if severity:
        clauses.append("severity = ANY(%s)")
        params.append(list(severity))

    sql = "SELECT * FROM signals"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY detected_at DESC"

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, tuple(params) if params else None)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
    finally:
        conn.close()
    return pd.DataFrame([dict(r) for r in rows], columns=columns)


def signal_history(signal_id: int) -> pd.DataFrame:
    """The append-only action log for one signal."""
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT from_status, to_status, actor, actor_role, note, evidence,
                   assigned_to, due_date, occurred_at
              FROM signal_actions
             WHERE signal_id = %s
             ORDER BY occurred_at, action_id
        """, (signal_id,))
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
    finally:
        conn.close()
    return pd.DataFrame([dict(r) for r in rows], columns=columns)


def response_timeliness(dataset_id: Optional[str] = None) -> Dict[str, object]:
    """How long each stage of the response takes.

    The review asked that programme managers be able to see time from specimen
    collection to confirmed result, alert review, notification and response.
    Medians, because a handful of long-running signals would otherwise dominate
    a mean and hide the typical case.

    The whole action log is fetched in one query. Fetching it per signal was a
    round trip each, which over a network to a hosted database made the page
    take minutes on a few hundred signals.
    """
    signals = list_signals(dataset_id=dataset_id)
    if signals.empty:
        return {"signals": 0}

    conn = db.get_connection()
    try:
        cur = conn.cursor()
        if dataset_id:
            cur.execute("""
                SELECT a.signal_id, a.to_status, a.occurred_at
                  FROM signal_actions a
                  JOIN signals s ON s.signal_id = a.signal_id
                 WHERE s.dataset_id = %s OR s.dataset_id IS NULL
            """, (dataset_id,))
        else:
            cur.execute(
                "SELECT signal_id, to_status, occurred_at FROM signal_actions")
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
    finally:
        conn.close()
    history = pd.DataFrame([dict(r) for r in rows], columns=columns)

    detected_at = signals.set_index("signal_id")["detected_at"]

    def _median_days(to_status: str) -> Optional[float]:
        if history.empty:
            return None
        reached = history[history["to_status"] == to_status]
        if reached.empty:
            return None
        origin = reached["signal_id"].map(detected_at)
        delta = (pd.to_datetime(reached["occurred_at"], utc=True)
                 - pd.to_datetime(origin, utc=True))
        days = (delta.dt.total_seconds() / 86400).dropna()
        return float(days.median()) if not days.empty else None

    # Specimen to detection: how stale a signal is by the time it is raised.
    specimen_to_detection = None
    dated = signals.dropna(subset=["last_specimen_date"])
    if not dated.empty:
        delta = (pd.to_datetime(dated["detected_at"], utc=True).dt.tz_localize(None)
                 - pd.to_datetime(dated["last_specimen_date"]))
        days = (delta.dt.total_seconds() / 86400).dropna()
        specimen_to_detection = float(days.median()) if not days.empty else None

    open_signals = signals[signals["status"].isin(OPEN_STATUSES)]
    overdue = 0
    if not open_signals.empty and "due_date" in open_signals.columns:
        due = pd.to_datetime(open_signals["due_date"], errors="coerce")
        overdue = int((due.notna() & (due < pd.Timestamp.now())).sum())

    return {
        "signals": int(len(signals)),
        "open": int(len(open_signals)),
        "overdue": overdue,
        "median_days_specimen_to_detection": specimen_to_detection,
        "median_days_to_review": _median_days(STATUS_UNDER_REVIEW),
        "median_days_to_assignment": _median_days(STATUS_ASSIGNED),
        "median_days_to_action": _median_days(STATUS_ACTIONED),
        "median_days_to_resolution": _median_days(STATUS_RESOLVED),
        "by_status": signals["status"].value_counts().to_dict(),
        "by_severity": signals["severity"].value_counts().to_dict(),
    }


def rules_frame() -> pd.DataFrame:
    """Every rule, described. Published so a reviewer can judge a signal."""
    return pd.DataFrame([rule.as_row() for rule in RULES.values()])


__all__ += [
    "record_signals", "advance_signal", "list_signals", "signal_history",
    "response_timeliness", "rules_frame",
]
