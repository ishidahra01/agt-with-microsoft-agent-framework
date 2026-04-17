# Demo Guide

This document explains what each demo act is trying to show, what successful behavior looks like, and how to interpret the outcome.

The goal is not to prescribe exact wording from the model. The important part is whether the right governance path, delegation path, and tool usage happened.

## How to use this guide

- Use this document before running a demo to understand what each act is intended to prove.
- Use it after a run to judge whether the demo behavior was correct at a functional level.
- Treat model wording as flexible. Treat tool usage, delegation behavior, trust changes, and policy outcomes as the real signals.

## Demo map

| Act | Main purpose | Primary mechanism |
| --- | --- | --- |
| Act 1 | Normal governed support workflow | `workspace-governor` direct Claude path |
| Act 1B | Explicit Claude SDK subagent delegation | Claude `Agent` tool + `AgentDefinition` subagents |
| Act 2 | Control-plane denial and explanation | Governance review MCP tool |
| Act 3 | Reliability degradation and quarantine | Governance review MCP tool + reliability monitor |
| Act 4 | Trust-based delegation decision | Delegation review MCP tool + trust registry |
| Act 5 | MCP configuration safety review | MCP scan tool |

## Act 1: Live Workflow

### Act 1 purpose

Show the default operator experience for a normal support request.

This is the baseline path: the top-level `workspace-governor` reads the ticket and runbook, inspects allowed workspace state, and proposes safe next actions in Japanese.

### Act 1 demonstration target

- The top-level Claude agent can do useful work without needing an explicit subagent path.
- The agent stays inside the approved workspace boundaries.
- The agent can use workspace and governance tools to produce a grounded answer.

### Act 1 success criteria

- The agent reads the ticket and runbook.
- The answer stays in the IT support frame rather than drifting into generic advice.
- The proposed next actions are read-only or otherwise policy-safe.
- Restricted areas such as `secrets/` are treated as sensitive or blocked.

### Act 1 interpretation

- The top-level agent is configured correctly.
- MCP tools for workspace inspection are connected and callable.
- Governance context is influencing the final answer even when the request is benign.

## Act 1B: Claude SDK Subagents

### Act 1B purpose

Prove that Claude SDK subagent delegation is really happening.

This act is intentionally explicit: the parent agent is instructed to use `triage-subagent` first and then `audit-explainer-subagent`.

### Act 1B demonstration target

- `AgentDefinition` subagents are registered correctly.
- The `Agent` tool is enabled and allowed.
- The parent agent can route work to specialized subagents and then compose the result.

### Act 1B success criteria

- The final answer clearly reflects a two-stage flow: triage first, explanation second.
- The audit artifacts show `Agent` tool usage.
- The audit artifacts show `SubagentStart` and `SubagentStop` events.
- The triage subagent performs the workspace-reading work rather than the parent doing all of it directly.

### Act 1B interpretation

- The repository is correctly using Claude SDK subagents, not just simulating them in prompt text.
- The app's Claude-side multi-agent path is working independently of any outer orchestration layer.

## Act 2: Control Plane

### Act 2 purpose

Show that a risky follow-up request is not merely answered politely but is formally checked against governance policy.

### Act 2 demonstration target

- Prompt, file, and command requests can be evaluated by the control plane.
- The model can explain a governance denial in operator-facing language.
- Denied operations still produce a useful answer with alternatives.

### Act 2 success criteria

- Sensitive file access such as `secrets/.env` is denied.
- Privileged command use such as `sudo ...` is denied.
- The response includes the reason for rejection and a safer alternative path.
- The trust state may change due to policy violations or checks.

### Act 2 interpretation

- Governance is not cosmetic. It is being invoked as part of the agent flow.
- The agent can turn structured governance results into an operator-readable explanation.

## Act 3: Reliability

### Act 3 purpose

Show that repeated unsafe behavior is tracked over time and can trigger containment.

### Act 3 demonstration target

- Repeated denied requests are not treated as isolated events.
- Reliability monitoring accumulates signals across attempts.
- Quarantine can be triggered as an operational consequence.

### Act 3 success criteria

- Repeated restricted requests are denied again.
- The reliability state changes across attempts.
- At some point the app reports that `workspace-governor` is quarantined.
- The trust snapshot or governance snapshot reflects the quarantine outcome.

### Act 3 interpretation

- The demo has moved beyond single-request policy checks and is exercising stateful governance.
- The system can enforce consequences when an agent keeps pushing against policy boundaries.

## Act 4: Trust

### Act 4 purpose

Show that delegation depends on trust and identity, not just capability names.

### Act 4 demonstration target

- The app can evaluate whether another agent is safe to delegate to.
- Trusted and untrusted peers produce different outcomes.
- Delegation review can be surfaced in plain Japanese for an operator.

### Act 4 success criteria

- `trusted-peer-helper` is allowed.
- `untrusted-peer-helper` is denied.
- The answer explains the difference using trust score, trust tier, identity verification, or similar governance signals.

### Act 4 interpretation

- Delegation is governed by identity and trust state, not only by task semantics.
- The trust registry is actively influencing agent behavior.

## Act 5: MCP Scan

### Act 5 purpose

Show that candidate MCP configurations can be evaluated before adoption.

### Act 5 demonstration target

- The MCP scan capability is integrated into the agent flow.
- A safe and suspicious configuration can be compared in one operator-facing answer.
- The result is actionable: adopt one, reject the other.

### Act 5 success criteria

- `safe_config.json` is assessed as acceptable or clean.
- `suspicious_config.json` is assessed as risky or unacceptable.
- The response names the risky properties in plain language.
- The final recommendation is unambiguous.

### Act 5 interpretation

- MCP safety review is part of the governance surface, not an external manual step.
- The agent can convert scanner findings into a deployment decision.

## About the console output

Most of the long Japanese prose printed during the demo is generated by Claude after reading tool results.

There are also app-level control messages printed by Python itself, for example:

- `INFO Trust before ...`
- `INFO Trust after ...`
- `WARN ...`
- `BLOCK Attempt ... quarantine triggered ...`
- artifact export messages

The distinction matters:

- Claude prose tells you how the model interpreted the governance outcome.
- App control messages tell you what the runtime itself enforced or recorded.

## Observability during demos

The demo can export Claude-native OpenTelemetry signals when telemetry variables are set in `.env`.

What is exported:

- Python spans around the main governed runtime path and selected governance/tool boundaries
- Metrics for Claude usage and tool activity
- Structured Claude log events
- Claude traces for interactions, model requests, tool calls, and hooks

What enables it:

- `CLAUDE_CODE_ENABLE_TELEMETRY=1`
- one or more of `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`
- `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` if you want traces

Recommended demo settings:

- Use OTLP over HTTP/protobuf
- Point `OTEL_EXPORTER_OTLP_ENDPOINT` at Langfuse
- Set `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` to Langfuse's `/v1/traces` endpoint for Python-side tracing
- Keep export intervals at `1000` ms for short-lived acts so the Claude child process flushes before exit
- Use Langfuse for trace-first inspection

Important constraint:

- Do not set any exporter to `console`. Claude Agent SDK uses stdout as its response transport, so console telemetry would corrupt the message stream.

How to interpret exported traces:

- Python parent spans represent orchestration and governance work inside this repo
- `claude_code.interaction` shows one agent loop turn
- `claude_code.llm_request` shows one model call
- `claude_code.tool` shows a tool invocation
- `claude_code.hook` shows a hook execution

The Python runtime now creates parent spans and passes W3C trace context into the Claude child process with `TRACEPARENT`, so Langfuse can show Python spans and Claude CLI spans as one trace. If you still do not see some trust or reliability internals, that is expected: not every internal helper is instrumented.

Backend-specific setup files in this repo:

- [observability/README.md](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/observability/README.md)

## What to inspect when behavior looks suspicious

- Check [artifacts/audit-log.json](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/artifacts/audit-log.json) to see which tools were actually called.
- Check [artifacts/governance-snapshot.json](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/artifacts/governance-snapshot.json) to inspect trust and reliability state after the run.
- For Act 1B specifically, look for `Agent` tool usage and `SubagentStart` / `SubagentStop` events.
- For Acts 2-5, look for the governance MCP tool calls rather than just the final prose.

## Minimal success checklist

If you want a fast judgment after running `python app/demo.py demo`, these are the key checks:

- Act 1 returns a safe support summary grounded in ticket/runbook/workspace state.
- Act 1B shows explicit subagent delegation behavior.
- Act 2 denies secret access and privileged command use.
- Act 3 triggers reliability consequences for repeated unsafe requests.
- Act 4 approves trusted delegation and rejects untrusted delegation.
- Act 5 recommends `safe_config.json` and rejects `suspicious_config.json`.

If those six things hold, the demo is functioning as intended at a repo-consumer level.
