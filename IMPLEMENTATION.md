# Implementation Notes

## Summary

The runtime path is no longer a mock governance simulator.

The working implementation now lives in:

- [app/demo.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/demo.py)
- [app/governance/runtime.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/governance/runtime.py)

## What changed

- Replaced the old custom demo runner with real `ClaudeAgent` instances from `agent-framework-claude`
- Added Claude SDK configuration for:
  - built-in tools
  - permission modes
  - MCP server usage
  - hooks
  - programmatic Claude subagent definitions via `AgentDefinition`
  - project-scoped Claude Skills loaded from `app/.claude/skills/*/SKILL.md`
- Moved app-owned runtime assets under `app/`, including governance policies and MCP sample configuration files
- Wrapped the top-level `workspace-governor` with `from_agent_framework(...)`
- Replaced the old mock runtime governance path with current installed AGT components where they actually work:
  - `agentmesh.governance.AuditLog`
  - `agentmesh.AgentMeshClient` metadata/DIDs
  - `agent_sre.anomaly.AnomalyDetector`
  - `agent_os.cli.mcp_scan.scan_config`
- Reworked Acts 2-5 so they are no longer direct CLI-side subsystem checks:
  - The core framing remains an IT support ticket workflow: ticket review, runbook confirmation, and safe next actions
  - Act 2 invokes governance review inside that workflow when the operator asks for risky extra access
  - Act 3 accumulates live denials through repeated risky follow-up requests in the same support case
  - Act 4 invokes trust delegation review when deciding whether to share the investigation with a helper agent
  - Act 5 invokes MCP scanning when choosing a safe MCP configuration for the support workflow

## Runtime simplification

The app no longer uses a separate MAF `WorkflowAgent` orchestration layer.

- `act1` now runs the top-level `workspace-governor` directly.
- `act1b` remains the explicit Claude SDK subagent delegation demo.
- `serve` now exposes `workspace-governor` through the Azure Agent Server adapter.

This keeps the MAF integration for agent construction and hosting while making Claude SDK subagents the only multi-agent execution mechanism.

## Compatibility shim

Two package mismatches exist in the installed environment:

1. `agent-framework-orchestrations` was referenced by MAF docs and lazy imports, but was not installable here.
2. `agent_os.integrations.maf_adapter` imports old `agent_sre` symbols that do not exist in the installed `agent_sre` build.

Because of those mismatches, the repo contains a local compatibility layer in [app/governance/runtime.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/governance/runtime.py) that preserves the intended architecture while staying on the installed official package APIs.

## Claude Agent SDK implementation shape

The repository now follows the current Claude Agent SDK split:

- Skills are filesystem artifacts only. They live under `app/.claude/skills/<skill-name>/SKILL.md` and are discovered because `cwd` points at [app](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app) and `setting_sources=["project"]` is passed to the SDK.
- Subagents are defined programmatically in [app/demo.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/demo.py) with `AgentDefinition`, which is the SDK-recommended approach for app code.
- The top-level agent enables the `Skill` tool so project Skills can be invoked, and enables the `Agent` tool so Claude can delegate to programmatically defined subagents.
- The audit explainer subagent explicitly opts into the `governance-explainer` Skill because subagents do not inherit parent Skills automatically.

## App boundary

The repository now treats [app](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app) as the application boundary:

- `app/.claude/` contains Claude SDK customization.
- `app/policies/` contains governance policy definitions loaded directly by the runtime.
- `app/mcp/` contains MCP configuration samples used by the Act 5 scanner demo.
- [demo_workspace](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/demo_workspace) remains outside the app because it represents the external workspace or storage target the agent operates on.

## Validated locally

These commands were run successfully:

```bash
python app/demo.py smoke-test
python app/demo.py act5
python app/demo.py demo
```

Live Claude inference was not validated end-to-end here because no Anthropic credential was present in the environment.
