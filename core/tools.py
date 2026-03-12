# escalation tool
def create_escalation_ticket(event_id: str, reason: str):
    print(f"[TOOL] Escalation ticket created for {event_id}")
    print(f"[TOOL] Reason: {reason}")
    return {"status": "ESCALATED"}


# rework tool
def log_rework(event_id: str, note: str):
    print(f"[TOOL] Rework logged for {event_id}")
    print(f"[TOOL] Note: {note}")
    return {"status": "REWORK_LOGGED"}


# close tool
def close_incident(event_id: str):
    print(f"[TOOL] Incident {event_id} closed")
    return {"status": "CLOSED"}
