# Architecture

This document describes the architecture of the Governed Workspace Demo application.

## Overview

The application demonstrates governance integration with Microsoft Agent Framework (MAF) and Claude Agent SDK, showcasing how to build governed multi-agent systems.

## Technology Stack

### Core Frameworks
- **Microsoft Agent Framework (MAF)**: Agent runtime surface and hosting
- **agent-framework-claude**: Constructs Claude-backed agents from MAF
- **Claude Agent SDK**: Provides subagent definitions, skills, and tool management

### Governance Components
- **agentmesh**: Audit logging and identity-backed trust records
- **agent_sre**: Anomaly detection and reliability monitoring
- **agent_os**: Official MCP scanner for safety checks

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                   Azure Agent Server                        │
│                  (HTTP/REST Interface)                      │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              workspace-governor (MAF Agent)                 │
│           Built with agent-framework-claude                 │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐  ┌────────▼────────┐  ┌──────▼────────┐
│  triage-     │  │   executor-     │  │  audit-       │
│  subagent    │  │   subagent      │  │  explainer-   │
│              │  │                 │  │  subagent     │
└──────────────┘  └─────────────────┘  └───────────────┘
     (Claude SDK AgentDefinition instances)

                            │
┌─────────────────────────────────────────────────────────────┐
│                  Governance Runtime                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Control     │  │    Trust     │  │ Reliability  │     │
│  │   Plane      │  │  Governance  │  │  Monitoring  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                     MCP Tools Layer                          │
│  - Workspace tools (read ticket, runbook)                   │
│  - Governance review tools                                   │
│  - Delegation review tools                                   │
│  - MCP config scanner                                        │
└─────────────────────────────────────────────────────────────┘
```

## Agent Hierarchy

### Top-Level Agent: workspace-governor
- Built through MAF using `agent-framework-claude`
- Wrapped with Azure Agent Server adapter via `from_agent_framework(...)`
- Configured with Claude Code tool preset
- Enabled with both `Skill` and `Agent` tools

### Claude SDK Subagents
Defined programmatically with `AgentDefinition`:

1. **triage-subagent**: Reads tickets and runbooks, identifies safe actions
2. **executor-subagent**: Executes workspace operations
3. **audit-explainer-subagent**: Formats governance results for operators
   - Explicitly opts into the `governance-explainer` Skill

### Claude SDK Skills
Filesystem-based artifacts in `app/.claude/skills/*/SKILL.md`:
- `governance-explainer`: Explains governance decisions
- `demo-walkthrough`: Guides through demo scenarios

## Governance Integration

### Control Plane
- Policy definitions in `app/policies/control_plane.yaml`
- Evaluates prompt, file, and command requests
- Blocks restricted operations (e.g., secret access, privileged commands)

### Trust Governance
- Identity and trust metadata in `app/policies/trust_identity.yaml`
- AgentMesh-backed dynamic trust state
- DID-based peer verification
- Trust scores and tier evaluation

### Reliability Monitoring
- Anomaly detection with Agent SRE
- Threshold configuration in `app/policies/reliability.yaml`
- Quarantine tracking for repeated violations
- Stateful monitoring across requests

### MCP Safety
- Official Agent OS MCP scanner
- Sample configurations in `app/mcp/`:
  - `safe_config.json`: Scanner-approved configuration
  - `suspicious_config.json`: Detectable unsafe configuration

## Data Flow

### Act 1: Normal Workflow
```
User Request
    ↓
workspace-governor
    ↓
MCP Tools (read ticket, runbook)
    ↓
Governance Review (control plane check)
    ↓
Response to User
```

### Act 1B: Subagent Delegation
```
User Request
    ↓
workspace-governor
    ↓
Agent tool → triage-subagent
    ↓
Workspace reading
    ↓
Back to workspace-governor
    ↓
Agent tool → audit-explainer-subagent
    ↓
Format explanation
    ↓
Final response
```

### Acts 2-5: Governance Scenarios
Each act integrates governance checks into realistic support workflows:
- Act 2: Control-plane denial
- Act 3: Reliability degradation
- Act 4: Trust-based delegation
- Act 5: MCP configuration review

## Directory Structure

```
app/
├── demo.py              # Main entrypoint
├── governance/          # Governance runtime
│   └── runtime.py       # Compatibility layer over AGT packages
├── policies/            # Policy definitions
│   ├── control_plane.yaml
│   ├── trust_identity.yaml
│   └── reliability.yaml
├── mcp/                 # MCP sample configurations
│   ├── safe_config.json
│   └── suspicious_config.json
└── .claude/             # Claude SDK artifacts
    └── skills/          # Filesystem-based skills
        ├── governance-explainer/
        └── demo-walkthrough/

demo_workspace/          # External workspace
├── tickets/            # Work tickets
├── runbooks/           # Standard procedures
└── secrets/            # Restricted area

artifacts/              # Runtime output
├── audit-log.json      # AgentMesh audit log
├── governance-snapshot.json
└── trust-state.json    # Dynamic trust state
```

## Runtime Environment

### Claude Execution
- Claude Agent SDK launches Claude Code CLI as child process
- Environment variables forwarded from `.env`
- Foundry-specific configuration for model and PowerShell tools

### Observability
- Claude-native OTLP telemetry export
- Python parent spans + Claude CLI spans in single trace
- W3C trace context via `TRACEPARENT` injection
- Langfuse as trace backend (OTLP over HTTP/protobuf)

### Compatibility Layer
The governance runtime in `app/governance/runtime.py` provides a compatibility layer because:
1. `agent-framework-orchestrations` package was not installable
2. `agent_os.integrations.maf_adapter` has mismatched dependencies

This layer preserves the architecture while using installed AGT package APIs.

## Key Design Decisions

### Single Top-Level Agent
- Only `workspace-governor` is hosted/live
- No extra WorkflowAgent orchestration layer
- Claude SDK subagents provide multi-agent delegation

### Skill vs Subagent Split
- **Skills**: Filesystem artifacts for domain knowledge
- **Subagents**: Programmatic definitions for execution roles
- Skills loaded via `setting_sources=["project"]`
- Subagents registered with `AgentDefinition`

### App Boundary
- `app/` contains the application
- `demo_workspace/` represents external storage
- Clear separation of concerns

### Governance as MCP Tools
- Governance exposed through MCP tools
- Integrated into agent workflow
- Not standalone CLI-side checks
- Natural agent experience

## Extension Points

### Adding New Subagents
1. Create `AgentDefinition` in `app/demo.py`
2. Configure tools and permissions
3. Register with parent agent
4. Add to subagent list

### Adding New Skills
1. Create `app/.claude/skills/<skill-name>/SKILL.md`
2. Define skill instructions in Markdown
3. Skills auto-discovered via `setting_sources=["project"]`

### Adding New Governance Policies
1. Add rules to appropriate YAML in `app/policies/`
2. Update governance runtime if needed
3. Add corresponding MCP tools if required

### Adding New MCP Configurations
1. Create JSON in `app/mcp/`
2. Update Act 5 demo to include new config
3. Document expected scanner results
