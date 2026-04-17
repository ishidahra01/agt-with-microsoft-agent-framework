# Observability Backends

This demo already exports Claude-native OTLP telemetry when the relevant environment variables are set in `.env`.

This repo is currently documented for one backend pattern only:

- Langfuse: direct OTLP over HTTP/protobuf from the Claude child process to Langfuse

## What the current app exports

The current implementation exports Claude-native telemetry from the Claude Code CLI that the Claude Agent SDK launches, and it can also emit Python-side spans from the repo runtime.

- Exported today: Claude CLI traces, and Python spans around the app runtime and governance MCP/tool checks
- Optional: Claude CLI metrics and Claude CLI log events
- Not exported automatically: every internal method in the repo-local governance runtime

The app uses one Langfuse-bound OpenTelemetry trace path. Python starts the parent span, injects `TRACEPARENT` into the Claude child process environment, and Claude Code CLI spans can join the same trace.

## Langfuse

Use this when you mainly want Claude traces and LLM-oriented observability.

1. Create a Langfuse project and get the public and secret keys.
2. Put the following in `.env`.

```dotenv
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

US region:

```dotenv
OTEL_EXPORTER_OTLP_ENDPOINT=https://us.cloud.langfuse.com/api/public/otel
```

Local/self-hosted Langfuse:

```dotenv
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/otel
```

Notes:

- Langfuse OTLP ingestion is trace-oriented. For this demo, start with traces only.
- Langfuse OTLP currently supports HTTP transport, not gRPC.
- Python tracing auto-follows the Claude trace settings when `APP_ENABLE_PYTHON_TRACING` is unset, so that variable is not needed in the minimal setup.
- If `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set, the app generates the OTLP `Authorization=Basic ...` header at startup and mirrors it back into the OTEL header environment variables used by Python tracing and the Claude child process.
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is included so the Python OTLP HTTP exporter uses the exact Langfuse trace endpoint while the Claude CLI continues to use the same backend.
- If you later want richer filtering in Langfuse, add `langfuse.*` span attributes in a second instrumentation phase. The current repo does not add those custom attributes yet.
- Python root spans and Claude CLI spans are intended to appear in the same trace. The bridge is W3C trace context passed through the `TRACEPARENT` environment variable.

Run the demo:

```bash
python app/demo.py act1
python app/demo.py demo
```

Then inspect traces in Langfuse. The most useful spans are usually `claude_code.interaction`, `claude_code.llm_request`, `claude_code.tool`, and `claude_code.hook`.

You should also see Python spans such as:

- `workspace-governor.run`
- `workspace_mcp.read_ticket`
- `workspace_mcp.read_runbook`
- `workspace_mcp.review_control_plane_request`
- `tool_permission_check`

## Current recommendation

- Keep telemetry Langfuse-only for now.
- Export traces first, then enable Claude metrics or Claude log events later only if you have a clear need.
- Treat Python spans as orchestration and governance context around the Claude CLI spans, not as a competing second backend.
