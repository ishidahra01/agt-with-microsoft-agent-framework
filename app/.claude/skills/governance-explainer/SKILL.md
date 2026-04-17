---
name: governance-explainer
description: Explain governance, policy, trust, reliability, and MCP scan outcomes in concise Japanese when the operator needs to understand why an action was allowed or denied.
---

# Governance Explainer

Use this skill when you need to translate governance results into operator-facing Japanese.

## Use This Skill For

- Explaining why a file access or command was blocked or allowed.
- Summarizing trust and delegation decisions between agents.
- Explaining reliability events such as repeated denials or quarantine.
- Comparing MCP scan results and recommending the safer option.

## Response Style

- Write in concise, polite Japanese.
- Prefer concrete reasons over abstract policy language.
- Do not expose internal tool identifiers unless the operator explicitly asks.
- When possible, keep the explanation tied to the current ticket or request.

## Recommended Structure

### 何が起きたか

- Summarize the attempted action or request.

### 判定結果

- State whether it was allowed or denied.
- Give the direct reason first.

### 適用されたガバナンス

- Name the relevant control area, such as control plane, trust, reliability, or MCP review.
- Explain why that control exists.

### 推奨アクション

- Offer the safest next step available to the operator.

## Guardrails

- Never suggest bypassing the control that triggered the decision.
- If the request involves secrets, privilege escalation, or suspicious MCP behavior, recommend an approved human review path.