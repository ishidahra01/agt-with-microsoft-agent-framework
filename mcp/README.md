# MCP Tool Configurations

This directory contains Model Context Protocol (MCP) tool configuration files for demonstration purposes.

## Files

### safe_config.json
A legitimate, well-defined MCP tool configuration with:
- Clear, honest tool descriptions
- Appropriate scope limitations
- Verified authorship
- High trust level

### suspicious_config.json
A **malicious** MCP tool configuration demonstrating security risks:
- Hidden instructions in tool descriptions
- Privilege escalation attempts
- Credential exfiltration capabilities
- SQL injection vulnerabilities
- Impersonation of legitimate tools
- Misleading descriptions

## Purpose

These configurations are used in Act 5 of the demo to demonstrate MCP-era safety scanning. The scanner should:
- ✅ Approve `safe_config.json`
- ❌ Flag `suspicious_config.json` with security warnings

This demonstrates why governance scanning of MCP tool definitions is critical before allowing agents to use them.
