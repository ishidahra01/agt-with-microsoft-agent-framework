# Governed Workspace Demo

This repository now uses the real package stack the original design called for:

- Microsoft Agent Framework as the runtime surface
- `agent-framework-claude` to construct Claude-backed agents from MAF
- Agent Governance Toolkit packages already installed in the environment
  - `agentmesh` for audit and identity-backed trust records
  - `agent_sre` for anomaly detection
  - `agent_os` official MCP scanner for MCP safety checks

The previous hand-written simulator has been replaced in the runtime path. The live entrypoint is [app/demo.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/demo.py).

## What is implemented

- A top-level `workspace-governor` Claude agent built through MAF
- Claude-side custom subagent definitions for:
  - `triage-subagent`
  - `executor-subagent`
  - `audit-explainer-subagent`
- Claude SDK features configured in code:
  - built-in Claude Code tool preset
  - permission modes
  - MCP server attachment
  - tool permission callback
  - hook callbacks for tool/subagent events
- MAF multi-agent workflow built with core `WorkflowBuilder` + `WorkflowAgent`
- Agent Governance runtime using current installed APIs:
  - control-plane compatibility middleware over the repo YAML policy files
  - AgentMesh audit log
  - AgentMesh-backed dynamic trust state, thresholds, and DIDs
  - Agent SRE anomaly detection and quarantine tracking
  - official Agent OS MCP config scanning
- Azure Agent Server host adapter creation via `from_agent_framework(...)`

## Important note about orchestrations

The public `agent_framework.orchestrations` namespace in this environment points to `agent-framework-orchestrations`, but that distribution was not installable here. Because of that, the repo uses the official core MAF workflow primitives that are installed and working now:

- `WorkflowBuilder`
- `WorkflowAgent`

This keeps the runtime on official MAF APIs instead of falling back to the previous mock orchestration layer.

## Run

```bash
python app/demo.py smoke-test
python app/demo.py demo
python app/demo.py act5
python app/demo.py serve
```

`demo` runs five educational acts:

1. Live workflow or smoke-test fallback
2. Control-plane blocking
3. Reliability / quarantine behavior
4. Trust-based delegation
5. Official MCP scanner

## Live Claude execution

Create a local `.env` from [`.env.example`](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/.env.example).

The live workflow path runs against Microsoft Foundry and requires one of these:

- `ANTHROPIC_FOUNDRY_RESOURCE`
- `ANTHROPIC_FOUNDRY_BASE_URL`

Optional authentication:

- `ANTHROPIC_FOUNDRY_API_KEY` for API key auth
- if omitted, the Claude process can use Entra ID via Azure CLI / managed identity / other credential sources supported by Foundry

Without a Foundry target, Act 1 falls back to a construction-only smoke test so the rest of the governance demo still runs.

The Claude child process now receives Foundry-specific environment variables from `.env` through `default_options["env"]`, including model pins and PowerShell tool configuration.

## Artifacts

Running `python app/demo.py demo` exports:

- [artifacts/audit-log.json](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/artifacts/audit-log.json)
- [artifacts/governance-snapshot.json](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/artifacts/governance-snapshot.json)

Dynamic trust state is also persisted incrementally at:

- [artifacts/trust-state.json](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/artifacts/trust-state.json)

## Repository focus

- [app/demo.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/demo.py): live entrypoint, Claude/MAF wiring, workflow construction
- [app/governance/runtime.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/governance/runtime.py): governance compatibility runtime on top of current AGT packages
- [policies/control_plane.yaml](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/policies/control_plane.yaml): control-plane rules
- [policies/trust_identity.yaml](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/policies/trust_identity.yaml): trust rules and peer metadata
- [policies/reliability.yaml](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/policies/reliability.yaml): anomaly thresholds
- [mcp/safe_config.json](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/mcp/safe_config.json): scanner-safe MCP example
- [mcp/suspicious_config.json](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/mcp/suspicious_config.json): scanner-detectable unsafe MCP example
