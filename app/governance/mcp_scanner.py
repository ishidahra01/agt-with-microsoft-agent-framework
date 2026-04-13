"""
Agent Governance Toolkit - MCP Security Scanner

This module scans Model Context Protocol (MCP) tool configurations
for security issues before allowing agents to use them.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class SeverityLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SecurityFinding:
    severity: SeverityLevel
    issue_type: str
    description: str
    location: str
    recommendation: str


@dataclass
class ScanResult:
    config_name: str
    passed: bool
    findings: List[SecurityFinding]
    risk_score: int
    summary: str


class MCPScanner:
    """Security scanner for MCP tool configurations"""

    def __init__(self):
        self.suspicious_patterns = {
            "_hidden": "Hidden or obfuscated instructions",
            "_secret": "Secret or undocumented behavior",
            "_impl": "Implementation details that should not be exposed",
            "_poisoned": "Deliberately poisoned configuration",
            "_malicious": "Malicious behavior indicators",
            "sudo": "Privilege escalation attempt",
            "privileged": "Privileged operation request",
            "credential": "Credential access",
            "password": "Password handling",
            "secret": "Secret access",
            ".env": "Environment file access",
            "exfiltrat": "Data exfiltration indicators",
            "injection": "Injection vulnerability indicators"
        }

        self.mandatory_fields = ["name", "version", "description", "tools"]

    def scan_config(self, config_path: str) -> ScanResult:
        """Scan an MCP config file for security issues"""
        config_path = Path(config_path)
        config_name = config_path.stem

        try:
            with open(config_path) as f:
                config = json.load(f)
        except Exception as e:
            return ScanResult(
                config_name=config_name,
                passed=False,
                findings=[
                    SecurityFinding(
                        severity=SeverityLevel.HIGH,
                        issue_type="parse_error",
                        description=f"Failed to parse config: {str(e)}",
                        location=str(config_path),
                        recommendation="Ensure config is valid JSON"
                    )
                ],
                risk_score=100,
                summary="Config failed to parse"
            )

        findings = []

        # Check for mandatory fields
        for field in self.mandatory_fields:
            if field not in config:
                findings.append(
                    SecurityFinding(
                        severity=SeverityLevel.MEDIUM,
                        issue_type="missing_field",
                        description=f"Missing mandatory field: {field}",
                        location="root",
                        recommendation=f"Add {field} field to config"
                    )
                )

        # Check metadata
        metadata = config.get('metadata', {})
        if not metadata.get('verified', False):
            findings.append(
                SecurityFinding(
                    severity=SeverityLevel.MEDIUM,
                    issue_type="unverified_source",
                    description="Config source is not verified",
                    location="metadata.verified",
                    recommendation="Only use configs from verified sources"
                )
            )

        if metadata.get('author') == 'anonymous' or not metadata.get('author'):
            findings.append(
                SecurityFinding(
                    severity=SeverityLevel.MEDIUM,
                    issue_type="anonymous_author",
                    description="Config author is anonymous or unknown",
                    location="metadata.author",
                    recommendation="Verify authorship before using"
                )
            )

        # Scan entire config for suspicious patterns
        config_str = json.dumps(config, indent=2)
        for pattern, description in self.suspicious_patterns.items():
            if pattern in config_str.lower():
                findings.append(
                    SecurityFinding(
                        severity=SeverityLevel.HIGH if pattern in ["_poisoned", "_malicious", "exfiltrat"] else SeverityLevel.MEDIUM,
                        issue_type="suspicious_pattern",
                        description=f"Suspicious pattern detected: {description}",
                        location=f"Contains '{pattern}'",
                        recommendation="Do not use this config - potential security risk"
                    )
                )

        # Check tools for issues
        tools = config.get('tools', [])
        for i, tool in enumerate(tools):
            tool_name = tool.get('name', f'tool_{i}')

            # Check for hidden fields in tool definitions
            for key in tool.keys():
                if key.startswith('_'):
                    findings.append(
                        SecurityFinding(
                            severity=SeverityLevel.HIGH,
                            issue_type="hidden_field",
                            description=f"Tool '{tool_name}' contains hidden field: {key}",
                            location=f"tools[{i}].{key}",
                            recommendation="Hidden fields may indicate malicious behavior"
                        )
                    )

            # Check for misleading descriptions
            description = tool.get('description', '')
            if any(word in description.lower() for word in ['important:', 'must use', 'should be preferred', 'specially configured']):
                findings.append(
                    SecurityFinding(
                        severity=SeverityLevel.HIGH,
                        issue_type="manipulative_description",
                        description=f"Tool '{tool_name}' has manipulative language in description",
                        location=f"tools[{i}].description",
                        recommendation="Manipulative descriptions may be trying to override agent judgment"
                    )
                )

            # Check for SQL injection risks
            input_schema = tool.get('inputSchema', {})
            properties = input_schema.get('properties', {})
            for prop_name, prop_def in properties.items():
                if 'sql' in prop_name.lower() or 'query' in prop_name.lower():
                    findings.append(
                        SecurityFinding(
                            severity=SeverityLevel.HIGH,
                            issue_type="sql_injection_risk",
                            description=f"Tool '{tool_name}' may be vulnerable to SQL injection",
                            location=f"tools[{i}].inputSchema.properties.{prop_name}",
                            recommendation="Ensure SQL queries are parameterized and sanitized"
                        )
                    )

        # Calculate risk score
        risk_score = 0
        for finding in findings:
            if finding.severity == SeverityLevel.CRITICAL:
                risk_score += 40
            elif finding.severity == SeverityLevel.HIGH:
                risk_score += 25
            elif finding.severity == SeverityLevel.MEDIUM:
                risk_score += 10
            elif finding.severity == SeverityLevel.LOW:
                risk_score += 5

        risk_score = min(risk_score, 100)

        # Determine pass/fail
        passed = risk_score < 30 and not any(f.severity in [SeverityLevel.CRITICAL, SeverityLevel.HIGH] for f in findings)

        # Generate summary
        if passed:
            summary = f"✅ Config passed security scan (risk score: {risk_score}/100)"
        else:
            critical_count = len([f for f in findings if f.severity == SeverityLevel.CRITICAL])
            high_count = len([f for f in findings if f.severity == SeverityLevel.HIGH])
            summary = f"❌ Config FAILED security scan (risk score: {risk_score}/100) - {critical_count} critical, {high_count} high severity issues"

        return ScanResult(
            config_name=config_name,
            passed=passed,
            findings=findings,
            risk_score=risk_score,
            summary=summary
        )

    def scan_directory(self, mcp_dir: str) -> List[ScanResult]:
        """Scan all MCP configs in a directory"""
        results = []
        mcp_path = Path(mcp_dir)

        for config_file in mcp_path.glob("*.json"):
            result = self.scan_config(str(config_file))
            results.append(result)

        return results

    def generate_report(self, results: List[ScanResult]) -> str:
        """Generate a human-readable security report"""
        lines = []
        lines.append("=" * 80)
        lines.append("MCP Security Scan Report")
        lines.append("=" * 80)
        lines.append("")

        total = len(results)
        passed = len([r for r in results if r.passed])
        failed = total - passed

        lines.append(f"Total configs scanned: {total}")
        lines.append(f"Passed: {passed} ✅")
        lines.append(f"Failed: {failed} ❌")
        lines.append("")

        for result in results:
            lines.append("-" * 80)
            lines.append(f"Config: {result.config_name}")
            lines.append(f"Status: {'✅ PASS' if result.passed else '❌ FAIL'}")
            lines.append(f"Risk Score: {result.risk_score}/100")
            lines.append(f"Findings: {len(result.findings)}")
            lines.append("")

            if result.findings:
                lines.append("Security Issues:")
                for i, finding in enumerate(result.findings, 1):
                    lines.append(f"  {i}. [{finding.severity.value}] {finding.issue_type}")
                    lines.append(f"     Description: {finding.description}")
                    lines.append(f"     Location: {finding.location}")
                    lines.append(f"     Recommendation: {finding.recommendation}")
                    lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)
