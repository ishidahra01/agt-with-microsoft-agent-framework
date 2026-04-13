# Quick Start Guide

## Running the Demo

### Full Interactive Demo

Run all 5 acts sequentially with interactive prompts:

```bash
cd /path/to/agt-with-microsoft-agent-framework
python app/demo.py
```

Press Enter at each prompt to advance through the acts.

### Individual Acts

Run specific acts for focused demonstrations:

```bash
# Act 1: Normal helpful flow
python app/demo.py act1

# Act 2: Unsafe request blocked
python app/demo.py act2

# Act 3: Anomaly containment
python app/demo.py act3

# Act 4: Trust check
python app/demo.py act4

# Act 5: MCP scan
python app/demo.py act5
```

## What to Expect

### Act 1 Output
- ✅ Triage subagent successfully reads tickets
- ✅ Triage subagent successfully reads runbooks
- Shows normal, approved operations

### Act 2 Output
- ❌ Access to `demo_workspace/secrets/.env` **DENIED**
- ❌ `sudo cat /etc/passwd` **DENIED**
- ❌ `rm -rf /tmp/*` **DENIED**
- Demonstrates system-enforced control plane

### Act 3 Output
- ❌ First attempt to access secrets **DENIED**
- ❌ Second attempt **DENIED**
- ❌ Third attempt **DENIED**
- 🚨 **ANOMALY DETECTED** - Agent quarantined!
- Shows reliability containment

### Act 4 Output
- ❌ `untrusted-peer-helper` delegation **DENIED** (trust score: 45)
- ✅ `trusted-peer-helper` delegation **ALLOWED** (trust score: 88)
- Demonstrates trust-based access control

### Act 5 Output
- ✅ `safe_config.json` **PASSED** (risk score: 0/100)
- ❌ `suspicious_config.json` **FAILED** (risk score: 100/100, 19 issues)
- Generates detailed report in `artifacts/mcp_scan_report.txt`

## Generated Artifacts

After running the demo, check these files:

```bash
# View policy decisions audit log
cat artifacts/policy_audit.json

# View agent health status
cat artifacts/agent_status.json

# View MCP security scan report
cat artifacts/mcp_scan_report.txt
```

## Customization Examples

### Adding a New Policy Rule

Edit `policies/control_plane.yaml`:

```yaml
file_access:
  - rule: deny_my_custom_path
    description: "Block access to custom directory"
    action: DENY
    patterns:
      - "my_restricted_dir/*"
    message: "Access to my restricted directory is prohibited"
```

### Creating a New Subagent

Create `app/.claude/agents/my-agent.json`:

```json
{
  "name": "my-agent",
  "description": "My custom agent",
  "prompt": "You are a helpful agent that...",
  "tools": {
    "allowed": ["read_file", "list_files"],
    "denied": ["write_file", "execute_command"]
  },
  "permissions": {
    "mode": "ask",
    "allowed_paths": ["demo_workspace/tickets/*"],
    "denied_paths": ["demo_workspace/secrets/*"]
  },
  "governance": {
    "trust_level": "high",
    "trust_score": 85
  }
}
```

Then add it to `policies/trust_identity.yaml`:

```yaml
agent_trust:
  my-agent:
    trust_level: high
    score: 85
    identity_verified: true
    capabilities_verified: true
    description: "My custom agent"
```

### Adjusting Anomaly Thresholds

Edit `policies/reliability.yaml`:

```yaml
anomaly_detection:
  repeated_denials:
    threshold: 5  # Changed from 3 to 5
    window_seconds: 120  # Changed from 60 to 120
```

## Troubleshooting

### Import Errors

If you see import errors, make sure you're running from the repository root:

```bash
cd /path/to/agt-with-microsoft-agent-framework
python app/demo.py
```

### YAML Parse Errors

If policies fail to load, check YAML syntax:

```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('policies/control_plane.yaml'))"
```

### Missing Dependencies

Install all requirements:

```bash
pip install -r requirements.txt
```

## Next Steps

1. **Explore the code** - Read through the governance modules to understand how each component works
2. **Modify policies** - Experiment with different policy configurations
3. **Add custom scenarios** - Create new demo acts to test specific governance scenarios
4. **Integrate with real systems** - Replace the demo runner with actual Microsoft Agent Framework integration

## Learning Resources

- Read the main [README.md](../README.md) for architecture details
- Review the [policies/](../policies/) directory for policy examples
- Check [app/governance/](../app/governance/) for implementation details
- See the official [Microsoft Agent Framework blog post](https://devblogs.microsoft.com/agent-framework/build-ai-agents-with-claude-agent-sdk-and-microsoft-agent-framework/)
