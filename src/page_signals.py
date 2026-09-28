"""
Signals & Response page.

The review asked for an operational lifecycle rather than a list of thresholds
that have been crossed:

    machine signal -> laboratory verification -> epidemiologist/clinician review
    -> assigned response owner -> action and due date -> resolution/evidence ->
    closure

This page is that queue. Each signal carries the rule and version that raised
it, its numerator and denominator with the denominator defined in words, its
surveillance unit, its baseline, the isolates behind it and a plain explanation
of why it fired -- so a reviewer can judge it without re-deriving it.

Nothing here notifies anyone. The review asks that sensitivity and false-alarm
burden be piloted against historical data before any automatic notification or
escalation, so signals are raised for review and that is the whole of it.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from src import signals as sig

_SEVERITY_ORDER = {sig.SEVERITY_CRITICAL: 0, sig.SEVERITY_HIGH: 1,
                   sig.SEVERITY_MODERATE: 2, sig.SEVERITY_INFO: 3}

_SEVERITY_COLOUR = {
    sig.SEVERITY_CRITICAL: "#7f1d1d",
    sig.SEVERITY_HIGH: "#b91c1c",
    sig.SEVERITY_MODERATE: "#b45309",
    sig.SEVERITY_INFO: "#0e7490",
}

#: What each transition needs from the person making it.
_TRANSITION_FORM = {
    sig.STATUS_LAB_VERIFICATION: {"note": "What the laboratory is being asked to do"},
    sig.STATUS_UNDER_REVIEW: {"note": "What the laboratory found"},
    sig.STATUS_ASSIGNED: {"assigned_to": "Response owner", "due_date": True,
                          "note": "What is being asked of them"},
    sig.STATUS_ACTIONED: {"note": "What was done"},
    sig.STATUS_RESOLVED: {"evidence": "Evidence of the outcome"},
    sig.STATUS_CLOSED: {"note": "Closing note"},
    sig.STATUS_DISMISSED: {"note": "Why this signal is not actionable"},
}


def _can_act() -> bool:
    """Working a signal changes a shared record, so it needs a signed-in user."""
    return bool(st.session_state.get("is_admin"))


def _run_detection(dataset_id: Optional[str]) -> None:
    with st.spinner("Running detection rules over the surveillance chain…"):
        try:
            found = sig.detect_all(dataset_id=dataset_id)
            counts = sig.record_signals(
                found, actor=st.session_state.get("user_email") or "system")
        except Exception as exc:                      # noqa: BLE001
            st.error(f"Detection failed: {exc}")
            return
    st.success(
        f"{counts['new']} new signal(s); {counts['refreshed']} already known and "
        "refreshed. Signals already under review keep their progress."
    )


def _overview(timeliness: Dict[str, object]) -> None:
    a, b, c, d = st.columns(4)
    a.metric("Open signals", f"{timeliness.get('open', 0):,}")
    a.caption("Detected, with the laboratory, under review, assigned or actioned")
    b.metric("Overdue", f"{timeliness.get('overdue', 0):,}",
             help="Assigned with a due date that has passed")
    lag = timeliness.get("median_days_specimen_to_detection")
    c.metric("Specimen to detection",
             f"{lag:.0f} days" if lag is not None else "—",
             help="Median age of the most recent specimen behind a signal when "
                  "the signal was raised. A large number means signals describe "
                  "the past rather than the present.")
    resolution = timeliness.get("median_days_to_resolution")
    d.metric("Detection to resolution",
             f"{resolution:.1f} days" if resolution is not None else "—",
             help="Median across resolved signals")

    if lag is not None and lag > 90:
        st.warning(
            f"Signals are being raised a median of {lag:.0f} days after the "
            "specimen was collected. At that lag these are a record of what "
            "happened, not an early warning, and they should not be described "
            "as real-time detection."
        )

    by_status = timeliness.get("by_status") or {}
    if by_status:
        frame = pd.DataFrame([
            {"Stage": sig.STATUS_LABELS.get(k, k), "Signals": v,
             "_order": list(sig.STATUSES).index(k) if k in sig.STATUSES else 99}
            for k, v in by_status.items()]).sort_values("_order")
        figure = px.bar(frame, x="Signals", y="Stage", orientation="h",
                        text="Signals")
        figure.update_layout(height=max(280, 34 * len(frame)),
                            margin=dict(l=10, r=10, t=30, b=10),
                            yaxis={"categoryorder": "array",
                                   "categoryarray": frame["Stage"].tolist()[::-1]})
        st.plotly_chart(figure, use_container_width=True)
        st.caption(
            "Where signals sit in the response lifecycle. A queue that is all "
            "'Detected by rule' means signals are being generated but not worked."
        )


def _signal_card(row: pd.Series) -> None:
    severity = str(row["severity"])
    colour = _SEVERITY_COLOUR.get(severity, "#475569")
    st.markdown(
        f"<div style='border-left:4px solid {colour};padding:2px 0 2px 12px;'>"
        f"<strong>{row['title']}</strong><br>"
        f"<span style='color:#64748b;font-size:0.86rem'>"
        f"{severity.title()} · {sig.STATUS_LABELS.get(str(row['status']), row['status'])}"
        f" · rule {row['rule_id']} v{row['rule_version']}</span></div>",
        unsafe_allow_html=True)

    st.markdown(row["explanation"])

    detail, method, history, action = st.tabs(
        ["Numbers", "How it was derived", "History", "Work this signal"])

    with detail:
        left, right = st.columns(2)
        with left:
            st.markdown(f"**Numerator.** {row.get('numerator')}")
            st.markdown(f"**Denominator.** {row.get('denominator')}")
            if pd.notna(row.get("value")):
                st.markdown(f"**Value.** {row['value']:.1f}")
            if pd.notna(row.get("baseline_value")):
                st.markdown(f"**Baseline.** {row['baseline_value']:.1f}")
            if pd.notna(row.get("threshold")):
                st.markdown(f"**Threshold.** {row['threshold']}")
        with right:
            for label, key in (("Sector", "sector"), ("Organism", "organism"),
                               ("Antibiotic", "antibiotic"),
                               ("Laboratory", "lab_name"), ("Region", "region")):
                if row.get(key):
                    st.markdown(f"**{label}.** {row[key]}")
            for label, key in (("First specimen", "first_specimen_date"),
                               ("Most recent specimen", "last_specimen_date")):
                if row.get(key) is not None and pd.notna(row.get(key)):
                    st.markdown(f"**{label}.** {row[key]}")

        isolates = row.get("affected_isolates")
        if isolates:
            try:
                listed = json.loads(isolates) if isinstance(isolates, str) else list(isolates)
            except (TypeError, ValueError):
                listed = []
            if listed:
                with st.expander(f"Affected isolates ({len(listed)})"):
                    st.code("\n".join(listed[:200]))

    with method:
        st.markdown(f"**Surveillance unit.** {row.get('surveillance_unit')}")
        st.markdown(f"**Denominator.** {row.get('denominator_definition')}")
        st.markdown(f"**Baseline.** {row.get('baseline_definition')}")
        st.markdown(f"**Minimum data.** {row.get('minimum_data')}")
        rule = sig.RULES.get(str(row["rule_id"]))
        if rule:
            st.info(rule.governance)

    with history:
        log = sig.signal_history(int(row["signal_id"]))
        if log.empty:
            st.caption("No history recorded.")
        else:
            st.dataframe(
                log.rename(columns={
                    "from_status": "From", "to_status": "To", "actor": "By",
                    "actor_role": "Role", "note": "Note", "evidence": "Evidence",
                    "assigned_to": "Owner", "due_date": "Due",
                    "occurred_at": "When"}),
                use_container_width=True, hide_index=True)

    with action:
        _action_form(row)


def _action_form(row: pd.Series) -> None:
    signal_id = int(row["signal_id"])
    current = str(row["status"])
    allowed = sig.ALLOWED_TRANSITIONS.get(current, ())

    if not allowed:
        st.caption(
            f"This signal is {sig.STATUS_LABELS[current].lower()}. There is "
            "nothing further to record; its history above is the permanent "
            "account of how it was handled."
        )
        return

    if not _can_act():
        st.info(
            "Working a signal changes a shared record, so it needs an "
            "administrator sign-in. The signal and its history are readable "
            "without one."
        )
        return

    with st.form(f"signal_action_{signal_id}"):
        to_status = st.selectbox(
            "Move to", allowed,
            format_func=lambda s: sig.STATUS_LABELS[s],
            key=f"to_{signal_id}")
        required = _TRANSITION_FORM.get(to_status, {})

        assigned_to, due_date, note, evidence = "", None, "", ""
        if "assigned_to" in required:
            assigned_to = st.text_input(required["assigned_to"],
                                        key=f"owner_{signal_id}")
        if required.get("due_date"):
            due_date = st.date_input(
                "Due date", value=dt.date.today() + dt.timedelta(days=14),
                key=f"due_{signal_id}")
        if "note" in required:
            note = st.text_area(required["note"], key=f"note_{signal_id}")
        if "evidence" in required:
            evidence = st.text_area(required["evidence"],
                                    key=f"evidence_{signal_id}",
                                    help="What changed, and how it is known. A "
                                         "signal cannot be resolved without it.")

        actor_role = st.text_input("Your role", value="",
                                   key=f"role_{signal_id}",
                                   placeholder="epidemiologist, IPC lead, "
                                               "laboratory scientist")
        submitted = st.form_submit_button("Record")

    if submitted:
        ok, message = sig.advance_signal(
            signal_id, to_status,
            actor=st.session_state.get("user_email") or "unknown",
            actor_role=actor_role, note=note, evidence=evidence,
            assigned_to=assigned_to, due_date=due_date)
        if ok:
            st.success(message)
            st.rerun()
        else:
            st.error(message)


def _queue(dataset_id: Optional[str]) -> None:
    left, middle, right = st.columns(3)
    with left:
        show = st.selectbox(
            "Show", ["Open", "All", "Closed or dismissed"], key="sig_show")
    with middle:
        severities = st.multiselect(
            "Severity", list(sig.SEVERITIES),
            default=[sig.SEVERITY_CRITICAL, sig.SEVERITY_HIGH],
            format_func=str.title, key="sig_sev")
    with right:
        rule_ids = ["(all)"] + list(sig.RULES)
        rule_choice = st.selectbox(
            "Rule", rule_ids,
            format_func=lambda r: "All rules" if r == "(all)" else sig.RULES[r].name,
            key="sig_rule")

    status_filter = {
        "Open": list(sig.OPEN_STATUSES),
        "All": None,
        "Closed or dismissed": [sig.STATUS_CLOSED, sig.STATUS_DISMISSED],
    }[show]

    frame = sig.list_signals(
        status=status_filter, dataset_id=dataset_id,
        rule_id=None if rule_choice == "(all)" else rule_choice,
        severity=severities or None)

    if frame.empty:
        st.info("No signals match those filters.")
        return

    frame = frame.assign(
        _severity_order=frame["severity"].map(_SEVERITY_ORDER).fillna(9)
    ).sort_values(["_severity_order", "detected_at"], ascending=[True, False])

    st.caption(f"{len(frame):,} signal(s). Most severe first.")
    page_size = 20
    total_pages = (len(frame) + page_size - 1) // page_size
    page = 1
    if total_pages > 1:
        page = st.number_input("Page", min_value=1, max_value=total_pages,
                               value=1, step=1, key="sig_page")
    window = frame.iloc[(page - 1) * page_size: page * page_size]

    for _, row in window.iterrows():
        with st.expander(
                f"{str(row['severity']).title()} — {row['title']}", expanded=False):
            _signal_card(row)


def render_signals_page() -> None:
    st.header("Signals & Response")
    st.caption(
        "Detected signals and the response to each. Every signal states the "
        "rule that raised it, its denominator and its baseline, so it can be "
        "judged rather than merely counted."
    )

    dataset_id = st.session_state.get("active_dataset_id")

    try:
        timeliness = sig.response_timeliness(dataset_id=dataset_id)
    except Exception as exc:                          # noqa: BLE001
        st.error(f"Could not read the signal queue: {exc}")
        return

    header_left, header_right = st.columns([3, 1])
    with header_right:
        if _can_act():
            if st.button("Run detection now", use_container_width=True):
                _run_detection(dataset_id)
                st.rerun()
        else:
            st.caption("Sign in to run detection.")

    if not timeliness.get("signals"):
        st.info(
            "No signals recorded yet. Run detection to screen the surveillance "
            "chain against the rules listed under **Rules**."
        )
        with st.expander("The rules that would be applied", expanded=True):
            st.dataframe(sig.rules_frame(), use_container_width=True,
                         hide_index=True)
        return

    queue, overview, rules = st.tabs(["Queue", "Response performance", "Rules"])
    with queue:
        _queue(dataset_id)
    with overview:
        _overview(timeliness)
    with rules:
        st.caption(
            "Every rule, with its surveillance unit, denominator, minimum data "
            "requirement, baseline and governance status. Thresholds are "
            "defaults for review and have not been approved as national action "
            "thresholds."
        )
        st.dataframe(sig.rules_frame(), use_container_width=True,
                     hide_index=True)


__all__ = ["render_signals_page"]
