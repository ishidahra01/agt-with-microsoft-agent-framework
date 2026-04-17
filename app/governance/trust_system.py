"""
Agent Governance Toolkit - Trust and Identity System

This module implements runtime trust-based access control for agent-to-agent interaction.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class TrustLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class TrustCheckResult:
    allowed: bool
    agent_name: str
    trust_level: TrustLevel
    trust_score: int
    reason: str
    required_capabilities: List[str]
    actual_capabilities: List[str]


class TrustSystem:
    """Runtime trust evaluation for agent delegation"""

    def __init__(self, policy_dir: str | Path | None = None):
        self.policy_dir = Path(policy_dir) if policy_dir is not None else Path(__file__).resolve().parents[1] / "policies"
        self.trust_config = self._load_trust_config()

    def _load_trust_config(self) -> Dict[str, Any]:
        """Load trust and identity policies"""
        trust_path = self.policy_dir / "trust_identity.yaml"
        if trust_path.exists():
            with open(trust_path) as f:
                return yaml.safe_load(f)
        return {}

    def check_agent_trust(self, agent_name: str, required_capabilities: List[str]) -> TrustCheckResult:
        """Check if an agent meets trust requirements for delegation"""

        agent_trust = self.trust_config.get('agent_trust', {}).get(agent_name)

        if not agent_trust:
            return TrustCheckResult(
                allowed=False,
                agent_name=agent_name,
                trust_level=TrustLevel.LOW,
                trust_score=0,
                reason=f"Agent '{agent_name}' not found in trust registry",
                required_capabilities=required_capabilities,
                actual_capabilities=[]
            )

        trust_level_str = agent_trust.get('trust_level', 'low')
        trust_score = agent_trust.get('score', 0)
        identity_verified = agent_trust.get('identity_verified', False)
        actual_capabilities = agent_trust.get('capabilities_verified', [])

        # Convert trust level string to enum
        trust_level = TrustLevel.LOW
        if trust_level_str == "high":
            trust_level = TrustLevel.HIGH
        elif trust_level_str == "medium":
            trust_level = TrustLevel.MEDIUM

        # Check delegation rules
        delegation_rules = self.trust_config.get('delegation', {}).get('rules', [])

        for rule in delegation_rules:
            rule_name = rule.get('name', '')

            # Check trust level requirement
            if 'required_trust_level' in rule:
                required_trust = rule['required_trust_level']
                if trust_level_str != required_trust and not (trust_level_str == "high" and required_trust in ["medium", "low"]):
                    return TrustCheckResult(
                        allowed=False,
                        agent_name=agent_name,
                        trust_level=trust_level,
                        trust_score=trust_score,
                        reason=f"Trust level '{trust_level_str}' does not meet requirement '{required_trust}' (rule: {rule_name})",
                        required_capabilities=required_capabilities,
                        actual_capabilities=actual_capabilities if isinstance(actual_capabilities, list) else []
                    )

            # Check identity verification
            if rule.get('required_fields', []):
                if 'identity_verified' in rule['required_fields'] and not identity_verified:
                    return TrustCheckResult(
                        allowed=False,
                        agent_name=agent_name,
                        trust_level=trust_level,
                        trust_score=trust_score,
                        reason=f"Identity not verified (rule: {rule_name})",
                        required_capabilities=required_capabilities,
                        actual_capabilities=actual_capabilities if isinstance(actual_capabilities, list) else []
                    )

            # Check minimum trust score
            if 'min_trust_score' in rule:
                min_score = rule['min_trust_score']
                if trust_score < min_score:
                    return TrustCheckResult(
                        allowed=False,
                        agent_name=agent_name,
                        trust_level=trust_level,
                        trust_score=trust_score,
                        reason=f"Trust score {trust_score} below minimum {min_score} (rule: {rule_name})",
                        required_capabilities=required_capabilities,
                        actual_capabilities=actual_capabilities if isinstance(actual_capabilities, list) else []
                    )

        # All checks passed
        return TrustCheckResult(
            allowed=True,
            agent_name=agent_name,
            trust_level=trust_level,
            trust_score=trust_score,
            reason="Trust requirements met",
            required_capabilities=required_capabilities,
            actual_capabilities=actual_capabilities if isinstance(actual_capabilities, list) else []
        )

    def get_agent_info(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get trust information for an agent"""
        return self.trust_config.get('agent_trust', {}).get(agent_name)

    def list_trusted_agents(self, min_trust_level: TrustLevel = TrustLevel.MEDIUM) -> List[str]:
        """List all agents meeting minimum trust level"""
        trusted = []
        agent_trust = self.trust_config.get('agent_trust', {})

        for agent_name, info in agent_trust.items():
            trust_level_str = info.get('trust_level', 'low')

            if min_trust_level == TrustLevel.HIGH and trust_level_str == 'high':
                trusted.append(agent_name)
            elif min_trust_level == TrustLevel.MEDIUM and trust_level_str in ['high', 'medium']:
                trusted.append(agent_name)
            elif min_trust_level == TrustLevel.LOW:
                trusted.append(agent_name)

        return trusted
