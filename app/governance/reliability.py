"""
Agent Governance Toolkit - Reliability and Anomaly Detection

This module implements reliability controls including anomaly detection,
circuit breakers, and behavioral quarantine for agent containment.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class AnomalyAction(Enum):
    ALLOW = "ALLOW"
    THROTTLE = "THROTTLE"
    QUARANTINE = "QUARANTINE"
    CIRCUIT_BREAK = "CIRCUIT_BREAK"


@dataclass
class ReliabilityEvent:
    timestamp: datetime
    agent_name: str
    event_type: str
    details: Dict[str, Any]


@dataclass
class AnomalyResult:
    detected: bool
    anomaly_type: str
    action: AnomalyAction
    message: str
    threshold: int
    actual_count: int
    details: Dict[str, Any]


class ReliabilityMonitor:
    """Detects and contains suspicious or failure-prone agent behavior"""

    def __init__(self, policy_dir: str | Path | None = None):
        self.policy_dir = Path(policy_dir) if policy_dir is not None else Path(__file__).resolve().parents[1] / "policies"
        self.config = self._load_config()

        # Tracking structures
        self.event_history: Dict[str, List[ReliabilityEvent]] = defaultdict(list)
        self.denial_counts: Dict[str, List[datetime]] = defaultdict(list)
        self.failure_counts: Dict[str, List[datetime]] = defaultdict(list)
        self.tool_call_counts: Dict[str, List[datetime]] = defaultdict(list)
        self.quarantined_agents: Dict[str, datetime] = {}
        self.circuit_states: Dict[str, CircuitState] = {}
        self.circuit_failure_counts: Dict[str, int] = defaultdict(int)
        self.circuit_opened_at: Dict[str, datetime] = {}

    def _load_config(self) -> Dict[str, Any]:
        """Load reliability policies"""
        reliability_path = self.policy_dir / "reliability.yaml"
        if reliability_path.exists():
            with open(reliability_path) as f:
                return yaml.safe_load(f)
        return {}

    def record_denial(self, agent_name: str, reason: str) -> AnomalyResult:
        """Record a policy denial and check for anomalies"""
        now = datetime.now()
        self.denial_counts[agent_name].append(now)

        # Record event
        event = ReliabilityEvent(
            timestamp=now,
            agent_name=agent_name,
            event_type="denial",
            details={"reason": reason}
        )
        self.event_history[agent_name].append(event)

        # Check repeated denials threshold
        anomaly_config = self.config.get('anomaly_detection', {}).get('repeated_denials', {})
        threshold = anomaly_config.get('threshold', 3)
        window_seconds = anomaly_config.get('window_seconds', 60)

        # Count recent denials within window
        cutoff = now - timedelta(seconds=window_seconds)
        recent_denials = [d for d in self.denial_counts[agent_name] if d > cutoff]
        self.denial_counts[agent_name] = recent_denials  # Clean old entries

        if len(recent_denials) >= threshold:
            action_str = anomaly_config.get('action', 'QUARANTINE')
            action = AnomalyAction[action_str]

            if action == AnomalyAction.QUARANTINE:
                self._quarantine_agent(agent_name)

            return AnomalyResult(
                detected=True,
                anomaly_type="repeated_denials",
                action=action,
                message=anomaly_config.get('message', 'Repeated denial threshold exceeded'),
                threshold=threshold,
                actual_count=len(recent_denials),
                details={
                    "agent": agent_name,
                    "window_seconds": window_seconds,
                    "reason": reason
                }
            )

        return AnomalyResult(
            detected=False,
            anomaly_type="repeated_denials",
            action=AnomalyAction.ALLOW,
            message="Within normal threshold",
            threshold=threshold,
            actual_count=len(recent_denials),
            details={"agent": agent_name}
        )

    def record_tool_call(self, agent_name: str, tool_name: str) -> AnomalyResult:
        """Record a tool call and check for rapid invocation patterns"""
        now = datetime.now()
        self.tool_call_counts[agent_name].append(now)

        # Check rapid tool calls threshold
        anomaly_config = self.config.get('anomaly_detection', {}).get('rapid_tool_calls', {})
        threshold = anomaly_config.get('threshold', 10)
        window_seconds = anomaly_config.get('window_seconds', 5)

        cutoff = now - timedelta(seconds=window_seconds)
        recent_calls = [d for d in self.tool_call_counts[agent_name] if d > cutoff]
        self.tool_call_counts[agent_name] = recent_calls

        if len(recent_calls) >= threshold:
            action_str = anomaly_config.get('action', 'THROTTLE')
            action = AnomalyAction[action_str]

            return AnomalyResult(
                detected=True,
                anomaly_type="rapid_tool_calls",
                action=action,
                message=anomaly_config.get('message', 'Too many tool calls too quickly'),
                threshold=threshold,
                actual_count=len(recent_calls),
                details={
                    "agent": agent_name,
                    "tool": tool_name,
                    "window_seconds": window_seconds
                }
            )

        return AnomalyResult(
            detected=False,
            anomaly_type="rapid_tool_calls",
            action=AnomalyAction.ALLOW,
            message="Within normal threshold",
            threshold=threshold,
            actual_count=len(recent_calls),
            details={"agent": agent_name}
        )

    def record_failure(self, agent_name: str, failure_reason: str) -> AnomalyResult:
        """Record a failure and check circuit breaker"""
        now = datetime.now()
        self.failure_counts[agent_name].append(now)

        # Record event
        event = ReliabilityEvent(
            timestamp=now,
            agent_name=agent_name,
            event_type="failure",
            details={"reason": failure_reason}
        )
        self.event_history[agent_name].append(event)

        # Check repeated failures threshold
        anomaly_config = self.config.get('anomaly_detection', {}).get('repeated_failures', {})
        threshold = anomaly_config.get('threshold', 5)
        window_seconds = anomaly_config.get('window_seconds', 120)

        cutoff = now - timedelta(seconds=window_seconds)
        recent_failures = [d for d in self.failure_counts[agent_name] if d > cutoff]
        self.failure_counts[agent_name] = recent_failures

        if len(recent_failures) >= threshold:
            action_str = anomaly_config.get('action', 'CIRCUIT_BREAK')
            action = AnomalyAction[action_str]

            if action == AnomalyAction.CIRCUIT_BREAK:
                self._open_circuit(agent_name)

            return AnomalyResult(
                detected=True,
                anomaly_type="repeated_failures",
                action=action,
                message=anomaly_config.get('message', 'Repeated failures - opening circuit breaker'),
                threshold=threshold,
                actual_count=len(recent_failures),
                details={
                    "agent": agent_name,
                    "window_seconds": window_seconds,
                    "reason": failure_reason
                }
            )

        return AnomalyResult(
            detected=False,
            anomaly_type="repeated_failures",
            action=AnomalyAction.ALLOW,
            message="Within normal threshold",
            threshold=threshold,
            actual_count=len(recent_failures),
            details={"agent": agent_name}
        )

    def _quarantine_agent(self, agent_name: str):
        """Place agent in quarantine"""
        self.quarantined_agents[agent_name] = datetime.now()

    def is_quarantined(self, agent_name: str) -> bool:
        """Check if agent is currently quarantined"""
        if agent_name not in self.quarantined_agents:
            return False

        quarantine_config = self.config.get('quarantine', {})
        duration_seconds = quarantine_config.get('duration_seconds', 600)

        quarantined_at = self.quarantined_agents[agent_name]
        elapsed = (datetime.now() - quarantined_at).total_seconds()

        if elapsed > duration_seconds:
            # Quarantine expired
            del self.quarantined_agents[agent_name]
            return False

        return True

    def _open_circuit(self, agent_name: str):
        """Open circuit breaker for agent"""
        self.circuit_states[agent_name] = CircuitState.OPEN
        self.circuit_opened_at[agent_name] = datetime.now()
        self.circuit_failure_counts[agent_name] = 0

    def check_circuit_breaker(self, agent_name: str) -> tuple[bool, str]:
        """Check if circuit breaker allows operation"""
        if agent_name not in self.circuit_states:
            self.circuit_states[agent_name] = CircuitState.CLOSED
            return True, "Circuit closed - normal operation"

        state = self.circuit_states[agent_name]

        if state == CircuitState.CLOSED:
            return True, "Circuit closed - normal operation"

        if state == CircuitState.OPEN:
            # Check if enough time has passed to try half-open
            circuit_config = self.config.get('circuit_breaker', {})
            half_open_after = circuit_config.get('half_open_after_seconds', 60)

            opened_at = self.circuit_opened_at.get(agent_name, datetime.now())
            elapsed = (datetime.now() - opened_at).total_seconds()

            if elapsed > half_open_after:
                self.circuit_states[agent_name] = CircuitState.HALF_OPEN
                return True, "Circuit half-open - testing recovery"

            return False, "Circuit breaker is OPEN - requests denied"

        if state == CircuitState.HALF_OPEN:
            return True, "Circuit half-open - limited requests allowed"

        return True, "Unknown state"

    def get_agent_status(self, agent_name: str) -> Dict[str, Any]:
        """Get comprehensive status for an agent"""
        now = datetime.now()

        # Count recent events
        recent_denials = len([d for d in self.denial_counts[agent_name]
                              if (now - d).total_seconds() < 60])
        recent_failures = len([d for d in self.failure_counts[agent_name]
                               if (now - d).total_seconds() < 120])
        recent_tool_calls = len([d for d in self.tool_call_counts[agent_name]
                                 if (now - d).total_seconds() < 5])

        return {
            "agent": agent_name,
            "quarantined": self.is_quarantined(agent_name),
            "circuit_state": self.circuit_states.get(agent_name, CircuitState.CLOSED).value,
            "recent_denials_60s": recent_denials,
            "recent_failures_120s": recent_failures,
            "recent_tool_calls_5s": recent_tool_calls,
            "total_events": len(self.event_history[agent_name])
        }
