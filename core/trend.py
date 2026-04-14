"""
trend.py — Phase 3: SPC and trend detection

Pure computational analysis — no LLM calls. Sits before the agent node
in the pipeline and populates state.trend_context with a structured
summary of tool health and deviation patterns.

Two analyses:
  1. SPC (Cpk) — rolling process capability per tool+joint, computed from
     the last N readings. Catches calibration drift before violations occur.
  2. Deviation pattern — consecutive non-OK results on the same tool across
     any joint. Detects systemic tool failure.

Uses the full event dataset (loaded at startup) and simulates real-time
processing by only looking at events before the current one.
"""

import logging
import math
from collections import Counter

import numpy as np
import pandas as pd

logger = logging.getLogger("torque.trend")

# ── Config ────────────────────────────────────────────────────────────────────

# Minimum samples needed for Cpk calculation. Below this, SPC is not reported.
MIN_SAMPLES_CPK = 15

# Window size for Cpk — uses the last N readings on the same tool+joint combo.
CPK_WINDOW = 25

# Window size for pattern detection — last N events on the same tool (any joint).
PATTERN_WINDOW = 15

# Threshold: how many non-OK in the pattern window triggers a trend alert.
PATTERN_THRESHOLD = 3

# Cpk warning threshold. Automotive standard is 1.33 for capable processes.
CPK_WARN = 1.33
CPK_CRITICAL = 1.0


# ── TrendDetector ─────────────────────────────────────────────────────────────

class TrendDetector:
    """
    Initialized with the full event dataframe at startup.

    For each event, analyze() looks at all prior events on the same tool
    to compute SPC metrics and detect deviation patterns. It returns a
    human-readable string for the agent's trend_context field.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.df["deviation"] = self.df["actual_torque_nm"] - self.df["target_torque_nm"]
        # Pre-build an index of event_id -> row position for fast lookup
        self._event_idx = {eid: i for i, eid in enumerate(self.df["event_id"])}

    def analyze(self, event_id: str, tool_id: str, joint: str,
                target_nm: float, tolerance_nm: float) -> str:
        """
        Analyze tool health and deviation patterns for the current event.

        Returns a formatted string for the agent prompt. If no issues are
        found, returns a brief "no trends" message. If patterns or SPC
        warnings are detected, returns a detailed alert.
        """
        idx = self._event_idx.get(event_id)
        if idx is None or idx < 5:
            return "Insufficient history — this is one of the first events in the dataset."

        # All events BEFORE this one on the same tool (simulating real-time)
        prior_all = self.df.iloc[:idx]
        prior_tool = prior_all[prior_all["tool_id"] == tool_id]

        if len(prior_tool) < 5:
            return f"Insufficient history for {tool_id} — fewer than 5 prior events."

        # ── 1. Deviation pattern (tool-level, any joint) ──────────────────
        pattern = self._detect_pattern(prior_tool, tool_id)

        # ── 2. Cpk (tool+joint combo) ────────────────────────────────────
        prior_tool_joint = prior_tool[prior_tool["joint"] == joint]
        cpk_info = self._compute_cpk(prior_tool_joint, target_nm, tolerance_nm, tool_id, joint)

        # ── 3. Mean shift detection (tool-level) ─────────────────────────
        shift = self._detect_mean_shift(prior_tool, tool_id)

        # ── Format output ─────────────────────────────────────────────────
        return self._format(tool_id, joint, pattern, cpk_info, shift)

    # ── Pattern detection ─────────────────────────────────────────────────────

    def _detect_pattern(self, prior_tool: pd.DataFrame, tool_id: str) -> dict:
        """
        Check the last PATTERN_WINDOW events on this tool for consecutive
        deviations. Returns a dict with the analysis.
        """
        recent = prior_tool.tail(PATTERN_WINDOW)
        total = len(recent)
        non_ok = recent[recent["result"] != "OK"]
        non_ok_count = len(non_ok)

        result = {
            "detected": non_ok_count >= PATTERN_THRESHOLD,
            "non_ok_count": non_ok_count,
            "window_size": total,
            "affected_joints": [],
            "drift_direction": None,
            "severity_note": "",
        }

        if not result["detected"]:
            return result

        # Which joints are affected?
        result["affected_joints"] = sorted(non_ok["joint"].unique().tolist())

        # Drift direction — are deviations predominantly positive or negative?
        recent_devs = recent["deviation"].values
        mean_dev = float(np.mean(recent_devs))
        if mean_dev > 0.5:
            result["drift_direction"] = "OVER (positive drift)"
        elif mean_dev < -0.5:
            result["drift_direction"] = "UNDER (negative drift)"
        else:
            result["drift_direction"] = "mixed"

        # Is it accelerating? Compare first half vs second half
        if total >= 6:
            first_half = recent_devs[:total // 2]
            second_half = recent_devs[total // 2:]
            first_mean = float(np.mean(np.abs(first_half)))
            second_mean = float(np.mean(np.abs(second_half)))
            if second_mean > first_mean * 1.3:
                result["severity_note"] = "Accelerating — recent deviations are larger than earlier ones."
            elif second_mean < first_mean * 0.7:
                result["severity_note"] = "Decelerating — deviations may be recovering."

        return result

    # ── SPC: Cpk ──────────────────────────────────────────────────────────────

    def _compute_cpk(self, prior_tool_joint: pd.DataFrame,
                     target_nm: float, tolerance_nm: float,
                     tool_id: str, joint: str) -> dict:
        """
        Compute Cpk on the last CPK_WINDOW readings for this tool+joint combo.

        Cpk = min((USL - μ) / (3σ), (μ - LSL) / (3σ))

        Automotive standard: Cpk >= 1.33 for capable processes.
        """
        result = {
            "computed": False,
            "cpk": None,
            "cp": None,
            "n_samples": 0,
            "mean_deviation": 0.0,
            "sigma": 0.0,
            "status": "",
        }

        if len(prior_tool_joint) < MIN_SAMPLES_CPK:
            result["status"] = f"Insufficient data ({len(prior_tool_joint)}/{MIN_SAMPLES_CPK} samples needed)"
            return result

        # Use last CPK_WINDOW readings
        readings = prior_tool_joint["actual_torque_nm"].tail(CPK_WINDOW).values
        n = len(readings)

        usl = target_nm + tolerance_nm
        lsl = target_nm - tolerance_nm
        mu = float(np.mean(readings))
        sigma = float(np.std(readings, ddof=1))

        if sigma < 1e-9:
            result["status"] = "Zero variance — all readings identical"
            result["computed"] = True
            result["n_samples"] = n
            result["cpk"] = 99.0  # effectively perfect
            return result

        cp = (usl - lsl) / (6 * sigma)
        cpk = min((usl - mu) / (3 * sigma), (mu - lsl) / (3 * sigma))

        result["computed"] = True
        result["cpk"] = round(cpk, 2)
        result["cp"] = round(cp, 2)
        result["n_samples"] = n
        result["mean_deviation"] = round(mu - target_nm, 2)
        result["sigma"] = round(sigma, 2)

        if cpk >= CPK_WARN:
            result["status"] = "Capable"
        elif cpk >= CPK_CRITICAL:
            result["status"] = "Warning — approaching capability limit"
        else:
            result["status"] = "NOT CAPABLE — process out of control"

        return result

    # ── Mean shift detection ──────────────────────────────────────────────────

    def _detect_mean_shift(self, prior_tool: pd.DataFrame, tool_id: str) -> dict:
        """
        Compare mean deviation of the last 10 events to the previous 10.
        Detects gradual drift even when individual events are still within spec.
        """
        result = {
            "detected": False,
            "recent_mean": 0.0,
            "baseline_mean": 0.0,
            "shift_nm": 0.0,
        }

        if len(prior_tool) < 20:
            return result

        recent_10 = prior_tool.tail(10)["deviation"].values
        baseline_10 = prior_tool.iloc[-20:-10]["deviation"].values

        recent_mean = float(np.mean(recent_10))
        baseline_mean = float(np.mean(baseline_10))
        shift = recent_mean - baseline_mean

        result["recent_mean"] = round(recent_mean, 2)
        result["baseline_mean"] = round(baseline_mean, 2)
        result["shift_nm"] = round(shift, 2)

        # Flag if the mean has shifted by more than 2 Nm
        # (a meaningful shift regardless of tolerance window)
        if abs(shift) > 2.0:
            result["detected"] = True

        return result

    # ── Formatter ─────────────────────────────────────────────────────────────

    def _format(self, tool_id: str, joint: str,
                pattern: dict, cpk_info: dict, shift: dict) -> str:
        """
        Produce the trend_context string for the agent prompt.

        If no issues detected, returns a brief all-clear.
        If issues found, returns a structured alert.
        """
        has_pattern = pattern["detected"]
        has_shift = shift["detected"]
        has_cpk_warn = cpk_info["computed"] and cpk_info["cpk"] is not None and cpk_info["cpk"] < CPK_WARN

        if not has_pattern and not has_shift and not has_cpk_warn:
            # All clear
            cpk_str = ""
            if cpk_info["computed"] and cpk_info["cpk"] is not None:
                cpk_str = f" Cpk={cpk_info['cpk']:.2f} (n={cpk_info['n_samples']})."
            return f"No active trends detected for {tool_id}.{cpk_str}"

        # ── Build alert ───────────────────────────────────────────────────
        lines = ["TREND ALERT:"]

        # Pattern
        if has_pattern:
            lines.append(f"  Tool: {tool_id}")
            lines.append(f"  Pattern: {pattern['non_ok_count']} non-OK events in last "
                         f"{pattern['window_size']} readings on this tool")
            if pattern["drift_direction"]:
                lines.append(f"  Drift direction: {pattern['drift_direction']}")
            if pattern["affected_joints"]:
                lines.append(f"  Affected joints: {', '.join(pattern['affected_joints'])}")
            if pattern["severity_note"]:
                lines.append(f"  Note: {pattern['severity_note']}")

        # Cpk
        if cpk_info["computed"] and cpk_info["cpk"] is not None:
            lines.append(f"  SPC ({tool_id} + {joint}):")
            lines.append(f"    Cpk = {cpk_info['cpk']:.2f}  |  Cp = {cpk_info['cp']:.2f}  |  "
                         f"n = {cpk_info['n_samples']}  |  Status: {cpk_info['status']}")
            lines.append(f"    Mean deviation: {cpk_info['mean_deviation']:+.2f} Nm  |  "
                         f"Sigma: {cpk_info['sigma']:.2f} Nm")

        # Mean shift
        if has_shift:
            direction = "positive" if shift["shift_nm"] > 0 else "negative"
            lines.append(f"  Mean shift detected on {tool_id}:")
            lines.append(f"    Baseline mean deviation: {shift['baseline_mean']:+.2f} Nm  →  "
                         f"Recent mean deviation: {shift['recent_mean']:+.2f} Nm")
            lines.append(f"    Shift: {shift['shift_nm']:+.2f} Nm ({direction})")

        return "\n".join(lines)