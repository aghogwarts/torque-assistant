"""
Torque Event Data Generator
============================
Generates realistic manufacturing torque events with:
  - 3 days of data, 2 shifts/day (Day: 06:00-14:00, Night: 14:00-22:00)
  - Variable cycle times per joint complexity (not uniform 30s gaps)
  - 30-min shift handover gaps between shifts
  - 3 tool drift windows — gradual calibration decay on a specific tool
  - Realistic violation clustering (violations happen in runs, not randomly)
  - TOOL_COMM_ERROR events tied to the drifting tool near peak drift
  - Expanded past_incidents.json (15 entries, richer context)
"""

import json
import random
import csv
from datetime import datetime, timedelta

random.seed(42)

# ─── Joint catalogue ──────────────────────────────────────────────────────────
# Each joint maps to its canonical specs.  cycle_time_range is the realistic
# tightening duration in seconds (affects inter-event gap variability).
JOINTS = {
    "WHEEL_LUG_NUT_FL":       {"target": 120, "tol": 10, "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "POWERTRAIN_ST-05",  "sop": "SOP-GEN-0022", "cycle": (20, 40)},
    "WHEEL_LUG_NUT_FR":       {"target": 120, "tol": 10, "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "CHASSIS_ST-14",     "sop": "SOP-GEN-0026", "cycle": (20, 40)},
    "WHEEL_LUG_NUT_RL":       {"target": 120, "tol": 10, "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "INTERIOR_ST-08",    "sop": "SOP-GEN-0071", "cycle": (20, 40)},
    "WHEEL_LUG_NUT_RR":       {"target": 120, "tol": 10, "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "FINAL_ASSY_ST-22",  "sop": "SOP-GEN-0070", "cycle": (20, 40)},
    "ENGINE_MOUNT_REAR_RIGHT":{"target": 85,  "tol": 5,  "angle": 30.0,  "safety": True,  "method": "Torque+Angle",  "station": "POWERTRAIN_ST-05",  "sop": "SOP-GEN-0006", "cycle": (45, 90)},
    "ENGINE_MOUNT_REAR_LEFT": {"target": 85,  "tol": 5,  "angle": 30.0,  "safety": True,  "method": "Torque+Angle",  "station": "FINAL_ASSY_ST-22",  "sop": "SOP-GEN-0003", "cycle": (45, 90)},
    "ENGINE_MOUNT_FRONT_RIGHT":{"target": 85, "tol": 5,  "angle": 15.0,  "safety": True,  "method": "Torque+Angle",  "station": "INTERIOR_ST-08",    "sop": "SOP-GEN-0010", "cycle": (45, 90)},
    "ENGINE_MOUNT_FRONT_LEFT":{"target": 85,  "tol": 5,  "angle": 30.0,  "safety": True,  "method": "Torque+Angle",  "station": "FINAL_ASSY_ST-22",  "sop": "SOP-GEN-0036", "cycle": (45, 90)},
    "TRANSMISSION_MOUNT_BOLT":{"target": 45,  "tol": 5,  "angle": 15.0,  "safety": True,  "method": "Torque+Angle",  "station": "POWERTRAIN_ST-05",  "sop": "SOP-GEN-0020", "cycle": (35, 70)},
    "BRAKE_CALIPER_BOLT":     {"target": 60,  "tol": 5,  "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "FINAL_ASSY_ST-22",  "sop": "SOP-GEN-0031", "cycle": (25, 50)},
    "SUSPENSION_ARM_BOLT_R":  {"target": 100, "tol": 5,  "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "POWERTRAIN_ST-05",  "sop": "SOP-GEN-0034", "cycle": (30, 60)},
    "SUSPENSION_ARM_BOLT_F":  {"target": 100, "tol": 5,  "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "INTERIOR_ST-08",    "sop": "SOP-GEN-0016", "cycle": (30, 60)},
    "STEERING_COLUMN_BOLT":   {"target": 40,  "tol": 5,  "angle": None,  "safety": True,  "method": "TorqueOnly",    "station": "INTERIOR_ST-08",    "sop": "SOP-GEN-0014", "cycle": (30, 55)},
    "SEAT_FRAME_REAR_L":      {"target": 45,  "tol": 5,  "angle": None,  "safety": False, "method": "TorqueOnly",    "station": "POWERTRAIN_ST-05",  "sop": "SOP-GEN-0073", "cycle": (15, 30)},
    "SEAT_FRAME_REAR_R":      {"target": 45,  "tol": 5,  "angle": None,  "safety": False, "method": "TorqueOnly",    "station": "CHASSIS_ST-14",     "sop": "SOP-GEN-0066", "cycle": (15, 30)},
    "BATTERY_HOLD_DOWN":      {"target": 65,  "tol": 5,  "angle": None,  "safety": False, "method": "TorqueOnly",    "station": "POWERTRAIN_ST-05",  "sop": "SOP-GEN-0023", "cycle": (20, 45)},
}

# Primary tool per joint (consistent with original data)
JOINT_TOOL = {
    "WHEEL_LUG_NUT_FL":        "MANUAL_WRENCH",
    "WHEEL_LUG_NUT_FR":        "MANUAL_WRENCH",
    "WHEEL_LUG_NUT_RL":        "MANUAL_WRENCH",
    "WHEEL_LUG_NUT_RR":        "DC_GUN",
    "ENGINE_MOUNT_REAR_RIGHT":  "PNEUMATIC_TQ",
    "ENGINE_MOUNT_REAR_LEFT":   "MANUAL_WRENCH",
    "ENGINE_MOUNT_FRONT_RIGHT": "DC_GUN",
    "ENGINE_MOUNT_FRONT_LEFT":  "ELECTRIC_ANGLE_GUN",
    "TRANSMISSION_MOUNT_BOLT":  "PNEUMATIC_TQ",
    "BRAKE_CALIPER_BOLT":       "MANUAL_WRENCH",
    "SUSPENSION_ARM_BOLT_R":    "DC_GUN",
    "SUSPENSION_ARM_BOLT_F":    "DC_GUN",
    "STEERING_COLUMN_BOLT":     "ELECTRIC_ANGLE_GUN",
    "SEAT_FRAME_REAR_L":        "PNEUMATIC_TQ",
    "SEAT_FRAME_REAR_R":        "PNEUMATIC_TQ",
    "BATTERY_HOLD_DOWN":        "PNEUMATIC_TQ",
}

VEHICLE_MODELS = ["Sedan-X", "Hatch-A", "SUV-Z", "EV-Q", "Truck-T"]

# ─── Drift window definitions ─────────────────────────────────────────────────
# Each drift window describes a period where one tool gradually goes out of
# calibration.  bias_start → bias_end is the Nm offset that ramps linearly
# across the window.  affected_joints is which joints that tool serves.
DRIFT_WINDOWS = [
    {
        # Day 1, shift 2 — DC_GUN starts drifting over-torque (worn clutch)
        "tool": "DC_GUN",
        "day": 0,
        "shift": 1,
        "start_pct": 0.20,     # starts earlier in the shift
        "end_pct": 0.95,
        "bias_start": 1.0,
        "bias_end": 13.0,      # peaks at +13 Nm — well past 5/10 Nm tolerance
        "direction": "over",
        "affected_joints": ["WHEEL_LUG_NUT_RR", "ENGINE_MOUNT_FRONT_RIGHT", "SUSPENSION_ARM_BOLT_R", "SUSPENSION_ARM_BOLT_F"],
        "comm_error_near_peak": True,
    },
    {
        # Day 2, shift 1 — PNEUMATIC_TQ under-torque drift (pressure drop)
        "tool": "PNEUMATIC_TQ",
        "day": 1,
        "shift": 0,
        "start_pct": 0.15,
        "end_pct": 0.95,
        "bias_start": -1.0,
        "bias_end": -14.0,     # drops to -14 Nm — breaches 5 Nm tolerance hard
        "direction": "under",
        "affected_joints": ["TRANSMISSION_MOUNT_BOLT", "ENGINE_MOUNT_REAR_RIGHT", "SEAT_FRAME_REAR_L", "SEAT_FRAME_REAR_R", "BATTERY_HOLD_DOWN"],
        "comm_error_near_peak": False,
    },
    {
        # Day 3, shift 1 — ELECTRIC_ANGLE_GUN angle sensor fault
        "tool": "ELECTRIC_ANGLE_GUN",
        "day": 2,
        "shift": 0,
        "start_pct": 0.25,
        "end_pct": 0.80,
        "bias_start": 0.0,
        "bias_end": 0.0,
        "direction": "angle",
        "affected_joints": ["ENGINE_MOUNT_FRONT_LEFT", "STEERING_COLUMN_BOLT", "TRANSMISSION_MOUNT_BOLT"],
        "comm_error_near_peak": False,
    },
]

# Baseline random violation rate for process noise (independent of drift)
# Simulates normal process variation that occasionally breaches tolerance
BASELINE_VIOLATION_RATE = 0.03   # 3% of all events

# ─── Schedule ─────────────────────────────────────────────────────────────────
START_DATE = datetime(2026, 3, 3)   # Monday
SHIFTS = [
    {"name": "Day",   "start_h": 6,  "end_h": 14},
    {"name": "Night", "start_h": 14, "end_h": 22},
]
HANDOVER_MINUTES = 30   # gap between shifts

EVENTS_PER_SHIFT = 167  # ~3 days × 2 shifts × 167 ≈ 1000 events total

# ─── Helpers ──────────────────────────────────────────────────────────────────

def vin():
    return f"VIN{random.randint(1000000000, 9999999999)}"


def shift_window(day: int, shift: int):
    """Return (shift_start_dt, shift_end_dt) for a given day and shift index."""
    s = SHIFTS[shift]
    base = START_DATE + timedelta(days=day)
    start = base.replace(hour=s["start_h"], minute=0, second=0, microsecond=0)
    end   = base.replace(hour=s["end_h"],   minute=0, second=0, microsecond=0)
    return start, end


def get_drift_bias(drift: dict, day: int, shift: int, event_pct: float):
    """
    Return (torque_bias_nm, angle_missing) for an event at event_pct
    through the shift, given a drift definition.
    Returns (0.0, False) if this event is outside the drift window.
    """
    if drift["day"] != day or drift["shift"] != shift:
        return 0.0, False
    if not (drift["start_pct"] <= event_pct <= drift["end_pct"]):
        return 0.0, False

    window_pct = (event_pct - drift["start_pct"]) / (drift["end_pct"] - drift["start_pct"])
    bias = drift["bias_start"] + window_pct * (drift["bias_end"] - drift["bias_start"])

    if drift["direction"] == "angle":
        return 0.0, True   # torque fine, angle drops out
    return bias, False


def is_comm_error(drift: dict, day: int, shift: int, event_pct: float):
    if not drift.get("comm_error_near_peak"):
        return False
    if drift["day"] != day or drift["shift"] != shift:
        return False
    # Fire comm error only in the last 15% of the drift window
    peak_zone_start = drift["end_pct"] - 0.15
    return peak_zone_start <= event_pct <= drift["end_pct"] and random.random() < 0.15


def compute_result(actual, target, tol, angle_req, actual_angle, tool_error):
    if tool_error:
        return "ToolError", ["tool_error"]
    violations = []
    if actual < target - tol:
        violations.append("under_torque")
    if actual > target + tol:
        violations.append("over_torque")
    if angle_req is not None and actual_angle is None:
        violations.append("angle_incomplete")

    if not violations:
        return "OK", []
    if "under_torque" in violations:
        return "UnderTorque", violations
    if "over_torque" in violations:
        return "OverTorque", violations
    if "angle_incomplete" in violations:
        return "AngleMissing", violations
    return "OK", []


# ─── Main generation loop ─────────────────────────────────────────────────────

def generate_events(n_per_shift=EVENTS_PER_SHIFT):
    events = []
    event_counter = 1

    for day in range(3):
        for shift_idx, shift_def in enumerate(SHIFTS):
            shift_start, shift_end = shift_window(day, shift_idx)
            shift_duration = (shift_end - shift_start).total_seconds()

            current_ts = shift_start + timedelta(seconds=random.randint(30, 90))

            for i in range(n_per_shift):
                event_pct = i / n_per_shift  # progress through shift

                # Pick joint and its specs
                joint_name = random.choice(list(JOINTS.keys()))
                spec = JOINTS[joint_name]
                tool = JOINT_TOOL[joint_name]

                # Check if this event falls inside a drift window for this tool
                torque_bias = 0.0
                angle_missing_forced = False
                tool_error = False

                for drift in DRIFT_WINDOWS:
                    if drift["tool"] == tool and joint_name in drift["affected_joints"]:
                        bias, ang_miss = get_drift_bias(drift, day, shift_idx, event_pct)
                        torque_bias += bias
                        if ang_miss:
                            angle_missing_forced = True
                        if is_comm_error(drift, day, shift_idx, event_pct):
                            tool_error = True

                # Compute actual torque — gaussian noise + drift bias
                noise = random.gauss(0, spec["tol"] * 0.20)
                actual_torque = round(spec["target"] + noise + torque_bias, 1)

                # Baseline process noise violation — randomly breach tolerance
                # regardless of drift (simulates operator or process variation)
                if torque_bias == 0.0 and not angle_missing_forced and not tool_error:
                    if random.random() < BASELINE_VIOLATION_RATE:
                        direction = random.choice(["over", "under"])
                        overshoot = random.uniform(spec["tol"] * 1.1, spec["tol"] * 2.2)
                        actual_torque = round(
                            spec["target"] + (overshoot if direction == "over" else -overshoot), 1
                        )

                # Angle measurement
                angle_req = spec["angle"]
                if angle_req is not None and not angle_missing_forced:
                    angle_noise = random.gauss(0, 1.5)
                    actual_angle = round(angle_req + angle_noise, 1)
                else:
                    actual_angle = None if (angle_req is not None) else None

                # Compute result
                result, violations = compute_result(
                    actual_torque, spec["target"], spec["tol"],
                    angle_req, actual_angle, tool_error
                )

                ts_str = current_ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

                events.append({
                    "event_id": f"EVT-{event_counter:06d}",
                    "timestamp": ts_str,
                    "vehicle_model": random.choice(VEHICLE_MODELS),
                    "vin": vin(),
                    "station": spec["station"],
                    "joint": joint_name,
                    "tool_id": tool,
                    "target_torque_nm": spec["target"],
                    "tolerance_nm": spec["tol"],
                    "actual_torque_nm": actual_torque,
                    "angle_required": angle_req if angle_req is not None else "",
                    "actual_angle_deg": actual_angle if actual_angle is not None else "",
                    "sop_id": spec["sop"],
                    "sop_chunks_used": "[]",
                    "result": result,
                    "violations": json.dumps(violations),
                    "tool_error": "TOOL_COMM_ERROR" if tool_error else "",
                })

                event_counter += 1

                # Advance timestamp — variable cycle time + some inter-event idle
                cycle_lo, cycle_hi = spec["cycle"]
                advance = random.randint(cycle_lo, cycle_hi) + random.randint(5, 20)
                current_ts += timedelta(seconds=advance)

                # Stay within shift bounds (clamp with a small buffer)
                max_ts = shift_end - timedelta(seconds=30)
                if current_ts > max_ts:
                    current_ts = max_ts

            # Shift handover gap — next shift starts after a break
            # (handled naturally by shift_window using absolute times)

    return events


# ─── Past incidents — expanded ────────────────────────────────────────────────

PAST_INCIDENTS = [
    {"content": "DC_GUN on POWERTRAIN_ST-05 produced over-torque readings on WHEEL_LUG_NUT_RR across 12 consecutive vehicles. Root cause: worn torque-limiting clutch. Corrective action: clutch replaced, tool recalibrated, 50-cycle verification run performed."},
    {"content": "PNEUMATIC_TQ pressure drop on CHASSIS_ST-14 caused under-torque on TRANSMISSION_MOUNT_BOLT for 8 events. Root cause: blocked air supply filter. Action: filter replaced, air pressure restored, affected vehicles flagged for re-torque inspection."},
    {"content": "ELECTRIC_ANGLE_GUN angle sensor intermittent fault on ENGINE_MOUNT_FRONT_LEFT. Angle measurements missing for 6 events across one shift. Root cause: loose encoder connector. Action: connector reseated, sensor re-zeroed, all angle-required fasteners re-verified."},
    {"content": "MANUAL_WRENCH operator on FINAL_ASSY_ST-22 applied under-torque on BRAKE_CALIPER_BOLT. Root cause: operator fatigue late in shift, torque setting slipped. Action: operator retrained, torque wrench click-point audited, shift-end spot-check procedure added."},
    {"content": "Suspension arm bolt over-torque detected on CHASSIS_ST-14 during final audit. DC_GUN calibration had drifted +6 Nm. Affected vehicles recalled for inspection. Corrective action: daily calibration check mandated for DC_GUN."},
    {"content": "Engine mount front right bolts returned under-torque on 3 consecutive EV-Q units. Investigation found incorrect SOP revision loaded in MES — old tolerance ±8 Nm instead of ±5 Nm. SOP corrected, MES updated."},
    {"content": "TOOL_COMM_ERROR storm on DC_GUN during peak production. 4 events returned no torque reading. Root cause: intermittent CAN bus fault. Action: cable harness replaced, communication verified at 100 cycles."},
    {"content": "Wheel lug nut FL over-torque on Truck-T model. Target 120 Nm, actual 134 Nm. Bolt yield detected. Root cause: wrong torque table loaded for Truck-T variant. Bolt replaced, SOP vehicle-model mapping audited across all stations."},
    {"content": "Steering column bolt ANGLE_MISSING for 5 Sedan-X units at INTERIOR_ST-08. Operator bypassed angle step due to MES screen freeze. Action: MES stability patch applied, angle step made mandatory with hardware interlock."},
    {"content": "Seat frame rear bolts under-torque on 2 Hatch-A units. PNEUMATIC_TQ air supply pressure dropped during compressor maintenance window. Maintenance scheduling updated to avoid overlap with production shifts."},
    {"content": "ENGINE_MOUNT_REAR_RIGHT under-torque cluster — 4 events in 20 minutes. PNEUMATIC_TQ tool battery low indicator ignored by operator. Tool auto-shutoff triggered mid-tighten. Action: low-battery alert added to station HMI."},
    {"content": "Over-torque on BATTERY_HOLD_DOWN bolts on EV-Q. Actual torque 78 Nm vs target 65 Nm. Root cause: operator used wrong gun preset for EV variant. Preset selection now validated against VIN vehicle type in MES before tool enables."},
    {"content": "SUSPENSION_ARM_BOLT_F under-torque discovered in end-of-line audit on 6 SUV-Z units. DC_GUN torque output degraded after dropping. Tool failed post-drop calibration check. All units reworked."},
    {"content": "Angle measurement out-of-range on ENGINE_MOUNT_REAR_LEFT (actual 14° vs required 30°). Operator started angle phase before pre-torque fully applied. Sequence lock implemented in tool controller firmware."},
    {"content": "TRANSMISSION_MOUNT_BOLT angle incomplete across full Truck-T build run (22 units). MES angle verification step skipped due to software config error after server restart. Patch deployed, affected units re-inspected."},
]


# ─── Write outputs ─────────────────────────────────────────────────────────────

def main():
    import os
    out_dir = "torque-assistant-v2/data"
    os.makedirs(out_dir, exist_ok=True)

    events = generate_events()

    # --- CSV ---
    fieldnames = [
        "event_id", "timestamp", "vehicle_model", "vin", "station", "joint",
        "tool_id", "target_torque_nm", "tolerance_nm", "actual_torque_nm",
        "angle_required", "actual_angle_deg", "sop_id", "sop_chunks_used",
        "result", "violations", "tool_error",
    ]
    csv_path = f"{out_dir}/torque_events.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)
    print(f"[WRITE] {csv_path}  ({len(events)} events)")

    # --- JSON (mirror of CSV) ---
    json_path = f"{out_dir}/torque_events.json"
    with open(json_path, "w") as f:
        json.dump(events, f, indent=2)
    print(f"[WRITE] {json_path}")

    # --- Past incidents ---
    inc_path = f"{out_dir}/past_incidents.json"
    with open(inc_path, "w") as f:
        json.dump(PAST_INCIDENTS, f, indent=2)
    print(f"[WRITE] {inc_path}  ({len(PAST_INCIDENTS)} incidents)")

    # --- Quick stats ---
    import collections
    results = collections.Counter(e["result"] for e in events)
    tools_in_drift = collections.Counter(
        e["tool_id"] for e in events if e["result"] != "OK"
    )
    print("\n=== Result distribution ===")
    for k, v in sorted(results.items()):
        print(f"  {k}: {v}")
    print("\n=== Violations by tool ===")
    for k, v in tools_in_drift.most_common():
        print(f"  {k}: {v}")

    # Verify timestamp variance
    import statistics
    from datetime import datetime
    ts_list = [datetime.fromisoformat(e["timestamp"].replace("Z","")) for e in events]
    diffs = [(ts_list[i+1]-ts_list[i]).total_seconds() for i in range(len(ts_list)-1) if (ts_list[i+1]-ts_list[i]).total_seconds() < 600]
    print(f"\n=== Timestamp gaps (within-shift, seconds) ===")
    print(f"  mean={statistics.mean(diffs):.1f}  std={statistics.stdev(diffs):.1f}  min={min(diffs):.0f}  max={max(diffs):.0f}")


if __name__ == "__main__":
    main()
