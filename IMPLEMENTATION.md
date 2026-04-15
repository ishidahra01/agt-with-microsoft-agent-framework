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
  - Claude subagent definitions
- Implemented a real MAF multi-agent workflow with `WorkflowBuilder`
- Wrapped the workflow with `from_agent_framework(...)`
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

## Compatibility shim

Two package mismatches exist in the installed environment:

1. `agent-framework-orchestrations` was referenced by MAF docs and lazy imports, but was not installable here.
2. `agent_os.integrations.maf_adapter` imports old `agent_sre` symbols that do not exist in the installed `agent_sre` build.

Because of those mismatches, the repo contains a local compatibility layer in [app/governance/runtime.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/governance/runtime.py) that preserves the intended architecture while staying on the installed official package APIs.

## Validated locally

These commands were run successfully:

```bash
python app/demo.py smoke-test
python app/demo.py act5
python app/demo.py demo
```

Live Claude inference was not validated end-to-end here because no Anthropic credential was present in the environment.
