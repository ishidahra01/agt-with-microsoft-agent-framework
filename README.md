# Governed Multi-Agent Workspace Assistant Demo

A comprehensive demonstration of **Agent Governance Toolkit (AGT)** integrated with **Microsoft Agent Framework** and **Claude Agent SDK** for building secure, trustworthy multi-agent systems.

## 🎯 What This Demo Shows

This demo implements a governed multi-agent workspace assistant that demonstrates four critical governance values:

| Governance Value | What It Means | How We Demonstrate It |
|-----------------|---------------|----------------------|
| **System-Enforced Control Plane** | Dangerous actions are blocked at the system level, not relying on the model to "behave" | Policy engine blocks file access to secrets/, privilege escalation, and destructive commands **before execution** |
| **Runtime Trust for Agent Delegation** | Not every peer agent is equally trusted; delegation is allowed/denied based on trust | Trust system validates agent identity and trust score before allowing task delegation |
| **Agent Reliability & Failure Containment** | Runaway or suspicious behavior is detected and contained | Anomaly detection triggers quarantine after repeated policy violations; circuit breakers prevent cascading failures |
| **MCP-Era Safety** | Suspicious MCP tool definitions are detected before agents use them | Security scanner flags hidden instructions, privilege escalation, and credential exfiltration in tool configs |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     User / Demo Runner                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  workspace-governor (Main Agent)                │
│  • Orchestrates workflow                                        │
│  • Delegates to subagents                                       │
│  • Produces final reports in Japanese                           │
└───────────┬──────────────────────────────────┬──────────────────┘
            │                                  │
            ▼                                  ▼
┌───────────────────────┐          ┌──────────────────────────┐
│  triage-subagent      │          │  executor-subagent       │
│  • Read-only          │          │  • Action-oriented       │
│  • Analyzes tickets   │          │  • Limited tool set      │
│  • Reviews runbooks   │          │  • Restricted scope      │
└───────────────────────┘          └──────────────────────────┘
            │                                  │
            └──────────────┬───────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Agent Governance Toolkit (AGT)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Policy       │  │ Trust &      │  │ Reliability         │  │
│  │ Engine       │  │ Identity     │  │ Monitor             │  │
│  │              │  │              │  │                     │  │
│  │ • File       │  │ • Agent      │  │ • Anomaly Detection │  │
│  │   access     │  │   trust      │  │ • Quarantine        │  │
│  │ • Command    │  │   scores     │  │ • Circuit Breaker   │  │
│  │   execution  │  │ • Delegation │  │ • Rate Limiting     │  │
│  │ • Tool usage │  │   rules      │  │                     │  │
│  └──────────────┘  └──────────────┘  └─────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ MCP Scanner                                              │  │
│  │ • Scans tool configs for security issues                │  │
│  │ • Detects hidden instructions, privilege escalation     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 📂 Repository Structure

```
.
├── app/
│   ├── .claude/
│   │   ├── agents/              # Subagent definitions
│   │   │   ├── triage-subagent.json
│   │   │   ├── executor-subagent.json
│   │   │   └── audit-explainer-subagent.json
│   │   └── skills/              # Reusable skills
│   │       ├── governance-explainer.json
│   │       └── demo-walkthrough.json
│   ├── governance/              # AGT implementation
│   │   ├── __init__.py
│   │   ├── policy_engine.py     # Control plane enforcement
│   │   ├── trust_system.py      # Trust-based delegation
│   │   ├── reliability.py       # Anomaly detection & containment
│   │   └── mcp_scanner.py       # MCP security scanning
│   └── demo.py                  # Interactive demo runner
├── policies/
│   ├── control_plane.yaml       # File/command/tool policies
│   ├── trust_identity.yaml      # Agent trust configuration
│   └── reliability.yaml         # Anomaly thresholds
├── demo_workspace/
│   ├── tickets/                 # Safe sample tickets
│   ├── runbooks/                # Safe runbooks
│   └── secrets/                 # RESTRICTED - governance test
├── mcp/
│   ├── safe_config.json         # Legitimate MCP tools
│   └── suspicious_config.json   # Malicious MCP tools
├── artifacts/                   # Generated outputs
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/ishidahra01/agt-with-microsoft-agent-framework.git
cd agt-with-microsoft-agent-framework

# Install dependencies
pip install -r requirements.txt
```

### Run the Demo

```bash
# Run the full interactive 5-act demo
cd app
python demo.py

# Or run individual acts
python demo.py act1  # Normal flow
python demo.py act2  # Unsafe blocked
python demo.py act3  # Anomaly containment
python demo.py act4  # Trust check
python demo.py act5  # MCP scan
```

## 🎭 Demo Walkthrough

### Act 1: 正常な動作 (Normal Helpful Flow)

**Goal:** Show agents working normally with safe operations.

**What Happens:**
1. Main agent delegates ticket analysis to `triage-subagent`
2. Subagent reads `demo_workspace/tickets/TICKET-001.md` ✅ **ALLOWED**
3. Subagent reads `demo_workspace/runbooks/workspace-setup.md` ✅ **ALLOWED**
4. Analysis completes successfully

**Key Takeaway:** Safe operations within policy boundaries are allowed smoothly.

---

### Act 2: 危険な要求のブロック (Unsafe Request Blocked)

**Goal:** Demonstrate system-enforced control plane blocking dangerous operations.

**What Happens:**
1. Agent attempts to read `demo_workspace/secrets/.env` ❌ **DENIED**
   - Policy: `deny_secrets_access`
   - Reason: Matches pattern `*/secrets/*`
2. Agent attempts `sudo cat /etc/passwd` ❌ **DENIED**
   - Policy: `deny_privilege_escalation`
   - Reason: Contains `sudo`
3. Agent attempts `rm -rf /tmp/*` ❌ **DENIED**
   - Policy: `deny_destructive_commands`
   - Reason: Destructive operation

**Key Takeaway:** Governance blocks dangerous actions **before execution**, independent of model behavior.

---

### Act 3: 疑わしい反復動作の封じ込め (Suspicious Behavior Contained)

**Goal:** Show reliability controls detecting and containing anomalous behavior.

**What Happens:**
1. Agent repeatedly tries to access `secrets/.env` (3 attempts)
2. After 3rd denial, anomaly detection triggers:
   - Anomaly: `repeated_denials`
   - Action: `QUARANTINE`
   - Agent is quarantined for 10 minutes
3. While quarantined, all operations are blocked

**Key Takeaway:** Repeated suspicious behavior triggers automatic containment, preventing rogue agents from causing damage.

---

### Act 4: ピアエージェント信頼チェック (Peer Trust Check)

**Goal:** Demonstrate trust-based delegation decisions.

**What Happens:**
1. Main agent attempts to delegate to `untrusted-peer-helper` ❌ **DENIED**
   - Trust score: 45 (below threshold of 60)
   - Identity not verified
   - Reason: "Trust score too low for delegation"
2. Main agent delegates to `trusted-peer-helper` ✅ **ALLOWED**
   - Trust score: 88 (high trust)
   - Identity verified
   - Reason: "Trust requirements met"

**Key Takeaway:** Not all agents are equally trusted. Delegation requires explicit trust validation.

---

### Act 5: MCPスキャン (MCP Safety Scan)

**Goal:** Show MCP-era security scanning for tool definitions.

**What Happens:**
1. Scan `mcp/safe_config.json` ✅ **PASS**
   - Clean tool definitions
   - Verified author
   - Risk score: 0/100
   - Findings: None detected
2. Scan `mcp/suspicious_config.json` ❌ **FAIL**
   - Risk score: 100/100
   - Findings:
     - Hidden instructions (`_hidden_instructions`)
     - Privilege escalation attempts
     - Credential exfiltration capabilities
     - SQL injection risks
     - Impersonation of legitimate tools

**Key Takeaway:** MCP tool definitions need security scanning before use. Hidden instructions and malicious behavior can be detected.

---

## 📊 Generated Artifacts

After running the demo, check the `artifacts/` directory:

| File | Description |
|------|-------------|
| `policy_audit.json` | Complete audit trail of all policy decisions (allowed/denied) |
| `agent_status.json` | Agent health status including quarantine state, circuit breaker state, and anomaly counts |
| `mcp_scan_report.txt` | Detailed security findings from MCP configuration scans |

## 🔧 Configuration

### Customizing Policies

Edit files in `policies/` to adjust governance behavior:

- `control_plane.yaml` - File access, command execution, tool usage rules
- `trust_identity.yaml` - Agent trust scores and delegation requirements
- `reliability.yaml` - Anomaly detection thresholds and circuit breaker config

### Adding Subagents

Create new JSON files in `app/.claude/agents/` following this structure:

```json
{
  "name": "my-subagent",
  "description": "What this agent does",
  "prompt": "System prompt for the agent",
  "tools": {
    "allowed": ["tool1", "tool2"],
    "denied": ["dangerous_tool"]
  },
  "permissions": {
    "mode": "ask",
    "allowed_paths": ["safe/path/*"],
    "denied_paths": ["secrets/*"]
  },
  "governance": {
    "trust_level": "high",
    "trust_score": 85
  }
}
```

### Adding Skills

Create new JSON files in `app/.claude/skills/` to define reusable capabilities.

## 🔗 Integration with Microsoft Agent Framework

This demo uses simulated agents and governance layers. To integrate with the actual Microsoft Agent Framework + Claude Agent SDK:

1. **Replace the demo runner** with MAF agent hosting
2. **Wire the governance layers** into MAF's middleware/hooks
3. **Configure Claude Agent SDK** to use the defined subagents and skills
4. **Deploy policies** to your governance infrastructure

See [Microsoft's blog post](https://devblogs.microsoft.com/agent-framework/build-ai-agents-with-claude-agent-sdk-and-microsoft-agent-framework/) for integration guidance.

## 🎓 Learning Points

### Why Governance Matters

This demo illustrates why governance is critical for production AI agent systems:

1. **Don't trust the model alone** - Even well-prompted models can be manipulated or make mistakes. System-level enforcement is essential.

2. **Defense in depth** - Multiple layers (policy, trust, anomaly detection, MCP scanning) work together.

3. **Explicit trust** - Trust is not implicit. Every delegation requires explicit trust validation.

4. **Behavioral monitoring** - Unusual patterns are detected and contained before they cause harm.

5. **Supply chain security** - In the MCP era, tool definitions are code. They need security scanning.

### Before and After Governance

| Without Governance | With Governance (This Demo) |
|-------------------|----------------------------|
| Agent reads secrets because LLM "didn't know better" | ❌ Blocked by policy before execution |
| Untrusted agent receives sensitive tasks | ❌ Blocked by trust validation |
| Rogue agent makes 1000 API calls | ❌ Quarantined after anomaly detection |
| Malicious MCP tool exfiltrates data | ❌ Flagged by security scanner |

## 🧪 Testing

```bash
# Run all acts sequentially
python app/demo.py

# Run specific act for focused testing
python app/demo.py act2

# Check generated artifacts
ls -l artifacts/
cat artifacts/policy_audit.json
cat artifacts/mcp_scan_report.txt
```

## 🚧 Limitations & Future Work

This is a **teaching/demo artifact**, not a production system. Current limitations:

- Simulated agents (not actual MAF/Claude SDK integration)
- Local-only (no distributed deployment)
- Mock MCP tools (not real MCP servers)
- No persistent storage
- No UI

**Future enhancements:**
- Real MAF + Claude SDK integration
- Distributed multi-node deployment
- Real MCP server integration
- Web UI for governance dashboard
- Persistent audit storage (e.g., Azure Cosmos DB)
- Advanced anomaly detection with ML

## 📚 References

- [Microsoft Agent Framework + Claude Agent SDK Announcement](https://devblogs.microsoft.com/agent-framework/build-ai-agents-with-claude-agent-sdk-and-microsoft-agent-framework/)
- [Claude Agent SDK Documentation](https://docs.anthropic.com/en/docs/agents)
- [Agent Governance Toolkit](https://github.com/anthropics/agent-governance-toolkit)
- Model Context Protocol (MCP) specification

## 📄 License

This project is licensed under the terms in the LICENSE file.

## 🤝 Contributing

This is a demonstration project. For production use cases, please consult the official Microsoft Agent Framework and Claude Agent SDK documentation.

## 📧 Questions?

For questions about:
- **Agent Governance Toolkit** - See [AGT repository](https://github.com/anthropics/agent-governance-toolkit)
- **Microsoft Agent Framework** - See [MAF documentation](https://devblogs.microsoft.com/agent-framework/)
- **Claude Agent SDK** - See [Claude documentation](https://docs.anthropic.com/)

---

**Built with ❤️ to demonstrate safe, trustworthy AI agent systems**
