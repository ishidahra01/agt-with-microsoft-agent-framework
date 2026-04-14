from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
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
    TRUST_ORDER = {"low": 0, "medium": 1, "high": 2}

    def __init__(self, trust_path: Path, audit_log: AuditLog):
        payload = _read_yaml(trust_path)
        self.trust_levels = payload.get("trust_levels", {})
        self.agent_trust = payload.get("agent_trust", {})
        self.delegation_rules = payload.get("delegation", {}).get("rules", [])
        self.audit_log = audit_log
        self.clients = {
            agent_name: AgentMeshClient(
                agent_name,
                capabilities=self._capabilities_for(agent_name),
                trust_config={"initial_score": int(agent.get("score", 50))},
            )
            for agent_name, agent in self.agent_trust.items()
        }

    def _capabilities_for(self, agent_name: str) -> list[str]:
        agent = self.agent_trust.get(agent_name, {})
        level = str(agent.get("trust_level", "low"))
        return list(self.trust_levels.get(level, {}).get("capabilities", []))

    def check_delegation(self, requester: str, peer_agent: str, required_capabilities: list[str]) -> TrustDecision:
        agent = self.agent_trust.get(peer_agent, {})
        trust_level = str(agent.get("trust_level", "low"))
        trust_score = int(agent.get("score", 0))
        identity_verified = bool(agent.get("identity_verified", False))
        did = None
        if peer_agent in self.clients:
            did = self.clients[peer_agent].agent_did

        reason = "Trust requirements met"
        allowed = True

        for rule in self.delegation_rules:
            min_trust_score = rule.get("min_trust_score")
            if min_trust_score is not None and trust_score < int(min_trust_score):
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
            trust_level=trust_level,
            trust_score=trust_score,
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
    def __init__(self, audit_log: AuditLog, agent_id: str):
        self.audit_log = audit_log
        self.agent_id = agent_id

    async def process(self, context: AgentContext, call_next):
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
        finally:
            self.audit_log.log(
                event_type="agent_invocation",
                agent_did=self.agent_id,
                action="complete",
                data={"start_entry_id": entry.entry_id},
                outcome="success",
            )


class ControlPlaneMiddleware(AgentMiddleware):
    def __init__(self, policy: ControlPlanePolicy, audit_log: AuditLog, reliability: ReliabilityMonitor, agent_id: str):
        self.policy = policy
        self.audit_log = audit_log
        self.reliability = reliability
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
            self.reliability.record_denial(self.agent_id, decision.reason)
            context.result = AgentResponse(messages=[Message(role="assistant", text=f"Governance blocked the request: {decision.reason}")])
            raise MiddlewareTermination(decision.reason)
        await call_next()


class CapabilityGuardMiddleware(FunctionMiddleware):
    def __init__(self, policy: ControlPlanePolicy, audit_log: AuditLog, reliability: ReliabilityMonitor, agent_id: str):
        self.policy = policy
        self.audit_log = audit_log
        self.reliability = reliability
        self.agent_id = agent_id

    async def process(self, context: FunctionInvocationContext, call_next):
        tool_name = getattr(getattr(context, "function", None), "name", "unknown")
        decision = self.policy.check_tool(self.agent_id, tool_name)
        if not decision.allowed:
            self.reliability.record_denial(self.agent_id, decision.reason)
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
        await call_next()


class GovernanceRuntime:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.audit_log = AuditLog()
        self.control_plane = ControlPlanePolicy(repo_root / "policies" / "control_plane.yaml")
        self.trust_registry = TrustRegistry(repo_root / "policies" / "trust_identity.yaml", self.audit_log)
        self.reliability = ReliabilityMonitor(repo_root / "policies" / "reliability.yaml", self.audit_log)

    def middleware_for(self, agent_id: str) -> list[Any]:
        return [
            AuditTrailMiddleware(self.audit_log, agent_id),
            ControlPlaneMiddleware(self.control_plane, self.audit_log, self.reliability, agent_id),
            CapabilityGuardMiddleware(self.control_plane, self.audit_log, self.reliability, agent_id),
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
            "trusted_agents": {
                agent_name: {
                    "score": info.get("score"),
                    "trust_level": info.get("trust_level"),
                    "identity_verified": info.get("identity_verified"),
                }
                for agent_name, info in self.trust_registry.agent_trust.items()
            },
            "reliability": self.reliability.summary(),
        }