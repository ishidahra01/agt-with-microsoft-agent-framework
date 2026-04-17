# Quick Start

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Configure Microsoft Foundry

Create a local `.env` from [`.env.example`](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/.env.example) and set either:

- `ANTHROPIC_FOUNDRY_RESOURCE`
- `ANTHROPIC_FOUNDRY_BASE_URL`

The Claude and Foundry settings are the required part. The OTEL and Langfuse entries in `.env.example` are optional and only needed if you want tracing.

Optional:

- `ANTHROPIC_FOUNDRY_API_KEY` for API key auth
- otherwise Foundry auth is expected to come from Entra ID-compatible sources

## 3. Validate the stack

```bash
python app/demo.py smoke-test
```

This verifies that:

- Claude-backed agents are constructed through `agent-framework-claude`
- the Agent Governance runtime initializes
- the Azure Agent Server adapter can wrap the top-level agent
- project-scoped Claude Skills can be discovered from `app/.claude/skills/`

## 4. Run the educational demo

```bash
python app/demo.py demo
```

Expected behavior without Foundry target configuration:

- Act 1: construction-only smoke-test output
- Act 1B-5: live Claude execution is skipped with a configuration warning because these acts now execute through the Claude runtime

## 5. Run a single act

```bash
python app/demo.py act2
python app/demo.py act4
python app/demo.py act5
python app/demo.py act1b
```

## 6. Enable live Claude execution

Set one of these and rerun `act1` or `demo`:

```bash
set ANTHROPIC_FOUNDRY_RESOURCE=...
```

or

```bash
set ANTHROPIC_FOUNDRY_BASE_URL=...
```

Optional API key auth:

```bash
set ANTHROPIC_FOUNDRY_API_KEY=...
```

Then run:

```bash
python app/demo.py act1 --prompt "TICKET-001 を読み、runbook を確認して安全な次アクションを日本語でまとめてください。"
```

## 7. Claude SDK layout in this repo

- Skills: `app/.claude/skills/*/SKILL.md`
- Subagents: programmatic `AgentDefinition` instances in [app/demo.py](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/app/demo.py)
- Runtime wrapper: `from agent_framework_claude import ClaudeAgent` remains the construction path
- App-owned policy files: `app/policies/`
- App-owned MCP sample configs: `app/mcp/`

`demo_workspace/` remains outside `app/` because it models the external workspace or storage target the agent inspects.

## 8. Start the HTTP endpoint

```bash
python app/demo.py serve --port 8088
```

## 9. Export artifacts only

```bash
python app/demo.py export-artifacts
```
