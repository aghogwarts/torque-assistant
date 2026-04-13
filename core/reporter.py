"""
reporter.py

Writes the three-file run report after each batch:
  run_reports/<batch_label>/
      report.json   — full per-event data + summary stats
      report.csv    — flat tabular, one row per event
      report.txt    — human-readable summary with descriptive text

Call save_report(results, run_log, batch_label) from main.py after the
batch loop finishes. Does not depend on any other core/ module.
"""

import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone

# ── Public entry point ────────────────────────────────────────────────────────


def save_report(results: list[dict], run_log: list[dict], batch_label: str):
    """
    Orchestrates writing all three report files into
    run_reports/<batch_label>/. Creates the directory if needed.
    """
    out_dir = os.path.join("run_reports", batch_label)
    os.makedirs(out_dir, exist_ok=True)

    _write_json(results, run_log, os.path.join(out_dir, "report.json"))
    _write_csv(results, os.path.join(out_dir, "report.csv"))
    _write_txt(results, run_log, os.path.join(out_dir, "report.txt"), batch_label)

    print(f"\n[REPORT] Saved to {out_dir}/")
    print(f"         report.json | report.csv | report.txt")


# ── Stats helper ──────────────────────────────────────────────────────────────


def _build_stats(results: list[dict], run_log: list[dict]) -> dict:
    """
    Derives all summary statistics from the results list and run_log.
    Centralised here so all three writers use identical numbers.
    """
    total = len(results)
    errors = [r for r in results if r["error"]]
    processed = total - len(errors)

    auto_closed = [r for r in results if "auto_close" in r["path"]]
    full_path = [r for r in results if "auto_close" not in r["path"] and not r["error"]]

    validation_counts = Counter(r["validation"] for r in results if r["validation"])
    severity_counts = Counter(r["severity"] for r in results if r["severity"])

    # Faults = any non-OK validation result
    faults = [r for r in results if r["validation"] and r["validation"] != "OK"]
    faults_by_joint = Counter(r["joint"] for r in faults)
    faults_by_type = Counter(r["validation"] for r in faults)

    # Actions from run_log
    actions = Counter(entry["action"] for entry in run_log)
    escalations = [e for e in run_log if e["action"] == "ESCALATED"]
    reworks = [e for e in run_log if e["action"] == "REWORK_LOGGED"]

    # Unknown joints (safety_critical resolved to None)
    unknown_joints = sorted(
        set(r["joint"] for r in results if r["safety_critical"] is None)
    )

    return {
        "total": total,
        "processed": processed,
        "errors": len(errors),
        "auto_closed": len(auto_closed),
        "full_path": len(full_path),
        "validation_counts": dict(validation_counts),
        "severity_counts": dict(severity_counts),
        "faults": len(faults),
        "faults_by_joint": dict(faults_by_joint.most_common()),
        "faults_by_type": dict(faults_by_type),
        "actions": dict(actions),
        "escalations": escalations,
        "reworks": reworks,
        "unknown_joints": unknown_joints,
        "error_list": [
            {"event_id": r["event_id"], "error": r["error"]} for r in errors
        ],
    }


# ── JSON writer ───────────────────────────────────────────────────────────────


def _write_json(results: list[dict], run_log: list[dict], path: str):
    """
    Full structured report — per-event results + summary stats + raw run_log.
    Useful for programmatic consumption or piping into other tools.
    """
    stats = _build_stats(results, run_log)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": stats,
        "events": results,
        "run_log": run_log,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


# ── CSV writer ────────────────────────────────────────────────────────────────


def _write_csv(results: list[dict], path: str):
    """
    Flat tabular export — one row per event.
    'path' column is the node sequence joined by ' -> '.
    Includes v2 agent decision fields: confidence, reasoning, root cause,
    recommended corrective, SOP references.
    """
    if not results:
        return

    fieldnames = [
        "event_id",
        "joint",
        "validation",
        "severity",
        "safety_critical",
        "path",
        "action",
        "confidence",
        "reasoning",
        "root_cause_hypothesis",
        "recommended_corrective",
        "sop_references",
        "error",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            sop_refs = r.get("sop_references") or []
            writer.writerow(
                {
                    "event_id": r["event_id"],
                    "joint": r["joint"],
                    "validation": r["validation"] or "",
                    "severity": r["severity"] or "",
                    "safety_critical": r["safety_critical"],
                    "path": " -> ".join(r["path"]),
                    "action": r["action"] or "",
                    "confidence": r.get("confidence") or "",
                    "reasoning": r.get("reasoning") or "",
                    "root_cause_hypothesis": r.get("root_cause_hypothesis") or "",
                    "recommended_corrective": r.get("recommended_corrective") or "",
                    "sop_references": "; ".join(sop_refs) if sop_refs else "",
                    "error": r["error"] or "",
                }
            )


# ── TXT writer ────────────────────────────────────────────────────────────────


def _write_txt(results: list[dict], run_log: list[dict], path: str, batch_label: str):
    """
    Human-readable summary report.
    Sections: header, batch info, event statistics, validation breakdown,
    severity breakdown, routing breakdown, faults detail, actions taken,
    unknown joints, errors.
    """
    s = _build_stats(results, run_log)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = []

    def ln(text=""):
        lines.append(text)

    # ── Header ────────────────────────────────────────────────────────────────
    ln("=" * 70)
    ln("  TORQUE INCIDENT MANAGEMENT — BATCH RUN REPORT")
    ln("=" * 70)
    ln(f"  Generated : {now}")
    ln(f"  Batch     : {batch_label}")
    ln()

    # ── Batch info ────────────────────────────────────────────────────────────
    ln("BATCH INFO")
    ln("-" * 40)
    ln(f"  This report covers {s['total']} tightening events processed in a single")
    ln(f"  batch run of the Torque Incident Management workflow. Each event")
    ln(f"  represents one fastener tightening operation from the assembly line.")
    ln()
    ln(f"  Total events submitted : {s['total']}")
    ln(f"  Successfully processed : {s['processed']}")
    if s["errors"]:
        ln(f"  Errors (skipped)       : {s['errors']}")
    ln()

    # ── Event statistics ──────────────────────────────────────────────────────
    ln("EVENT STATISTICS")
    ln("-" * 40)
    ln(f"  Events were routed through the LangGraph workflow. Clean events on")
    ln(f"  non-safety-critical joints bypass the LLM entirely (auto-close fast")
    ln(f"  path). All other events go through RAG retrieval and the decision agent.")
    ln()
    ln(f"  Auto-closed (no LLM)   : {s['auto_closed']}")
    ln(f"  Full path (LLM used)   : {s['full_path']}")
    if s["total"] > 0:
        pct = round(s["auto_closed"] / s["total"] * 100, 1)
        ln(f"  Auto-close rate        : {pct}%")
    ln()

    # ── Validation breakdown ──────────────────────────────────────────────────
    ln("VALIDATION BREAKDOWN")
    ln("-" * 40)
    ln(f"  Validation checks torque and angle readings against SOP spec tolerances.")
    ln()
    for label, key in [
        ("OK", "OK"),
        ("Over-torque", "OVER_TORQUE"),
        ("Under-torque", "UNDER_TORQUE"),
        ("Angle missing", "ANGLE_MISSING"),
    ]:
        count = s["validation_counts"].get(key, 0)
        ln(f"  {label:<20} : {count}")
    ln()

    # ── Severity breakdown ────────────────────────────────────────────────────
    ln("SEVERITY BREAKDOWN")
    ln("-" * 40)
    ln(f"  Severity is determined by the validation result and whether the joint")
    ln(f"  is safety-critical per the SOP spec.")
    ln()
    for label, key in [
        ("LOW  (OK result)", "LOW"),
        ("MEDIUM (deviation, non-critical)", "MEDIUM"),
        ("HIGH   (deviation, safety-critical)", "HIGH"),
    ]:
        count = s["severity_counts"].get(key, 0)
        ln(f"  {label:<38} : {count}")
    ln()

    # ── Faults detail ─────────────────────────────────────────────────────────
    ln("FAULTS FOUND")
    ln("-" * 40)
    if s["faults"] == 0:
        ln("  No faults detected in this batch.")
    else:
        ln(f"  {s['faults']} event(s) with a non-OK validation result.")
        ln()
        ln("  By type:")
        for fault_type, count in s["faults_by_type"].items():
            ln(f"    {fault_type:<20} : {count}")
        ln()
        ln("  By joint (most affected first):")
        for joint, count in s["faults_by_joint"].items():
            ln(f"    {joint:<35} : {count}")
    ln()

    # ── Actions taken ─────────────────────────────────────────────────────────
    ln("ACTIONS TAKEN")
    ln("-" * 40)
    ln(f"  Actions are determined by the decision agent's reasoning or the")
    ln(f"  auto-close fast path.")
    ln()
    for action, count in s["actions"].items():
        ln(f"  {action:<20} : {count}")
    ln()

    if s["escalations"]:
        ln(f"  Escalations ({len(s['escalations'])}):")
        for e in s["escalations"]:
            ln(f"    {e['event_id']}  —  {e['detail']}")
        ln()

    if s["reworks"]:
        ln(f"  Reworks ({len(s['reworks'])}):")
        for r in s["reworks"]:
            ln(f"    {r['event_id']}  —  {r['detail']}")
        ln()

    # ── Agent decision details (v2) ───────────────────────────────────────────
    # Show per-event reasoning for all non-auto-closed events that have
    # agent decision data.
    decided_events = [r for r in results
                      if r.get("reasoning") and "auto_close" not in r["path"]]
    if decided_events:
        ln("AGENT DECISION DETAILS")
        ln("-" * 40)
        ln(f"  Per-event reasoning from the decision agent for {len(decided_events)} event(s).")
        ln()
        for r in decided_events:
            conf = r.get("confidence")
            conf_str = f"{conf:.0%}" if conf is not None else "N/A"
            flag = "  ⚠ LOW CONFIDENCE" if conf is not None and conf < 0.90 else ""
            ln(f"  {r['event_id']}  |  {r['joint']}")
            ln(f"    Action: {r.get('action', '?')}  |  Severity: {r.get('severity', '?')}  |  Confidence: {conf_str}{flag}")
            ln(f"    Reasoning: {r.get('reasoning', 'N/A')}")
            rch = r.get("root_cause_hypothesis", "")
            if rch and rch != "N/A":
                ln(f"    Root Cause: {rch}")
            rc = r.get("recommended_corrective", "")
            if rc and rc != "N/A":
                ln(f"    Recommended: {rc}")
            ln()
    ln()

    # ── Unknown joints ────────────────────────────────────────────────────────
    if s["unknown_joints"]:
        ln("UNKNOWN JOINTS  ⚠")
        ln("-" * 40)
        ln(f"  The following joints appeared in events but were not found in")
        ln(f"  sops.json. They were treated as safety-critical (fail-safe).")
        ln(f"  Add them to sops.json to resolve this.")
        ln()
        for j in s["unknown_joints"]:
            ln(f"    {j}")
        ln()

    # ── Errors ────────────────────────────────────────────────────────────────
    if s["error_list"]:
        ln("ERRORS")
        ln("-" * 40)
        ln(f"  {s['errors']} event(s) failed during processing and were skipped.")
        ln()
        for e in s["error_list"]:
            ln(f"    {e['event_id']}  —  {e['error']}")
        ln()

    ln("=" * 70)
    ln("  END OF REPORT")
    ln("=" * 70)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))