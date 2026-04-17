# Governed Workspace Demo

This repository now uses the real package stack the original design called for:

- Microsoft Agent Framework as the runtime surface
- `agent-framework-claude` to construct Claude-backed agents from MAF
- Agent Governance Toolkit packages already installed in the environment
  - `agentmesh` for audit and identity-backed trust records
  - `agent_sre` for anomaly detection
  - `agent_os` official MCP scanner for MCP safety checks

The previous hand-written simulator has been replaced in the runtime path. The live entrypoint is [app/demo.py](app/demo.py).

For a repo-consumer view of what each demo act is trying to show, what successful behavior looks like, and how to interpret the result, see [DEMO_GUIDE.md](DEMO_GUIDE.md).

## What is implemented

- A top-level `workspace-governor` Claude agent built through MAF and framed as an IT support workspace agent
- Claude SDK subagents defined programmatically in [app/demo.py](app/demo.py) using `AgentDefinition` for:
  - `triage-subagent`
  - `executor-subagent`
  - `audit-explainer-subagent`
- Claude SDK Skills defined as filesystem artifacts under `app/.claude/skills/*/SKILL.md` and loaded through `setting_sources=["project"]`
- Claude SDK features configured in code:
  - built-in Claude Code tool preset
  - permission modes
  - MCP server attachment
  - tool permission callback
  - hook callbacks for tool/subagent events
- official Claude SDK feature split:
  - Skills are filesystem-based and enabled with the `Skill` tool
  - Subagents are programmatic and enabled with the `Agent` tool
- Governance MCP tools exposed to the agent for integrated demos:
  - control-plane review tool
  - delegation review tool
  - MCP config scan tool
- App-scoped runtime assets:
  - governance policy definitions under `app/policies/`
  - MCP sample configurations under `app/mcp/`
- Agent Governance runtime using current installed APIs:
  - control-plane compatibility middleware over the repo YAML policy files
  - AgentMesh audit log
  - AgentMesh-backed dynamic trust state, thresholds, and DIDs
  - Agent SRE anomaly detection and quarantine tracking
  - official Agent OS MCP config scanning
- Azure Agent Server host adapter creation via `from_agent_framework(...)` on the top-level `workspace-governor` agent

## Runtime shape

The runtime is now intentionally centered on a single top-level Claude agent plus Claude SDK subagents.

- `workspace-governor` is the only hosted/live agent surface
- Claude SDK `AgentDefinition` subagents provide the multi-agent delegation path
- The Azure Agent Server adapter wraps `workspace-governor` directly

This removes the extra WorkflowAgent orchestration layer and keeps the demo focused on Claude SDK delegation plus governance enforcement.

## Run

```bash
python app/demo.py smoke-test
python app/demo.py demo
python app/demo.py act5
python app/demo.py serve
```

`demo` runs six educational acts around the same IT support scenario for `TICKET-001`:

1. Ticket review, runbook confirmation, and safe next-action summary
2. Explicit Claude SDK subagent delegation through the `Agent` tool
3. A risky follow-up request in the same support flow that is blocked by the control plane
4. Repeated risky follow-up requests that trigger reliability quarantine tracking
5. A support-task delegation decision evaluated through trust governance
6. MCP configuration selection for the same support case, evaluated through governance scanning

## Live Claude execution

Create a local `.env` from [`.env.example`](.env.example).

For actual app execution, the Claude and Foundry settings are the baseline required configuration. The OTEL and Langfuse settings in `.env.example` are optional and are only needed if you want observability.

The live workflow path runs against Microsoft Foundry and requires one of these:

- `ANTHROPIC_FOUNDRY_RESOURCE`
- `ANTHROPIC_FOUNDRY_BASE_URL`

Optional authentication:

- `ANTHROPIC_FOUNDRY_API_KEY` for API key auth
- if omitted, the Claude process can use Entra ID via Azure CLI / managed identity / other credential sources supported by Foundry

In practice, the minimum required `.env` for live Claude execution is:

```bash
CLAUDE_CODE_USE_FOUNDRY=1
ANTHROPIC_FOUNDRY_RESOURCE=<your-foundry-resource-name>
# or ANTHROPIC_FOUNDRY_BASE_URL=<your-foundry-base-url>

# optional if you use API key auth
ANTHROPIC_FOUNDRY_API_KEY=<your-foundry-api-key>
```

Without a Foundry target, Act 1 falls back to a construction-only smoke test. Acts 1B-5 depend on live Claude execution because they are implemented as integrated agent scenarios rather than direct local function demos.

The Claude child process now receives Foundry-specific environment variables from `.env` through `default_options["env"]`, including model pins and PowerShell tool configuration.

## Claude SDK observability

If you want telemetry, the live demo can export Claude-native OpenTelemetry signals directly from the Claude Code CLI that the SDK launches.

- This path is native to Claude Agent SDK. The SDK forwards environment variables to the Claude CLI child process.
- Metrics, log events, and traces can be exported over OTLP to any compatible collector.
- Traces require `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` because Claude span export is still marked beta.

Optional `.env` additions for Langfuse tracing:

```bash
# .env
ANTHROPIC_FOUNDRY_RESOURCE=<your-foundry-resource-name>
# or ANTHROPIC_FOUNDRY_BASE_URL=<your-foundry-base-url>
CLAUDE_CODE_ENABLE_TELEMETRY=1
CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces
LANGFUSE_PUBLIC_KEY=<your-langfuse-public-key>
LANGFUSE_SECRET_KEY=<your-langfuse-secret-key>
```

Notes:

- Do not use the `console` exporter through Claude Agent SDK. The SDK uses stdout as its message channel.
- Add `ANTHROPIC_FOUNDRY_API_KEY` only if you use API key auth. Otherwise Entra ID can be used.
- Python tracing auto-follows the Claude trace settings when `APP_ENABLE_PYTHON_TRACING` is unset, so it is not required in the minimal `.env`.
- If `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set, the app builds `Authorization=Basic ...` for OTLP headers at startup so you do not need to pre-encode them in `.env`.
- Sensitive content export is opt-in through `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS`, and `OTEL_LOG_TOOL_CONTENT`.
- For backend-specific setup, see [observability/README.md](observability/README.md).

What this gives you:

- Python parent spans around the governed runtime and selected governance operations
- Claude interaction, LLM request, tool, and hook telemetry from the Claude CLI execution path
- Token, cost, and tool decision metrics emitted by Claude Code
- Structured Claude-side events for prompts, tool results, and API failures

What it does not automatically instrument:

- Every internal method in the repo-local governance runtime. The current implementation traces the main orchestration path and selected governance/tool boundaries.

The Python runtime now injects W3C trace context into the Claude child process through `TRACEPARENT`, so Python spans and Claude CLI spans can appear under the same trace in Langfuse.

### Backend choices in this repo

- Langfuse is the current supported backend in this repo and is used as a direct OTLP trace backend with no collector required.
- The current app emits Python spans and Claude child-process spans into the same Langfuse-bound trace path.

## Claude SDK alignment

The Claude-specific customization now follows the current SDK guidance:

- Skills are defined only as Markdown artifacts in `app/.claude/skills/.../SKILL.md`
- The runtime loads those Skills by setting `cwd` to [app](app) and `setting_sources=["project"]`
- Subagents are defined in code with `AgentDefinition`, which is the SDK-recommended path for applications
- The older JSON files under `app/.claude/...` were removed because they were non-standard for SDK Skills. `app/.claude` now contains only the Markdown Skill artifacts the SDK expects.

## Integrated governance scenarios

Acts 2-5 no longer call governance subsystems directly from the CLI entrypoint.

- Act 2 keeps the IT support context intact and shows how a risky operator follow-up is formally denied by governance.
- Act 3 keeps the same support case active and shows how repeated denied requests degrade reliability and trigger quarantine.
- Act 4 shows how the agent evaluates whether a helper can safely share the TICKET-001 investigation workload.
- Act 5 shows how the agent evaluates candidate MCP configurations before recommending one for the support workflow.

This keeps the ticket triage and safe-action workflow as the mainline experience while making Acts 1B-5 show governance and subagent behavior inside realistic agent activity rather than as standalone direct checks.

## Repository layout

- [app](app) contains the agent application itself, including Claude settings, runtime code, policies, and MCP sample definitions.
- [demo_workspace](demo_workspace) stays outside the app as the stand-in for an external workspace or storage target that the agent operates on.
- [artifacts](artifacts) contains run output and exported state.

## Artifacts

Running `python app/demo.py demo` exports:

- [artifacts/audit-log.json](artifacts/audit-log.json)
- [artifacts/governance-snapshot.json](artifacts/governance-snapshot.json)

Dynamic trust state is also persisted incrementally at:

- [artifacts/trust-state.json](artifacts/trust-state.json)

## Repository focus

- [app/demo.py](app/demo.py): live entrypoint, Claude/MAF wiring, subagent and governance configuration
- [app/governance/runtime.py](app/governance/runtime.py): governance compatibility runtime on top of current AGT packages
- [app/policies/control_plane.yaml](app/policies/control_plane.yaml): control-plane rules
- [app/policies/trust_identity.yaml](app/policies/trust_identity.yaml): trust rules and peer metadata
- [app/policies/reliability.yaml](app/policies/reliability.yaml): anomaly thresholds
- [app/mcp/safe_config.json](app/mcp/safe_config.json): scanner-safe MCP example
- [app/mcp/suspicious_config.json](app/mcp/suspicious_config.json): scanner-detectable unsafe MCP example
