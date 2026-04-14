from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml
from agent_framework import AgentContext, AgentMiddleware, AgentResponse, FunctionInvocationContext, FunctionMiddleware, Message, MiddlewareTermination
from agentmesh import AgentMeshClient
from agentmesh.governance import AuditLog
from agent_sre.anomaly import AnomalyAlert, AnomalyDetector, AnomalySeverity, DetectorConfig
from agent_os.cli.mcp_scan import SecurityFinding, scan_config


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _path_text(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/")


def _pattern_matches(value: str, pattern: str) -> bool:
    normalized_value = value.replace("\\", "/")
    normalized_pattern = pattern.replace("\\", "/")
    if fnmatch(normalized_value, normalized_pattern):
        return True
    escaped = re.escape(normalized_pattern).replace(r"\*", ".*")
    return re.search(escaped, normalized_value, flags=re.IGNORECASE) is not None


@dataclass
class GovernanceDecision:
    allowed: bool
    reason: str
    matched_rule: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrustDecision:
    allowed: bool
    agent_name: str
    trust_level: str
    trust_score: int
    identity_verified: bool
    reason: str
    did: str | None = None


TRUST_SCORE_MAX = 1000
TRUST_SCORE_DEFAULT = 500
TRUST_SCORE_FLOOR = 100
TRUST_WARNING_THRESHOLD = 500
TRUST_REVOCATION_THRESHOLD = 300
TRUST_DECAY_POINTS_PER_HOUR = 2.0
TRUST_EMA_ALPHA = 0.2
TRUST_DIMENSION_WEIGHTS = {
    "policy_compliance": 0.25,
    "security_posture": 0.25,
    "output_quality": 0.20,
    "resource_efficiency": 0.15,
    "collaboration_health": 0.15,
}
TRUST_TIER_THRESHOLDS = [
    (900, "verified_partner"),
    (700, "trusted"),
    (500, "standard"),
    (300, "probationary"),
    (0, "untrusted"),
]


@dataclass
class TrustState:
    agent_name: str
    total_score: int
    tier: str
    identity_verified: bool
    dimensions: dict[str, float]
    event_count: int = 0
    previous_score: int | None = None
    score_change: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_positive_signal_at: str | None = None
    last_event: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_score": self.total_score,
            "tier": self.tier,
            "identity_verified": self.identity_verified,
            "dimensions": self.dimensions,
            "event_count": self.event_count,
            "previous_score": self.previous_score,
            "score_change": self.score_change,
            "last_updated": self.last_updated,
            "last_positive_signal_at": self.last_positive_signal_at,
            "last_event": self.last_event,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrustState":
        dimensions = {
            name: float(payload.get("dimensions", {}).get(name, 50.0))
            for name in TRUST_DIMENSION_WEIGHTS
        }
        return cls(
            agent_name=str(payload.get("agent_name", "unknown")),
            total_score=int(payload.get("total_score", TRUST_SCORE_DEFAULT)),
            tier=str(payload.get("tier", "standard")),
            identity_verified=bool(payload.get("identity_verified", False)),
            dimensions=dimensions,
            event_count=int(payload.get("event_count", 0)),
            previous_score=payload.get("previous_score"),
            score_change=int(payload.get("score_change", 0)),
            last_updated=str(payload.get("last_updated", datetime.now(timezone.utc).isoformat())),
            last_positive_signal_at=payload.get("last_positive_signal_at"),
            last_event=dict(payload.get("last_event", {})),
        )


class ControlPlanePolicy:
    def __init__(self, policy_path: Path):
        payload = _read_yaml(policy_path)
        policies = payload.get("policies", {})
        self.file_access_rules = policies.get("file_access", [])
        self.command_rules = policies.get("command_execution", [])
        self.tool_rules = policies.get("tool_restrictions", [])

    def check_prompt(self, agent_name: str, text: str) -> GovernanceDecision:
        for rule in self.command_rules:
            for pattern in rule.get("patterns", []):
                if _pattern_matches(text, pattern):
                    return GovernanceDecision(
                        allowed=rule.get("action", "ALLOW") == "ALLOW",
                        reason=rule.get("message") or rule.get("description", "Command policy matched"),
                        matched_rule=rule.get("rule"),
                        details={"kind": "command", "pattern": pattern, "agent": agent_name},
                    )
        for rule in self.file_access_rules:
            for pattern in rule.get("patterns", []):
                if _pattern_matches(text, pattern):
                    return GovernanceDecision(
                        allowed=rule.get("action", "ALLOW") == "ALLOW",
                        reason=rule.get("message") or rule.get("description", "File policy matched"),
                        matched_rule=rule.get("rule"),
                        details={"kind": "file_access", "pattern": pattern, "agent": agent_name},
                    )
        return GovernanceDecision(True, "No blocking prompt policy matched")

    def check_file_access(self, path: str | Path) -> GovernanceDecision:
        normalized = _path_text(path)
        for rule in self.file_access_rules:
            for pattern in rule.get("patterns", []):
                if _pattern_matches(normalized, pattern):
                    return GovernanceDecision(
                        allowed=rule.get("action", "ALLOW") == "ALLOW",
                        reason=rule.get("message") or rule.get("description", "File policy matched"),
                        matched_rule=rule.get("rule"),
                        details={"kind": "file_access", "path": normalized, "pattern": pattern},
                    )
        return GovernanceDecision(True, f"No file rule blocked {normalized}")

    def check_command(self, command: str) -> GovernanceDecision:
        for rule in self.command_rules:
            for pattern in rule.get("patterns", []):
                if _pattern_matches(command, pattern):
                    return GovernanceDecision(
                        allowed=rule.get("action", "ALLOW") == "ALLOW",
                        reason=rule.get("message") or rule.get("description", "Command policy matched"),
                        matched_rule=rule.get("rule"),
                        details={"kind": "command_execution", "command": command, "pattern": pattern},
                    )
        return GovernanceDecision(True, f"No command rule blocked {command}")

    def check_tool(self, agent_name: str, tool_name: str) -> GovernanceDecision:
        for rule in self.tool_rules:
            if rule.get("agent") != agent_name:
                continue
            denied = set(rule.get("denied_tools", []))
            allowed = set(rule.get("allowed_tools", []))
            if tool_name in denied:
                return GovernanceDecision(False, f"Tool '{tool_name}' is denied for {agent_name}", rule.get("rule"))
            if allowed and tool_name not in allowed:
                return GovernanceDecision(False, f"Tool '{tool_name}' is outside the allow list for {agent_name}", rule.get("rule"))
            return GovernanceDecision(True, f"Tool '{tool_name}' is allowed for {agent_name}", rule.get("rule"))
        return GovernanceDecision(True, f"No tool restriction matched for {agent_name}")


class TrustRegistry:
    TRUST_ORDER = {
        "low": 0,
        "medium": 1,
        "high": 2,
        "untrusted": 0,
        "probationary": 1,
        "standard": 2,
        "trusted": 3,
        "verified_partner": 4,
    }

    def __init__(self, trust_path: Path, audit_log: AuditLog, storage_path: Path | None = None):
        payload = _read_yaml(trust_path)
        self.trust_levels = payload.get("trust_levels", {})
        self.agent_trust = payload.get("agent_trust", {})
        self.delegation_rules = payload.get("delegation", {}).get("rules", [])
        self.audit_log = audit_log
        self.storage_path = storage_path or trust_path.parent.parent / "artifacts" / "trust-state.json"
        self.state = self._load_state()
        self.clients = {
            agent_name: AgentMeshClient(
                agent_name,
                capabilities=self._capabilities_for(agent_name),
                trust_config={"initial_score": self._state_for(agent_name).total_score},
            )
            for agent_name, agent in self.agent_trust.items()
        }
        self._persist_state()

    def _load_state(self) -> dict[str, TrustState]:
        raw_agents: dict[str, Any] = {}
        if self.storage_path.exists():
            try:
                raw_payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
                raw_agents = dict(raw_payload.get("agents", {}))
            except (json.JSONDecodeError, OSError):
                raw_agents = {}

        state: dict[str, TrustState] = {}
        for agent_name in self.agent_trust:
            if agent_name in raw_agents:
                state[agent_name] = TrustState.from_dict(raw_agents[agent_name])
            else:
                state[agent_name] = self._bootstrap_state(agent_name)
        return state

    def _persist_state(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "agents": {agent_name: trust_state.to_dict() for agent_name, trust_state in self.state.items()},
        }
        self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _normalize_seed_score(self, raw_score: Any, configured_level: str | None) -> int:
        if raw_score is None:
            defaults = {"high": 850, "medium": 600, "low": 250}
            return defaults.get(str(configured_level or "").lower(), TRUST_SCORE_DEFAULT)
        score = int(raw_score)
        if score <= 100:
            return max(0, min(TRUST_SCORE_MAX, score * 10))
        return max(0, min(TRUST_SCORE_MAX, score))

    def _normalize_threshold(self, raw_threshold: Any) -> int:
        if raw_threshold is None:
            return TRUST_SCORE_DEFAULT
        value = int(raw_threshold)
        if value <= 100:
            return value * 10
        return value

    def _tier_for_score(self, score: int) -> str:
        for threshold, tier in TRUST_TIER_THRESHOLDS:
            if score >= threshold:
                return tier
        return "untrusted"

    def _capability_band_for_score(self, score: int) -> str:
        if score >= 700:
            return "high"
        if score >= 500:
            return "medium"
        return "low"

    def _bootstrap_state(self, agent_name: str) -> TrustState:
        config = self.agent_trust.get(agent_name, {})
        seed_score = self._normalize_seed_score(config.get("score"), str(config.get("trust_level", "medium")))
        dimension_seed = round(seed_score / 10.0, 2)
        dimensions = {name: dimension_seed for name in TRUST_DIMENSION_WEIGHTS}
        now = datetime.now(timezone.utc).isoformat()
        return TrustState(
            agent_name=agent_name,
            total_score=seed_score,
            tier=self._tier_for_score(seed_score),
            identity_verified=bool(config.get("identity_verified", False)),
            dimensions=dimensions,
            last_updated=now,
            last_positive_signal_at=now if seed_score >= TRUST_WARNING_THRESHOLD else None,
            last_event={"type": "bootstrap", "reason": "initialized from trust policy"},
        )

    def _state_for(self, agent_name: str, *, apply_decay: bool = True) -> TrustState:
        if agent_name not in self.state:
            self.state[agent_name] = self._bootstrap_state(agent_name)
        trust_state = self.state[agent_name]
        if apply_decay:
            self._apply_decay(trust_state)
        return trust_state

    def _compute_total(self, dimensions: dict[str, float]) -> int:
        weighted = sum(dimensions[name] * TRUST_DIMENSION_WEIGHTS[name] for name in TRUST_DIMENSION_WEIGHTS)
        return max(0, min(TRUST_SCORE_MAX, int(round(weighted * 10))))

    def _scale_dimensions_to_score(self, dimensions: dict[str, float], previous_total: int, new_total: int) -> None:
        if previous_total <= 0:
            normalized = max(0.0, min(100.0, new_total / 10.0))
            for name in dimensions:
                dimensions[name] = round(normalized, 2)
            return
        factor = new_total / previous_total
        for name, value in dimensions.items():
            dimensions[name] = round(max(0.0, min(100.0, value * factor)), 2)

    def _apply_decay(self, trust_state: TrustState) -> None:
        try:
            last_updated = datetime.fromisoformat(trust_state.last_updated)
        except ValueError:
            last_updated = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        hours_elapsed = max(0.0, (now - last_updated).total_seconds() / 3600.0)
        if hours_elapsed < 1.0 or trust_state.total_score <= TRUST_SCORE_FLOOR:
            return
        decay_points = int(hours_elapsed * TRUST_DECAY_POINTS_PER_HOUR)
        if decay_points <= 0:
            return
        previous_total = trust_state.total_score
        trust_state.total_score = max(TRUST_SCORE_FLOOR, trust_state.total_score - decay_points)
        self._scale_dimensions_to_score(trust_state.dimensions, previous_total, trust_state.total_score)
        trust_state.previous_score = previous_total
        trust_state.score_change = trust_state.total_score - previous_total
        trust_state.tier = self._tier_for_score(trust_state.total_score)
        trust_state.last_updated = now.isoformat()
        trust_state.last_event = {
            "type": "decay",
            "reason": f"{decay_points} points decayed after {hours_elapsed:.2f} idle hours",
        }
        self._persist_state()

    def _record_signal(
        self,
        agent_name: str,
        event_type: str,
        reason: str,
        dimension_signals: dict[str, float],
        *,
        positive: bool,
        metadata: dict[str, Any] | None = None,
    ) -> TrustState:
        trust_state = self._state_for(agent_name)
        previous_total = trust_state.total_score
        for dimension_name, signal_value in dimension_signals.items():
            if dimension_name not in trust_state.dimensions:
                continue
            bounded_signal = max(0.0, min(100.0, signal_value))
            current_value = trust_state.dimensions[dimension_name]
            trust_state.dimensions[dimension_name] = round(
                (current_value * (1.0 - TRUST_EMA_ALPHA)) + (bounded_signal * TRUST_EMA_ALPHA),
                2,
            )
        trust_state.total_score = self._compute_total(trust_state.dimensions)
        trust_state.tier = self._tier_for_score(trust_state.total_score)
        trust_state.previous_score = previous_total
        trust_state.score_change = trust_state.total_score - previous_total
        trust_state.event_count += 1
        trust_state.last_updated = datetime.now(timezone.utc).isoformat()
        if positive:
            trust_state.last_positive_signal_at = trust_state.last_updated
        trust_state.last_event = {
            "type": event_type,
            "reason": reason,
            "metadata": metadata or {},
        }
        self._persist_state()
        return trust_state

    def _capabilities_for(self, agent_name: str) -> list[str]:
        trust_state = self._state_for(agent_name)
        level = self._capability_band_for_score(trust_state.total_score)
        return list(self.trust_levels.get(level, {}).get("capabilities", []))

    def record_policy_violation(self, agent_name: str, reason: str) -> TrustState:
        return self._record_signal(
            agent_name,
            "policy_violation",
            reason,
            {
                "policy_compliance": 5,
                "security_posture": 15,
                "collaboration_health": 20,
            },
            positive=False,
        )

    def record_tool_invocation(self, agent_name: str, tool_name: str) -> TrustState:
        return self._record_signal(
            agent_name,
            "tool_invocation",
            f"safe tool invocation: {tool_name}",
            {
                "resource_efficiency": 75,
                "collaboration_health": 70,
            },
            positive=True,
            metadata={"tool_name": tool_name},
        )

    def record_execution_result(self, agent_name: str, *, success: bool, detail: str) -> TrustState:
        return self._record_signal(
            agent_name,
            "execution_result",
            detail,
            {
                "output_quality": 85 if success else 25,
                "collaboration_health": 80 if success else 30,
                "security_posture": 70 if success else 35,
            },
            positive=success,
        )

    def record_quarantine(self, agent_name: str, reason: str) -> TrustState:
        return self._record_signal(
            agent_name,
            "quarantine",
            reason,
            {
                "policy_compliance": 0,
                "security_posture": 0,
                "collaboration_health": 10,
            },
            positive=False,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            agent_name: {
                "score": trust_state.total_score,
                "tier": trust_state.tier,
                "capability_band": self._capability_band_for_score(trust_state.total_score),
                "identity_verified": trust_state.identity_verified,
                "dimensions": trust_state.dimensions,
                "event_count": trust_state.event_count,
                "score_change": trust_state.score_change,
                "last_updated": trust_state.last_updated,
                "last_event": trust_state.last_event,
            }
            for agent_name, trust_state in self.state.items()
        }

    def check_delegation(self, requester: str, peer_agent: str, required_capabilities: list[str]) -> TrustDecision:
        trust_state = self._state_for(peer_agent)
        trust_level = trust_state.tier
        trust_score = trust_state.total_score
        identity_verified = trust_state.identity_verified
        did = None
        if peer_agent in self.clients:
            did = self.clients[peer_agent].agent_did

        reason = "Trust requirements met"
        allowed = True

        for rule in self.delegation_rules:
            min_trust_score = rule.get("min_trust_score")
            if min_trust_score is not None and trust_score < self._normalize_threshold(min_trust_score):
                allowed = False
                reason = rule.get("message") or rule.get("description", "Trust score too low")
                break

            required_level = rule.get("required_trust_level")
            if required_level and self.TRUST_ORDER.get(trust_level, 0) < self.TRUST_ORDER.get(required_level, 0):
                allowed = False
                reason = rule.get("description", "Trust level too low")
                break

            required_fields = rule.get("required_fields", [])
            if "identity_verified" in required_fields and not identity_verified:
                allowed = False
                reason = rule.get("description", "Identity verification required")
                break

            needed_capabilities = rule.get("required_capabilities") or required_capabilities
            if needed_capabilities:
                capabilities = set(self._capabilities_for(peer_agent))
                if not set(needed_capabilities).issubset(capabilities):
                    allowed = False
                    reason = rule.get("description", "Peer agent is missing required capabilities")
                    break

        updated_state = self._record_signal(
            peer_agent,
            "delegation_check",
            reason,
            {
                "collaboration_health": 95 if allowed else 5,
                "policy_compliance": 95 if allowed else 10,
            },
            positive=allowed,
            metadata={
                "requester": requester,
                "required_capabilities": required_capabilities,
            },
        )

        self.audit_log.log(
            event_type="trust_handshake",
            agent_did=requester,
            action="delegate",
            data={
                "peer_agent": peer_agent,
                "peer_did": did,
                "required_capabilities": required_capabilities,
                "identity_verified": identity_verified,
                "trust_level": trust_level,
                "trust_score": trust_score,
            },
            outcome="success" if allowed else "denied",
        )

        return TrustDecision(
            allowed=allowed,
            agent_name=peer_agent,
            trust_level=updated_state.tier,
            trust_score=updated_state.total_score,
            identity_verified=identity_verified,
            reason=reason,
            did=did,
        )


class ReliabilityMonitor:
    def __init__(self, reliability_path: Path, audit_log: AuditLog):
        payload = _read_yaml(reliability_path)
        config = payload.get("anomaly_detection", {})
        repeated_denials = config.get("repeated_denials", {})
        self.denial_threshold = int(repeated_denials.get("threshold", 3))
        self.denial_window_seconds = int(repeated_denials.get("window_seconds", 60))
        self.audit_log = audit_log
        self.detector = AnomalyDetector(DetectorConfig(min_samples=2))
        self.denials: dict[str, deque[float]] = defaultdict(deque)
        self.quarantined_until: dict[str, float] = {}

    def record_denial(self, agent_id: str, reason: str) -> dict[str, Any]:
        now = time.time()
        window = self.denials[agent_id]
        window.append(now)
        while window and window[0] < now - self.denial_window_seconds:
            window.popleft()

        alert = None
        if len(window) >= self.denial_threshold:
            self.quarantined_until[agent_id] = now + 600
            alert = {
                "detected": True,
                "anomaly_type": "repeated_denials",
                "severity": AnomalySeverity.CRITICAL.value,
                "reason": reason,
                "count": len(window),
            }
            self.audit_log.log(
                event_type="rogue_detection",
                agent_did=agent_id,
                action="quarantine",
                data=alert,
                outcome="denied",
            )
        return alert or {"detected": False, "count": len(window)}

    def record_tool_call(self, agent_id: str, tool_name: str) -> AnomalyAlert | None:
        alert = self.detector.record_tool_call(agent_id, tool_name)
        if alert:
            self.audit_log.log(
                event_type="tool_invocation",
                agent_did=agent_id,
                action="anomaly",
                resource=tool_name,
                data=alert.to_dict(),
                outcome="success",
            )
        return alert

    def is_quarantined(self, agent_id: str) -> bool:
        return self.quarantined_until.get(agent_id, 0) > time.time()

    def summary(self) -> dict[str, Any]:
        return {
            "quarantined_agents": {
                agent_id: until for agent_id, until in self.quarantined_until.items() if until > time.time()
            },
            "anomaly_summary": self.detector.summary(),
        }


class AuditTrailMiddleware(AgentMiddleware):
    def __init__(self, audit_log: AuditLog, trust_registry: TrustRegistry, agent_id: str):
        self.audit_log = audit_log
        self.trust_registry = trust_registry
        self.agent_id = agent_id

    async def process(self, context: AgentContext, call_next):
        completed = False
        entry = self.audit_log.log(
            event_type="agent_invocation",
            agent_did=self.agent_id,
            action="start",
            data={"message_count": len(getattr(context, "messages", []) or [])},
            outcome="success",
        )
        metadata = getattr(context, "metadata", None)
        if isinstance(metadata, dict):
            metadata["audit_entry_id"] = entry.entry_id
        try:
            await call_next()
            completed = True
        except Exception:
            self.trust_registry.record_execution_result(
                self.agent_id,
                success=False,
                detail="agent invocation failed or was interrupted",
            )
            raise
        finally:
            self.audit_log.log(
                event_type="agent_invocation",
                agent_did=self.agent_id,
                action="complete",
                data={"start_entry_id": entry.entry_id},
                outcome="success",
            )
            if completed:
                self.trust_registry.record_execution_result(
                    self.agent_id,
                    success=True,
                    detail="agent invocation completed",
                )


class ControlPlaneMiddleware(AgentMiddleware):
    def __init__(self, policy: ControlPlanePolicy, audit_log: AuditLog, reliability: ReliabilityMonitor, trust_registry: TrustRegistry, agent_id: str):
        self.policy = policy
        self.audit_log = audit_log
        self.reliability = reliability
        self.trust_registry = trust_registry
        self.agent_id = agent_id

    async def process(self, context: AgentContext, call_next):
        messages = getattr(context, "messages", None) or []
        last_message = messages[-1] if messages else None
        text = getattr(last_message, "text", "") if last_message is not None else ""
        decision = self.policy.check_prompt(self.agent_id, text)
        self.audit_log.log(
            event_type="policy_evaluation",
            agent_did=self.agent_id,
            action="prompt_check",
            data={"text": text[:500], "matched_rule": decision.matched_rule},
            outcome="success" if decision.allowed else "denied",
            policy_decision="allow" if decision.allowed else "deny",
        )
        if not decision.allowed:
            result = self.reliability.record_denial(self.agent_id, decision.reason)
            self.trust_registry.record_policy_violation(self.agent_id, decision.reason)
            if result.get("detected"):
                self.trust_registry.record_quarantine(self.agent_id, decision.reason)
            context.result = AgentResponse(messages=[Message(role="assistant", text=f"Governance blocked the request: {decision.reason}")])
            raise MiddlewareTermination(decision.reason)
        await call_next()


class CapabilityGuardMiddleware(FunctionMiddleware):
    def __init__(self, policy: ControlPlanePolicy, audit_log: AuditLog, reliability: ReliabilityMonitor, trust_registry: TrustRegistry, agent_id: str):
        self.policy = policy
        self.audit_log = audit_log
        self.reliability = reliability
        self.trust_registry = trust_registry
        self.agent_id = agent_id

    async def process(self, context: FunctionInvocationContext, call_next):
        tool_name = getattr(getattr(context, "function", None), "name", "unknown")
        decision = self.policy.check_tool(self.agent_id, tool_name)
        if not decision.allowed:
            result = self.reliability.record_denial(self.agent_id, decision.reason)
            self.trust_registry.record_policy_violation(self.agent_id, decision.reason)
            if result.get("detected"):
                self.trust_registry.record_quarantine(self.agent_id, decision.reason)
            context.result = f"Governance blocked tool use: {decision.reason}"
            raise MiddlewareTermination(decision.reason)
        self.audit_log.log(
            event_type="tool_invocation",
            agent_did=self.agent_id,
            action="start",
            resource=tool_name,
            data={"tool": tool_name},
            outcome="success",
        )
        self.reliability.record_tool_call(self.agent_id, tool_name)
        self.trust_registry.record_tool_invocation(self.agent_id, tool_name)
        await call_next()


class GovernanceRuntime:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.audit_log = AuditLog()
        self.control_plane = ControlPlanePolicy(repo_root / "policies" / "control_plane.yaml")
        self.trust_registry = TrustRegistry(
            repo_root / "policies" / "trust_identity.yaml",
            self.audit_log,
            repo_root / "artifacts" / "trust-state.json",
        )
        self.reliability = ReliabilityMonitor(repo_root / "policies" / "reliability.yaml", self.audit_log)

    def middleware_for(self, agent_id: str) -> list[Any]:
        return [
            AuditTrailMiddleware(self.audit_log, self.trust_registry, agent_id),
            ControlPlaneMiddleware(self.control_plane, self.audit_log, self.reliability, self.trust_registry, agent_id),
            CapabilityGuardMiddleware(self.control_plane, self.audit_log, self.reliability, self.trust_registry, agent_id),
        ]

    def scan_mcp(self, config_path: str | Path) -> list[SecurityFinding]:
        return scan_config(Path(config_path))

    def export_audit(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        entries = self.audit_log.export()
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2, default=str)
        return output_path

    def governance_snapshot(self) -> dict[str, Any]:
        return {
            "audit_entries": len(self.audit_log.export()),
            "trusted_agents": self.trust_registry.snapshot(),
            "reliability": self.reliability.summary(),
        }