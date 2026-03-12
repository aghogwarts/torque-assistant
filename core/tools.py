import logging
from datetime import datetime, timezone

logger = logging.getLogger("torque.tools")

# Accumulated during a batch run. reporter.py reads this to populate
# the actions/faults sections of the run report. Cleared at start of
# each main() call via clear_run_log().
RUN_LOG: list[dict] = []


def clear_run_log():
    """Call once at the start of each batch run to reset the log."""
    RUN_LOG.clear()


def _log_action(event_id: str, action: str, detail: str):
    """Append one tool action to RUN_LOG with a UTC timestamp."""
    RUN_LOG.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id": event_id,
            "action": action,
            "detail": detail,
        }
    )


# ── Tool functions ────────────────────────────────────────────────────────────


def create_escalation_ticket(event_id: str, reason: str):
    logger.debug("[TOOL] Escalation ticket created for %s", event_id)
    logger.debug("[TOOL] Reason: %s", reason)
    _log_action(event_id, "ESCALATED", reason)
    return {"status": "ESCALATED"}


def log_rework(event_id: str, note: str):
    logger.debug("[TOOL] Rework logged for %s", event_id)
    logger.debug("[TOOL] Note: %s", note)
    _log_action(event_id, "REWORK_LOGGED", note)
    return {"status": "REWORK_LOGGED"}


def close_incident(event_id: str):
    logger.debug("[TOOL] Incident %s closed", event_id)
    _log_action(event_id, "CLOSED", "")
    return {"status": "CLOSED"}
