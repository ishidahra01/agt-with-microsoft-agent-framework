"""
Agent Governance Toolkit - Policy Engine

This module implements the control plane policy enforcement.
It evaluates file access, command execution, and tool usage requests
against governance policies BEFORE execution.
"""

import fnmatch
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class PolicyDecision(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass
class PolicyResult:
    decision: PolicyDecision
    rule_name: str
    message: str
    policy_type: str
    details: Dict[str, Any]


class PolicyEngine:
    """System-enforced control plane for agent operations"""

    def __init__(self, policy_dir: str | Path | None = None):
        self.policy_dir = Path(policy_dir) if policy_dir is not None else Path(__file__).resolve().parents[1] / "policies"
        self.policies = self._load_policies()
        self.audit_log = []

    def _load_policies(self) -> Dict[str, Any]:
        """Load all governance policies"""
        policies = {}

        # Load control plane policies
        control_plane_path = self.policy_dir / "control_plane.yaml"
        if control_plane_path.exists():
            with open(control_plane_path) as f:
                policies['control_plane'] = yaml.safe_load(f)

        return policies

    def check_file_access(self, file_path: str, operation: str = "read") -> PolicyResult:
        """Check if file access is allowed by policy"""

        if 'control_plane' not in self.policies:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                rule_name="default",
                message="No policies loaded",
                policy_type="file_access",
                details={"path": file_path}
            )

        file_access_rules = self.policies['control_plane'].get('policies', {}).get('file_access', [])
        normalized_path = Path(file_path).as_posix()

        # Check deny rules first (deny takes precedence)
        for rule in file_access_rules:
            if rule.get('action') == 'DENY':
                patterns = rule.get('patterns', [])
                for pattern in patterns:
                    if fnmatch.fnmatch(normalized_path, pattern):
                        result = PolicyResult(
                            decision=PolicyDecision.DENY,
                            rule_name=rule.get('rule', 'unknown'),
                            message=rule.get('message', 'Access denied by policy'),
                            policy_type="file_access",
                            details={
                                "path": normalized_path,
                                "pattern": pattern,
                                "description": rule.get('description', '')
                            }
                        )
                        self._audit_log(result)
                        return result

        # Check allow rules
        for rule in file_access_rules:
            if rule.get('action') == 'ALLOW':
                patterns = rule.get('patterns', [])
                for pattern in patterns:
                    if fnmatch.fnmatch(normalized_path, pattern):
                        result = PolicyResult(
                            decision=PolicyDecision.ALLOW,
                            rule_name=rule.get('rule', 'unknown'),
                            message="Access allowed by policy",
                            policy_type="file_access",
                            details={
                                "path": normalized_path,
                                "pattern": pattern
                            }
                        )
                        self._audit_log(result)
                        return result

        # Default deny for unmatched paths
        result = PolicyResult(
            decision=PolicyDecision.DENY,
            rule_name="default_deny",
            message="File path not in allowed list",
            policy_type="file_access",
            details={"path": normalized_path}
        )
        self._audit_log(result)
        return result

    def check_command_execution(self, command: str) -> PolicyResult:
        """Check if command execution is allowed by policy"""

        normalized_command = command.strip()

        if 'control_plane' not in self.policies:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                rule_name="default",
                message="No policies loaded",
                policy_type="command_execution",
                details={"command": normalized_command}
            )

        cmd_rules = self.policies['control_plane'].get('policies', {}).get('command_execution', [])

        # Check deny rules first
        for rule in cmd_rules:
            if rule.get('action') == 'DENY':
                patterns = rule.get('patterns', [])
                for pattern in patterns:
                    if fnmatch.fnmatch(normalized_command, pattern) or pattern in normalized_command:
                        result = PolicyResult(
                            decision=PolicyDecision.DENY,
                            rule_name=rule.get('rule', 'unknown'),
                            message=rule.get('message', 'Command denied by policy'),
                            policy_type="command_execution",
                            details={
                                "command": normalized_command,
                                "pattern": pattern,
                                "description": rule.get('description', '')
                            }
                        )
                        self._audit_log(result)
                        return result

        # Check allow rules
        for rule in cmd_rules:
            if rule.get('action') == 'ALLOW':
                patterns = rule.get('patterns', [])
                for pattern in patterns:
                    if fnmatch.fnmatch(normalized_command, pattern) or pattern in normalized_command:
                        result = PolicyResult(
                            decision=PolicyDecision.ALLOW,
                            rule_name=rule.get('rule', 'unknown'),
                            message="Command allowed by policy",
                            policy_type="command_execution",
                            details={"command": normalized_command}
                        )
                        self._audit_log(result)
                        return result

        # Default deny
        result = PolicyResult(
            decision=PolicyDecision.DENY,
            rule_name="default_deny",
            message="Command not in allowed list",
            policy_type="command_execution",
            details={"command": normalized_command}
        )
        self._audit_log(result)
        return result

    def check_tool_usage(self, agent_name: str, tool_name: str) -> PolicyResult:
        """Check if tool usage is allowed for this agent"""

        if 'control_plane' not in self.policies:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                rule_name="default",
                message="No policies loaded",
                policy_type="tool_usage",
                details={"agent": agent_name, "tool": tool_name}
            )

        tool_rules = self.policies['control_plane'].get('policies', {}).get('tool_restrictions', [])

        for rule in tool_rules:
            if rule.get('agent') == agent_name:
                allowed_tools = rule.get('allowed_tools', [])
                denied_tools = rule.get('denied_tools', [])

                if tool_name in denied_tools:
                    result = PolicyResult(
                        decision=PolicyDecision.DENY,
                        rule_name=rule.get('rule', 'unknown'),
                        message=f"Tool '{tool_name}' is denied for agent '{agent_name}'",
                        policy_type="tool_usage",
                        details={
                            "agent": agent_name,
                            "tool": tool_name,
                            "description": rule.get('description', '')
                        }
                    )
                    self._audit_log(result)
                    return result

                if allowed_tools and tool_name not in allowed_tools:
                    result = PolicyResult(
                        decision=PolicyDecision.DENY,
                        rule_name=rule.get('rule', 'unknown'),
                        message=f"Tool '{tool_name}' not in allowed list for agent '{agent_name}'",
                        policy_type="tool_usage",
                        details={
                            "agent": agent_name,
                            "tool": tool_name,
                            "allowed_tools": allowed_tools
                        }
                    )
                    self._audit_log(result)
                    return result

        # If no specific rule found, allow by default
        result = PolicyResult(
            decision=PolicyDecision.ALLOW,
            rule_name="default_allow",
            message="Tool usage allowed",
            policy_type="tool_usage",
            details={"agent": agent_name, "tool": tool_name}
        )
        self._audit_log(result)
        return result

    def _audit_log(self, result: PolicyResult):
        """Log policy decision for audit trail"""
        self.audit_log.append({
            "timestamp": self._get_timestamp(),
            "decision": result.decision.value,
            "rule": result.rule_name,
            "type": result.policy_type,
            "message": result.message,
            "details": result.details
        })

    def _get_timestamp(self) -> str:
        """Get current timestamp for audit log"""
        from datetime import datetime
        return datetime.now().isoformat()

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Retrieve audit log entries"""
        return self.audit_log

    def save_audit_log(self, filepath: str):
        """Save audit log to file"""
        import json
        with open(filepath, 'w') as f:
            json.dump(self.audit_log, f, indent=2)
