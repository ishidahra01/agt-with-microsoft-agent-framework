# Quick Start

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Configure Microsoft Foundry

Create a local `.env` from [`.env.example`](c:/Users/hishida/repo/agt-with-microsoft-agent-framework/.env.example) and set either:

- `ANTHROPIC_FOUNDRY_RESOURCE`
- `ANTHROPIC_FOUNDRY_BASE_URL`

Optional:

- `ANTHROPIC_FOUNDRY_API_KEY` for API key auth
- otherwise Foundry auth is expected to come from Entra ID-compatible sources

## 3. Validate the stack

```bash
python app/demo.py smoke-test
```

This verifies that:

- MAF workflow objects build
- Claude-backed agents are constructed through `agent-framework-claude`
- the Agent Governance runtime initializes
- the Azure Agent Server adapter can wrap the workflow

## 4. Run the educational demo

```bash
python app/demo.py demo
```

Expected behavior without Foundry target configuration:

- Act 1: construction-only smoke-test output
- Act 2: secret access / privilege escalation blocked
- Act 3: repeated denials trigger quarantine
- Act 4: trusted peer allowed, untrusted peer denied
- Act 5: suspicious MCP config flagged by the official scanner

## 5. Run a single act

```bash
python app/demo.py act2
python app/demo.py act4
python app/demo.py act5
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

## 7. Start the HTTP endpoint

```bash
python app/demo.py serve --port 8088
```

## 8. Export artifacts only

```bash
python app/demo.py export-artifacts
```
